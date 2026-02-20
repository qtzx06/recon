# local development testing

use this guide to run local smoke tests against the api.

## prerequisites

1. start the api server:

```bash
uv run uvicorn src.recon_api.main:app --reload --port 8080
```

2. add your local wallet to `.env.local` (this file is gitignored):

```bash
echo 'LOCAL_DEV_WALLET=<your_solana_wallet>' >> .env.local
```

## run local smoke test

```bash
./scripts/local-test.sh
```

optional overrides:

```bash
RECON_BASE_URL=http://127.0.0.1:8080 RECON_MAX_SIGNATURES=20 ./scripts/local-test.sh
```

## troubleshooting

if you get `503`, your rpc endpoint is likely rate-limited. set a private rpc url:

```bash
echo 'SOLANA_RPC_URL=https://<your-private-rpc-endpoint>' >> .env.local
```
