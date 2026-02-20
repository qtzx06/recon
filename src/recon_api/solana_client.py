from collections import Counter
from datetime import UTC, datetime
import time
from typing import Any

import httpx

LAMPORTS_PER_SOL = 1_000_000_000
KNOWN_ADDRESS_LABELS: dict[str, tuple[str, str]] = {
    'jitodontfront31111111TradeWithAxiomDotTrade': ('Axiom anti-front-run program', 'axiom'),
    'FLASHX8DrLbgeR8FcfNV1F5krxYcYMUdBkrP1EPBtxB9': ('Axiom execution/flash program', 'axiom'),
    '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P': ('Pump.fun program', 'pumpfun'),
}


class SolanaRPCError(RuntimeError):
    pass


class SolanaRateLimitError(SolanaRPCError):
    pass


def _rpc(client: httpx.Client, url: str, method: str, params: list[Any]) -> Any:
    payload = {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            if data.get('error'):
                raise SolanaRPCError(str(data['error']))
            return data.get('result')
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                last_error = exc
                if attempt < 3:
                    time.sleep(0.6 * (attempt + 1))
                    continue
                raise SolanaRateLimitError('Solana RPC rate limited (HTTP 429)') from exc
            raise SolanaRPCError(f'Solana RPC HTTP error: {exc.response.status_code}') from exc
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(0.4 * (attempt + 1))
                continue
            raise SolanaRPCError(f'Solana RPC transport error: {exc}') from exc
    raise SolanaRPCError(f'Solana RPC failed: {last_error}')


def _rpc_get_transactions_batch(
    client: httpx.Client, url: str, signatures: list[str], batch_size: int = 12
) -> dict[str, dict[str, Any] | None]:
    results: dict[str, dict[str, Any] | None] = {}
    if not signatures:
        return results

    for i in range(0, len(signatures), batch_size):
        chunk = signatures[i : i + batch_size]
        payload = [
            {
                'jsonrpc': '2.0',
                'id': idx,
                'method': 'getTransaction',
                'params': [sig, {'encoding': 'jsonParsed', 'maxSupportedTransactionVersion': 0}],
            }
            for idx, sig in enumerate(chunk, start=1)
        ]

        last_error: Exception | None = None
        for attempt in range(4):
            try:
                response = client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, list):
                    raise SolanaRPCError('Unexpected batch response format')
                for item, sig in zip(data, chunk, strict=False):
                    if isinstance(item, dict) and item.get('error'):
                        raise SolanaRPCError(str(item['error']))
                    results[sig] = item.get('result') if isinstance(item, dict) else None
                break
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (401, 403, 405, 415):
                    # Some providers/plans do not accept JSON-RPC batch payloads.
                    for sig in chunk:
                        results[sig] = _rpc(
                            client,
                            url,
                            'getTransaction',
                            [sig, {'encoding': 'jsonParsed', 'maxSupportedTransactionVersion': 0}],
                        )
                        time.sleep(0.08)
                    break
                if exc.response.status_code == 429:
                    last_error = exc
                    if attempt < 3:
                        time.sleep(0.7 * (attempt + 1))
                        continue
                    raise SolanaRateLimitError('Solana RPC rate limited (HTTP 429)') from exc
                raise SolanaRPCError(f'Solana RPC HTTP error: {exc.response.status_code}') from exc
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise SolanaRPCError(f'Solana RPC transport error: {exc}') from exc
        else:
            raise SolanaRPCError(f'Solana batch request failed: {last_error}')

    return results


def _parsed_instructions(tx: dict[str, Any]) -> list[dict[str, Any]]:
    message = tx.get('transaction', {}).get('message', {})
    instructions = message.get('instructions') or []
    parsed = []
    for ix in instructions:
        p = ix.get('parsed')
        if isinstance(p, dict):
            parsed.append(p)
    return parsed


def _program_from_instruction(ix: dict[str, Any]) -> str | None:
    program = ix.get('program')
    if isinstance(program, str):
        return program
    program_id = ix.get('programId')
    if isinstance(program_id, str):
        return program_id
    return None


def _account_keys(tx: dict[str, Any]) -> list[str]:
    keys = tx.get('transaction', {}).get('message', {}).get('accountKeys', [])
    out: list[str] = []
    for key in keys:
        if isinstance(key, str):
            out.append(key)
        elif isinstance(key, dict):
            pubkey = key.get('pubkey')
            if isinstance(pubkey, str):
                out.append(pubkey)
    return out


