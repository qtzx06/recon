import json

import boto3
import httpx

from .settings import settings


SYSTEM_PROMPT = (
    'You are a Solana wallet intelligence analyst. '
    'Given wallet metrics, linkage intelligence, and optional social context, infer behavior, risk profile, and actionable conclusions. '
    'Be concise, specific, and avoid hallucinating unavailable data. '
    'When mentioning timing/recency, use exact values from intelligence.first_seen_at and intelligence.last_seen_at; do not invent dates or years. '
    'Use sections: Summary, Wallet Graph, Behavior, Risk Flags, Actionable Next Steps.'
)


def _invoke_bedrock_boto3(body: dict) -> dict:
    client = boto3.client(
        'bedrock-runtime',
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        aws_session_token=settings.aws_session_token,
    )
    response = client.invoke_model(
        modelId=settings.bedrock_model_id,
        contentType='application/json',
        accept='application/json',
        body=json.dumps(body),
    )
    return json.loads(response['body'].read())


def _should_fallback_to_boto3(response: httpx.Response) -> bool:
    if response.status_code < 400:
        return False
    try:
        text = response.text
    except Exception:
        text = ''
    markers = (
        'AccessDeniedException',
        'CallWithBearerToken',
        'not authorized',
    )
    return any(marker in text for marker in markers)


def _has_aws_creds() -> bool:
    return bool(settings.aws_access_key_id and settings.aws_secret_access_key)


def analyze_wallet_with_bedrock(
    wallet: str, metrics: dict, intelligence: dict, social: dict | None = None
) -> tuple[str, str]:
    user_prompt = {
        'wallet': wallet,
        'metrics': metrics,
        'intelligence': intelligence,
        'social': social,
        'instructions': [
            'Infer likely strategy type (sniper, swing, passive, etc.)',
            'Assess whether this wallet is worth monitoring for alpha signals',
            'Call out likely funder ties and notable linked wallets from the data only',
            'If social data exists, summarize signal quality and potential identity clues',
            'List 2-4 concrete next checks a trader should run',
            'If you mention wallet age or recency, cite first_seen_at/last_seen_at directly from the input data',
        ],
    }

    body = {
        'anthropic_version': 'bedrock-2023-05-31',
        'max_tokens': 700,
        'temperature': 0.2,
        'system': SYSTEM_PROMPT,
        'messages': [
            {
                'role': 'user',
                'content': [{'type': 'text', 'text': json.dumps(user_prompt)}],
            }
        ],
    }

    # Prefer normal AWS credential auth when available; bearer-token auth
    # often lacks bedrock:CallWithBearerToken permission in workshop roles.
    if _has_aws_creds():
        payload = _invoke_bedrock_boto3(body)
    elif settings.bedrock_api_key:
        endpoint = (
            f'https://bedrock-runtime.{settings.aws_region}.amazonaws.com/'
            f'model/{settings.bedrock_model_id}/invoke'
        )
        headers = {
            'Authorization': f'Bearer {settings.bedrock_api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        with httpx.Client(timeout=60) as client:
            response = client.post(endpoint, headers=headers, content=json.dumps(body))
            if _should_fallback_to_boto3(response):
                payload = _invoke_bedrock_boto3(body)
            else:
                response.raise_for_status()
                payload = response.json()
    else:
        payload = _invoke_bedrock_boto3(body)

    text = ''.join(chunk.get('text', '') for chunk in payload.get('content', []))
    return text.strip(), settings.bedrock_model_id
