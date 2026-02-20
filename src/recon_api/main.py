from fastapi import FastAPI, HTTPException
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
from .x_client import search_x_mentions

app = FastAPI(title='recon API', version='0.1.0')


def _looks_like_solana_wallet(value: str) -> bool:
    if len(value) < 32 or len(value) > 44:
        return False
    allowed = set('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz')
    return all(ch in allowed for ch in value)


@app.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}


@app.post('/v1/wallet/report', response_model=WalletReportResponse)
def wallet_report(payload: WalletReportRequest) -> WalletReportResponse:
    if not _looks_like_solana_wallet(payload.wallet):
        raise HTTPException(status_code=400, detail='Invalid Solana wallet format')

    max_signatures = payload.max_signatures or settings.solana_signature_limit
    trace = TraceCollector()

    try:
        with trace.step('solana_research', detail=f'max_signatures={max_signatures}'):
            metrics_dict, intelligence_dict = collect_wallet_report_data(
                rpc_url=settings.solana_rpc_url,
                wallet=payload.wallet,
                max_signatures=max_signatures,
                timeout_s=settings.recon_timeout_seconds,
            )
        metrics = WalletMetrics.model_validate(metrics_dict)
        intelligence = WalletIntelligence.model_validate(intelligence_dict)
    except SolanaRateLimitError as exc:
        raise HTTPException(
            status_code=503,
            detail='Solana RPC rate limited. Use a private RPC URL in SOLANA_RPC_URL and retry.',
        ) from exc
    except (SolanaRPCError, ValidationError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f'Failed to build wallet metrics: {exc}') from exc

    social: SocialIntel | None = None
    if settings.recon_enable_x_search and settings.x_bearer_token:
        try:
            funders = [w.wallet for w in intelligence.likely_funders[:2]]
            funded = [w.wallet for w in intelligence.likely_funded_wallets[:2]]
            query_terms = [payload.wallet, *funders, *funded]
            with trace.step('x_search', detail=f'terms={len(query_terms)}'):
                social = search_x_mentions(
                    bearer_token=settings.x_bearer_token,
                    query_terms=query_terms,
                    timeout_s=settings.recon_timeout_seconds,
                    max_results=settings.x_max_results,
                )
        except Exception:
            social = SocialIntel(query_terms=[], total_results=0, mentions=[])

    if settings.recon_metrics_only:
        response = WalletReportResponse(
            metrics=metrics,
            intelligence=intelligence,
            social=social,
            analysis='Metrics-only mode enabled. Bedrock analysis skipped.',
            model=None,
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
        return response

    try:
        with trace.step('bedrock_analysis'):
            analysis, model = analyze_wallet_with_bedrock(
                wallet=payload.wallet,
                metrics=metrics.model_dump(),
                intelligence=intelligence.model_dump(),
                social=social.model_dump() if social else None,
            )
    except Exception as exc:
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
    return response
