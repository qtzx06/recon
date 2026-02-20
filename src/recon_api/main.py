import json
from collections.abc import Callable, Generator
from queue import Queue
from threading import Thread
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from .bedrock_client import analyze_wallet_with_bedrock
from .datadog_client import send_wallet_trace_log
from .observability import TraceCollector
from .schemas import (
    SocialIntel,
    WalletIntelligence,
    WalletMetrics,
    WalletReportRequest,
    WalletReportResponse,
)
from .settings import settings
from .solana_client import SolanaRPCError, SolanaRateLimitError, collect_wallet_report_data
from .x_client import XSearchError, search_x_mentions

app = FastAPI(title='recon API', version='0.1.0')
EventCallback = Callable[[str, dict | None], None]


def _looks_like_solana_wallet(value: str) -> bool:
    if len(value) < 32 or len(value) > 44:
        return False
    allowed = set('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz')
    return all(ch in allowed for ch in value)


@app.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}


def _emit(on_event: EventCallback | None, event: str, data: dict | None = None) -> None:
    if on_event:
        on_event(event, data or {})


def _build_wallet_report(
    payload: WalletReportRequest, on_event: EventCallback | None = None
) -> WalletReportResponse:
    if not _looks_like_solana_wallet(payload.wallet):
        raise HTTPException(status_code=400, detail='Invalid Solana wallet format')

    max_signatures = payload.max_signatures or settings.solana_signature_limit
    trace = TraceCollector()
    _emit(
        on_event,
        'started',
        {'wallet': payload.wallet, 'max_signatures': max_signatures},
    )

    try:
        _emit(
            on_event,
            'step_started',
            {'step': 'solana_research', 'detail': f'max_signatures={max_signatures}'},
        )
        with trace.step('solana_research', detail=f'max_signatures={max_signatures}'):
            metrics_dict, intelligence_dict = collect_wallet_report_data(
                rpc_url=settings.solana_rpc_url,
                wallet=payload.wallet,
                max_signatures=max_signatures,
                timeout_s=settings.recon_timeout_seconds,
            )
        metrics = WalletMetrics.model_validate(metrics_dict)
        intelligence = WalletIntelligence.model_validate(intelligence_dict)
        _emit(
            on_event,
            'step_completed',
            {'step': 'solana_research', 'signature_count': metrics.signature_count},
        )
    except SolanaRateLimitError as exc:
        _emit(
            on_event,
            'error',
            {
                'step': 'solana_research',
                'status_code': 503,
                'detail': 'Solana RPC rate limited. Use a private RPC URL in SOLANA_RPC_URL and retry.',
            },
        )
        raise HTTPException(
            status_code=503,
            detail='Solana RPC rate limited. Use a private RPC URL in SOLANA_RPC_URL and retry.',
        ) from exc
    except (SolanaRPCError, ValidationError, ValueError) as exc:
        _emit(
            on_event,
            'error',
            {
                'step': 'solana_research',
                'status_code': 502,
                'detail': f'Failed to build wallet metrics: {exc}',
            },
        )
        raise HTTPException(status_code=502, detail=f'Failed to build wallet metrics: {exc}') from exc

    social: SocialIntel | None = None
    if settings.recon_enable_x_search and settings.x_bearer_token:
        try:
            funders = [w.wallet for w in intelligence.likely_funders[:2]]
            funded = [w.wallet for w in intelligence.likely_funded_wallets[:2]]
            query_terms = [payload.wallet, *funders, *funded]
            _emit(
                on_event,
                'step_started',
                {'step': 'x_search', 'detail': f'terms={len(query_terms)}'},
            )
            with trace.step('x_search', detail=f'terms={len(query_terms)}'):
                social = search_x_mentions(
                    bearer_token=settings.x_bearer_token,
                    query_terms=query_terms,
                    timeout_s=settings.recon_timeout_seconds,
                    max_results=settings.x_max_results,
                )
            _emit(
                on_event,
                'step_completed',
                {
                    'step': 'x_search',
                    'query_terms': query_terms,
                    'total_results': social.total_results if social else 0,
                },
            )
        except XSearchError as exc:
            social = SocialIntel(query_terms=[], total_results=0, mentions=[])
            _emit(
                on_event,
                'step_failed',
                {
                    'step': 'x_search',
                    'status_code': exc.status_code,
                    'detail': f'{exc.detail}; continuing without social enrichment',
                },
            )
        except Exception as exc:
            social = SocialIntel(query_terms=[], total_results=0, mentions=[])
            _emit(
                on_event,
                'step_failed',
                {
                    'step': 'x_search',
                    'detail': f'X search failed ({exc}); continuing without social enrichment',
                },
            )
    else:
        _emit(
            on_event,
            'step_skipped',
            {'step': 'x_search', 'detail': 'x search disabled or token missing'},
        )

    if settings.recon_metrics_only:
        response = WalletReportResponse(
            metrics=metrics,
            intelligence=intelligence,
            social=social,
            analysis='Metrics-only mode enabled. Bedrock analysis skipped.',
            model=None,
            trace=trace.as_list(),
        )
        _emit(
            on_event,
            'step_skipped',
            {'step': 'bedrock_analysis', 'detail': 'metrics-only mode enabled'},
        )
        try:
            send_wallet_trace_log(
                wallet=payload.wallet,
                trace=response.trace,
                metrics=metrics.model_dump(),
                social_count=social.total_results if social else 0,
            )
        except Exception:
            pass
        _emit(
            on_event,
            'completed',
            {'response': response.model_dump(mode='json')},
        )
        return response

    try:
        _emit(on_event, 'step_started', {'step': 'bedrock_analysis'})
        with trace.step('bedrock_analysis'):
            analysis, model = analyze_wallet_with_bedrock(
                wallet=payload.wallet,
                metrics=metrics.model_dump(),
                intelligence=intelligence.model_dump(),
                social=social.model_dump() if social else None,
            )
        _emit(
            on_event,
            'step_completed',
            {'step': 'bedrock_analysis', 'model': settings.bedrock_model_id},
        )
    except Exception as exc:
        _emit(
            on_event,
            'error',
            {'step': 'bedrock_analysis', 'status_code': 502, 'detail': f'Bedrock request failed: {exc}'},
        )
        raise HTTPException(status_code=502, detail=f'Bedrock request failed: {exc}') from exc

    response = WalletReportResponse(
        metrics=metrics,
        intelligence=intelligence,
        social=social,
        analysis=analysis,
        model=model,
        trace=trace.as_list(),
    )
    try:
        send_wallet_trace_log(
            wallet=payload.wallet,
            trace=response.trace,
            metrics=metrics.model_dump(),
            social_count=social.total_results if social else 0,
        )
    except Exception:
        pass
    _emit(
        on_event,
        'completed',
        {'response': response.model_dump(mode='json')},
    )
    return response


