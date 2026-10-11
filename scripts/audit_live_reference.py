"""Independent Decimal audit of the recorded Hakutora/cbBTC live runs.

Reads embedded HTTP responses; imports no application financial code or solver.
This verifies historical observations, not current freshness or execution.
"""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
D = lambda value: Decimal(str(value))


def close(actual, expected, label):
    assert abs(D(actual) - D(expected)) <= D('.02'), (label, actual, expected)


def seconds(value):
    return float(value) if isinstance(value, (int, float)) else datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()


def audit(path):
    rec = json.loads(path.read_text(encoding='utf-8'))
    payload = {k: v for k, v in rec.items() if k != 'receipt_sha256'}
    assert hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest() == rec['receipt_sha256']
    if rec['receipt_schema'] == 'blast-radius-native-live-v2':
        from scripts.audit_native_live import audited_view
        rec = audited_view(rec)
    assert len(rec['portfolio']) == 1 and rec['portfolio'][0]['id'] == 'hakutora-usdc'
    analysis, position = rec['analysis'], rec['portfolio'][0]
    assert analysis['scenario']['dependency_id'] == 'token:ethereum:0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf'
    assert analysis['scenario']['severity'] == 1 and not analysis['locks']
    assert rec['executable'] is False and analysis['plan']['executable'] is False
    vaults, markets = [], {}
    for observation in rec['observations']:
        assert not observation.get('error') and observation['http_status'] == 200
        request = observation['request']
        assert hashlib.sha256(json.dumps(request, sort_keys=True, separators=(',', ':')).encode()).hexdigest() == observation['key']
        if request['url'] != 'https://blue-api.morpho.org/graphql':
            continue  # Pendle active identities have no financial role in this run.
        data = observation['response']['data']
        if 'vaultByAddress' in data:
            vaults.append(data['vaultByAddress'])
        else:
            markets.update({m['marketId']: m for m in data.values()})
    assert len(vaults) == 1
    vault = vaults[0]
    assert vault['address'].lower() == position['vault'].lower() and vault['chain']['id'] == 1
    state = vault['state']
    total, size = D(state['totalAssetsUsd']), D(position['size_usd'])
    close(sum(D(a['supplyAssetsUsd']) for a in state['allocation']), total, 'allocation reconciliation')
    loss, capacities, claims = D(0), {}, {}
    times = [seconds(state['timestamp'])]
    if 'normalization' in rec:
        times.extend(mark['timestamp'] for mark in rec['normalization']['prices'].values())
    for allocation in state['allocation']:
        claim = D(allocation['supplyAssetsUsd'])
        if not claim:
            continue
        market = markets[allocation['market']['marketId']]
        assert market['loanAsset']['address'].lower() == vault['asset']['address'].lower()
        s = market['state']
        times.append(seconds(s['timestamp']))
        supply, debt, collateral, liquidity = [D(s[k]) for k in ('supplyAssetsUsd', 'borrowAssetsUsd', 'collateralAssetsUsd', 'liquidityAssetsUsd')]
        assert 0 <= debt <= supply and 0 <= claim <= supply
        close(liquidity, supply-debt, 'market liquidity')
        capacities[market['marketId']] = liquidity
        claims[market['marketId']] = min(claim, liquidity)
        assert market['collateralAsset']['address'].lower() == analysis['scenario']['dependency_id'].split(':')[-1]
        impairment = min(D(1), max(D(0), (debt-max(D(0), debt-collateral))/supply))
        loss += size*claim/total*impairment
    decision = analysis['analyzed_at']
    policy = rec['policy']
    assert policy['risk_seconds'] == policy['max_skew_seconds']
    assert policy['risk_seconds'] in ((900, 3600) if 'normalization' in rec else (900,))
    assert all(-policy['future_tolerance_seconds'] <= decision-t <= policy['risk_seconds'] for t in times)
    assert max(times)-min(times) <= policy['max_skew_seconds']
    assert {c['observed_at'] for c in analysis['freshness']['checks']} == set(times)
    close(loss, analysis['scenario']['loss_usd'], 'conditional loss')
    close(size, analysis['scenario']['aum_usd'], 'portfolio value')
    options = []
    for step in range(21):
        fraction, sold = D(step)/20, size*D(step)/20
        if sold > sum(claims.values()):
            continue
        execution, conversion = sold*D('.0002'), sold*D('.001')
        carry = sold*max(D(0), D(state['netApy']))*30/365
        residual, cost = loss*(1-fraction), execution+conversion+carry
        options.append((fraction, sold, residual+execution+conversion, cost, residual, execution, conversion, carry))
    recorded = analysis['exit_candidates']
    assert len(recorded['options'][position['id']]) == len(options)
    for calculated, candidate in zip(options, recorded['options'][position['id']]):
        for index, key in ((0, 'fraction'), (1, 'notional_usd'), (5, 'execution_usd'), (6, 'conversion_usd'), (7, 'carry_usd')):
            close(calculated[index], candidate[key], 'candidate '+key)
    for mid in claims:
        close(claims[mid], recorded['vault_caps'][position['id']][mid], 'funded bound')
        close(capacities[mid], recorded['resources'][mid], 'shared capacity')
    plan = analysis['plan']
    assert plan['status'] == 'optimal' and plan['target_met'] and len(plan['actions']) == 1
    selected = next(o for o in options if o[0] == D(plan['actions'][0]['fraction']))
    eligible = [o for o in options if o[2] <= D(analysis['loss_limit'])]
    close(selected[3], min(o[3] for o in eligible), 'exhaustive least cost')
    fraction, sold, accounted, cost, residual, execution, conversion, carry = selected
    for key, value in {'accounted_loss_usd': accounted, 'protection_cost_usd': cost, 'residual_loss_usd': residual,
                       'execution_usd': execution, 'conversion_usd': conversion, 'carry_usd': carry,
                       'capital_sold_usd': sold, 'capital_released_usd': sold-execution-conversion,
                       'avoided_loss_usd': loss-residual, 'break_even_probability': cost/(loss-residual)}.items():
        close(value, plan['audit'][key], key)
    by_market = {}
    for withdrawal in plan['withdrawals']:
        assert withdrawal['position'] == position['id']
        mid, amount = withdrawal['market'], D(withdrawal['amount_usd'])
        assert mid not in by_market and 0 <= amount <= claims[mid] and amount <= capacities[mid]
        by_market[mid] = amount
    close(sum(by_market.values()), sold, 'withdrawal funding')
    result = {'receipt': path.relative_to(ROOT).as_posix(), 'receipt_sha256': rec['receipt_sha256'],
            'decision_utc': datetime.fromtimestamp(decision, timezone.utc).isoformat(),
            'source_timestamps_utc': [datetime.fromtimestamp(t, timezone.utc).isoformat() for t in times],
            'historical_freshness_passed': True, 'independent_optimality_verified': True,
            'candidates_enumerated': len(options), 'conditional_loss_usd': float(loss),
            'reduction': float(fraction), 'accounted_loss_usd': float(accounted), 'executable': False}
    if 'normalization' in rec:
        strict = all(decision-t <= 900 for t in times) and max(times)-min(times) <= 900
        assert strict == rec['risk_data_status']['strict_15_minute_risk_passed']
        result.update(risk_policy_seconds=policy['risk_seconds'], strict_15_minute_risk_passed=strict,
                      classification=rec['risk_data_status']['classification'])
    return result


if __name__ == '__main__':
    paths = [Path(p) for p in sys.argv[1:]] or [ROOT/'artifacts/certified_live'/name for name in
             ('hakutora_20261011_receipt.json', 'hakutora_release_20261011_receipt.json',
              'hakutora_browser_20261011_receipt.json', 'hakutora_recovery_20261011_receipt.json')]
    results = [audit(p.resolve()) for p in paths]
    report = {'status': 'PASS', 'audited_at': datetime.now(timezone.utc).isoformat(),
              'method': 'Embedded real HTTP responses; separate Decimal calculations and exhaustive 21-candidate enumeration; no product or solver imports',
              'cases': results}
    (ROOT/'artifacts/certified_live/independent_audit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
