# recon

`recon` is a backend-first wallet intelligence API for Solana.

## What it does now
- Accepts a wallet address
- Pulls recent signatures + parsed transactions from Solana RPC
- Computes quick metrics (`fees`, `flow`, `volume`, `counterparties`, `active days`)
- Builds deep intelligence (`likely funders`, `funded wallets`, `linked wallets`, `program usage`)
- Optionally searches X for social mentions tied to wallet/links
- Sends research context to Claude on Amazon Bedrock for narrative analysis
- Captures pipeline trace timings and optionally ships run logs to Datadog

## API
- `GET /health`
- `POST /v1/wallet/report`

Request example:

```json
{
  "wallet": "8NfY...replace_with_real_wallet...A9",
  "max_signatures": 120
}
```

## Setup

```bash
uv venv
source .venv/bin/activate
uv sync
cp .env.example .env
```

Set AWS credentials in your shell (temporary session creds are fine):

```bash
export AWS_DEFAULT_REGION="us-west-2"
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_SESSION_TOKEN="..."
```

For Solana RPC, a private provider URL is strongly recommended to avoid public RPC rate limits:

```bash
export SOLANA_RPC_URL="https://<your-provider-endpoint>"
```

Optional integrations:

```bash
export AWS_BEARER_TOKEN_BEDROCK="bedrock-api-key-..."
export X_BEARER_TOKEN="..."
export RECON_ENABLE_X_SEARCH=true
export DD_API_KEY="..."
export DD_SITE="datadoghq.com"
export DD_TRACE_ENABLED=false
```

Bedrock auth supports either `BEDROCK_API_KEY` or `AWS_BEARER_TOKEN_BEDROCK`.

Run the API:

```bash
uv run uvicorn src.recon_api.main:app --reload --port 8080
```

Test:

```bash
curl -s http://127.0.0.1:8080/health

curl -s http://127.0.0.1:8080/v1/wallet/report \
  -H 'content-type: application/json' \
  -d '{"wallet":"<SOLANA_WALLET_ADDRESS>","max_signatures":20}'
```

## Next steps (frontend)
- Build a Next.js UI that calls `POST /v1/wallet/report`
- Add streaming response + incremental analysis sections
- Add timeline UI for `trace` and graph UI for `intelligence.linked_wallets`