@app.post('/v1/wallet/report', response_model=WalletReportResponse)
def wallet_report(payload: WalletReportRequest) -> WalletReportResponse:
    return _build_wallet_report(payload)


def _format_sse(event: str, data: dict) -> str:
    return f'event: {event}\ndata: {json.dumps(data, separators=(",", ":"))}\n\n'


@app.post('/v1/wallet/report/stream')
def wallet_report_stream(payload: WalletReportRequest) -> StreamingResponse:
    request_id = str(uuid4())

    def event_stream() -> Generator[str, None, None]:
        queue: Queue[dict | None] = Queue()

        def on_event(event: str, data: dict | None) -> None:
            queue.put({'event': event, 'data': data or {}})

        def worker() -> None:
            try:
                _build_wallet_report(payload, on_event=on_event)
            except HTTPException as exc:
                on_event('error', {'status_code': exc.status_code, 'detail': exc.detail})
            except Exception as exc:
                on_event('error', {'status_code': 500, 'detail': str(exc)})
            finally:
                queue.put(None)

        Thread(target=worker, daemon=True).start()

        while True:
            item = queue.get()
            if item is None:
                break
            frame = {'request_id': request_id, **item['data']}
            yield _format_sse(item['event'], frame)

    return StreamingResponse(
        event_stream(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )
