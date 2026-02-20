# x api quick fix

if `x_search` fails with `401 unauthorized`, the issue is your x app token, not recon code.

## 1) set a fresh bearer token

```bash
export X_BEARER_TOKEN='PASTE_NEW_X_BEARER_TOKEN_HERE'
export RECON_ENABLE_X_SEARCH=true
```

notes:
- paste raw token only
- do not include `Bearer `
- avoid stray characters from terminal paste (`^[E`, extra spaces/newlines)

## 2) verify x directly before running recon

```bash
curl -i "https://api.x.com/2/tweets/search/recent?query=solana&max_results=10" \
  -H "Authorization: Bearer $X_BEARER_TOKEN"
```

expected:
- `HTTP/2 200` => token works, recon x stage should work
- `HTTP/2 401` => invalid/revoked/wrong token/app
- `HTTP/2 403` => token valid but app/plan lacks endpoint access

## 3) optional fallback for demo (keep pipeline green)

```bash
export RECON_ENABLE_X_SEARCH=false
```

this disables x enrichment and allows solana + bedrock + datadog flow to complete.