def collect_wallet_report_data(
    rpc_url: str, wallet: str, max_signatures: int, timeout_s: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    counterparties = Counter()
    linked_wallets = Counter()
    total_fees_lamports = 0
    inbound_lamports = 0
    outbound_lamports = 0
    active_days = set()
    inbound_by_source = Counter()
    outbound_by_destination = Counter()
    program_usage = Counter()
    first_seen: datetime | None = None
    last_seen: datetime | None = None

    with httpx.Client(timeout=timeout_s) as client:
        signatures = _rpc(
            client,
            rpc_url,
            'getSignaturesForAddress',
            [wallet, {'limit': max_signatures}],
        )
        signature_ids = [sig.get('signature') for sig in signatures if sig.get('signature')]
        transactions = _rpc_get_transactions_batch(client, rpc_url, signature_ids)

        for sig in signatures:
            signature = sig.get('signature')
            block_time = sig.get('blockTime')
            if block_time:
                at = datetime.fromtimestamp(block_time, UTC)
                day = at.date().isoformat()
                active_days.add(day)
                first_seen = at if first_seen is None else min(first_seen, at)
                last_seen = at if last_seen is None else max(last_seen, at)

            if not signature:
                continue

            tx = transactions.get(signature)
            if not tx:
                continue

            fee = tx.get('meta', {}).get('fee') or 0
            total_fees_lamports += int(fee)

            for k in _account_keys(tx):
                if k and k != wallet:
                    linked_wallets[k] += 1

            for parsed in _parsed_instructions(tx):
                program = _program_from_instruction(parsed)
                if program:
                    program_usage[program] += 1
                if parsed.get('type') != 'transfer':
                    continue
                info = parsed.get('info', {})
                source = info.get('source')
                destination = info.get('destination')
                lamports = info.get('lamports')
                if lamports is None:
                    continue
                lamports = int(lamports)

                if source == wallet:
                    outbound_lamports += lamports
                    if destination:
                        counterparties[destination] += 1
                        outbound_by_destination[destination] += lamports
                elif destination == wallet:
                    inbound_lamports += lamports
                    if source:
                        counterparties[source] += 1
                        inbound_by_source[source] += lamports

    top_counterparties = [
        {'wallet': cp, 'transfers': count}
        for cp, count in counterparties.most_common(8)
    ]

    total_fees_sol = total_fees_lamports / LAMPORTS_PER_SOL
    inbound_sol = inbound_lamports / LAMPORTS_PER_SOL
    outbound_sol = outbound_lamports / LAMPORTS_PER_SOL

    metrics = {
        'wallet': wallet,
        'signature_count': len(signatures),
        'total_fees_sol': round(total_fees_sol, 6),
        'inbound_sol': round(inbound_sol, 6),
        'outbound_sol': round(outbound_sol, 6),
        'transfer_volume_sol': round(inbound_sol + outbound_sol, 6),
        'net_flow_sol': round(inbound_sol - outbound_sol, 6),
        'active_days': len(active_days),
        'top_counterparties': top_counterparties,
    }
    intelligence = {
        'first_seen_at': first_seen.isoformat() if first_seen else None,
        'last_seen_at': last_seen.isoformat() if last_seen else None,
        'unique_counterparties': len(counterparties),
        'likely_funders': [
            {
                'wallet': w,
                'total_sol': round(l / LAMPORTS_PER_SOL, 6),
                'transfers': counterparties[w],
            }
            for w, l in inbound_by_source.most_common(10)
        ],
        'likely_funded_wallets': [
            {
                'wallet': w,
                'total_sol': round(l / LAMPORTS_PER_SOL, 6),
                'transfers': counterparties[w],
            }
            for w, l in outbound_by_destination.most_common(10)
        ],
        'frequent_programs': [
            {'program': p, 'interactions': c}
            for p, c in program_usage.most_common(10)
        ],
        'linked_wallets': [w for w, _ in linked_wallets.most_common(20)],
        'known_labels': [],
        'inferred_entities': [],
    }

    # Known label enrichment from linked/program/counterparty addresses.
    candidate_addresses = set(linked_wallets.keys())
    candidate_addresses.update(program_usage.keys())
    candidate_addresses.update(counterparties.keys())
    known_labels = []
    seen_labels = set()
    for address in candidate_addresses:
        meta = KNOWN_ADDRESS_LABELS.get(address)
        if not meta:
            continue
        label, category = meta
        if address in seen_labels:
            continue
        seen_labels.add(address)
        known_labels.append({'address': address, 'label': label, 'category': category})
    intelligence['known_labels'] = known_labels

    # Entity inference heuristics.
    inferred_entities: list[dict[str, Any]] = []
    axm_wallets = {
        w
        for w in candidate_addresses
        if isinstance(w, str) and w.lower().startswith('axm')
    }
    axiom_labels = [l for l in known_labels if l['category'] == 'axiom']
    if axm_wallets or axiom_labels:
        evidence = [*sorted(list(axm_wallets))[:4], *[l['address'] for l in axiom_labels][:3]]
        evidence = list(dict.fromkeys(evidence))
        signal_count = len(axm_wallets) + len(axiom_labels)
        confidence = 'high' if signal_count >= 3 else 'medium'
        inferred_entities.append(
            {
                'entity': 'Axiom-linked trading cluster',
                'confidence': confidence,
                'reason': 'Detected Axiom-associated addresses/programs and/or axm vanity-linked wallets.',
                'evidence': evidence,
            }
        )

    pump_labels = [l for l in known_labels if l['category'] == 'pumpfun']
    if pump_labels:
        inferred_entities.append(
            {
                'entity': 'Pump.fun ecosystem activity',
                'confidence': 'medium',
                'reason': 'Detected known Pump.fun program interaction in linked/program addresses.',
                'evidence': [l['address'] for l in pump_labels[:3]],
            }
        )

    intelligence['inferred_entities'] = inferred_entities
    return metrics, intelligence


def collect_wallet_metrics(rpc_url: str, wallet: str, max_signatures: int, timeout_s: int) -> dict[str, Any]:
    metrics, _ = collect_wallet_report_data(
        rpc_url=rpc_url,
        wallet=wallet,
        max_signatures=max_signatures,
        timeout_s=timeout_s,
    )
    return metrics
