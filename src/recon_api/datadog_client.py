from datetime import UTC, datetime
from typing import Any

import httpx

from .schemas import TraceStep
from .settings import settings


def send_wallet_trace_log(
    wallet: str,
    trace: list[TraceStep],
    metrics: dict[str, Any],
    social_count: int,
) -> None:
    if not settings.dd_api_key or not settings.dd_send_logs:
        return

    url = f'https://http-intake.logs.{settings.dd_site}/api/v2/logs'
    payload = {
        'ddsource': 'python',
        'service': settings.dd_service,
        'ddtags': f'env:{settings.dd_env},version:{settings.dd_version}',
        'hostname': 'recon-api',
        'timestamp': datetime.now(UTC).isoformat(),
        'message': 'wallet_report_completed',
        'wallet': wallet,
        'trace': [step.model_dump() for step in trace],
        'metrics': metrics,
        'social_results': social_count,
    }
    headers = {'Content-Type': 'application/json', 'DD-API-KEY': settings.dd_api_key}

    with httpx.Client(timeout=settings.recon_timeout_seconds) as client:
        resp = client.post(url, headers=headers, json=[payload])
        resp.raise_for_status()


def datadog_config_summary() -> dict[str, Any]:
    return {
        'dd_send_logs': settings.dd_send_logs,
        'dd_trace_enabled': settings.dd_trace_enabled,
        'dd_site': settings.dd_site,
        'dd_service': settings.dd_service,
        'dd_env': settings.dd_env,
        'dd_version': settings.dd_version,
        'dd_api_key_present': bool(settings.dd_api_key),
    }


def send_test_log(message: str = 'recon_datadog_test_log') -> None:
    if not settings.dd_api_key:
        raise RuntimeError('DD_API_KEY is missing')
    if not settings.dd_send_logs:
        raise RuntimeError('DD_SEND_LOGS is false')

    url = f'https://http-intake.logs.{settings.dd_site}/api/v2/logs'
    payload = {
        'ddsource': 'python',
        'service': settings.dd_service,
        'ddtags': f'env:{settings.dd_env},version:{settings.dd_version},kind:test',
        'hostname': 'recon-api',
        'timestamp': datetime.now(UTC).isoformat(),
        'message': message,
    }
    headers = {'Content-Type': 'application/json', 'DD-API-KEY': settings.dd_api_key}

    with httpx.Client(timeout=settings.recon_timeout_seconds) as client:
        resp = client.post(url, headers=headers, json=[payload])
        resp.raise_for_status()
