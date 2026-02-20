# recon

`recon` is a backend-first wallet intelligence api for solana.

## what it does now
- accepts a wallet address
- pulls recent signatures + parsed transactions from solana rpc
- computes quick metrics (`fees`, `flow`, `volume`, `counterparties`, `active days`)
- builds deep intelligence (`likely funders`, `funded wallets`, `linked wallets`, `program usage`)
- optionally searches x for social mentions tied to wallet/links
- sends research context to claude on amazon bedrock for narrative analysis
- captures pipeline trace timings and optionally ships run logs to datadog

## api
- `GET /health`
- `POST /v1/wallet/report`
- `POST /v1/wallet/report/stream` (SSE progress stream)

request example:

```json
{
  "wallet": "8NfY...replace_with_real_wallet...A9",
  "max_signatures": 120
}
```

## setup

```bash
uv venv
source .venv/bin/activate
uv sync
cp .env.example .env
```

set aws credentials in your shell (temporary session creds are fine):

```bash
export AWS_REGION="us-west-2"
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_SESSION_TOKEN="..."
```

for solana rpc, a private provider url is strongly recommended to avoid public rpc rate limits:

```bash
export SOLANA_RPC_URL="https://<your-provider-endpoint>"
```

optional integrations:

```bash
export AWS_BEARER_TOKEN_BEDROCK="bedrock-api-key-..."
export X_BEARER_TOKEN="AAAAAAAA...<x app bearer>"
export RECON_ENABLE_X_SEARCH=true
export DD_API_KEY="..."
export DD_SITE="datadoghq.com"
export DD_TRACE_ENABLED=true
export DD_TRACE_AGENT_URL="http://127.0.0.1:8126"
```

x api notes:
- use an x api v2 app bearer token from `console.x.com`
- store only the raw token value (do not prepend `Bearer `)
- if your x project/app does not have recent search access yet, x search will return auth errors and recon will continue without social enrichment

bedrock auth supports either `BEDROCK_API_KEY` or `AWS_BEARER_TOKEN_BEDROCK`.

## env reference

required for full run:
- `AWS_REGION`: bedrock region (default `us-west-2`)
- `BEDROCK_MODEL_ID`: model id or inference profile id
- `SOLANA_RPC_URL`: rpc endpoint (helius/private rpc recommended)

aws auth (choose one path):
- `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` + `AWS_SESSION_TOKEN`
- `BEDROCK_API_KEY` (or alias `AWS_BEARER_TOKEN_BEDROCK`)

core behavior:
- `SOLANA_SIGNATURE_LIMIT`: default signatures to inspect when request omits `max_signatures`
- `RECON_TIMEOUT_SECONDS`: timeout for rpc/x/http calls
- `RECON_METRICS_ONLY`: if `true`, skips bedrock analysis

x enrichment:
- `RECON_ENABLE_X_SEARCH`: enable/disable x search stage
- `X_BEARER_TOKEN`: x api v2 app bearer token
- `X_MAX_RESULTS`: max tweets to return

datadog:
- `DD_API_KEY`: required for log shipping to datadog
- `DD_SITE`: datadog site, e.g. `datadoghq.com`
- `DD_SERVICE`: service name tag
- `DD_ENV`: environment tag
- `DD_VERSION`: version tag
- `DD_SEND_LOGS`: enable/disable agentless logs intake
- `DD_TRACE_ENABLED`: enable/disable ddtrace spans
- `DD_TRACE_AGENT_URL`: apm agent url (default `http://127.0.0.1:8126`)

run the api:

```bash
uv run uvicorn src.recon_api.main:app --reload --port 8080
```

for best datadog coverage:
- run a local datadog agent with apm enabled on `127.0.0.1:8126`
- keep `DD_TRACE_ENABLED=true` for spans (`solana_research`, `x_search`, `bedrock_analysis`)
- keep `DD_SEND_LOGS=true` so each wallet run is also shipped to datadog logs

test:

```bash
curl -s http://127.0.0.1:8080/health

curl -s http://127.0.0.1:8080/v1/wallet/report \
  -H 'content-type: application/json' \
  -d '{"wallet":"<SOLANA_WALLET_ADDRESS>","max_signatures":20}'

# stream progress in real time (server-sent events)
curl -N http://127.0.0.1:8080/v1/wallet/report/stream \
  -H 'content-type: application/json' \
  -d '{"wallet":"<SOLANA_WALLET_ADDRESS>","max_signatures":20}'
```

local development testing docs: `docs/local-dev.md`
