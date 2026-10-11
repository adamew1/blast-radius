"""Independent integer/Decimal audit of native-live-v2 receipt normalization.

Imports no application code. Original provider responses are left intact; a
separate normalized view is returned for independent financial reconstruction.
"""
import copy
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

D = lambda value: Decimal(str(value))


def objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def integer(value):
    assert not isinstance(value, bool) and isinstance(value, (int, str)) and str(value).isdecimal()
    return int(value)


def audited_view(rec):
    assert rec['receipt_schema'] == 'blast-radius-native-live-v2'
    payload = {k: v for k, v in rec.items() if k != 'receipt_sha256'}
    assert hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest() == rec['receipt_sha256']
    ledger = rec['normalization']
    for observation in rec['observations']:
        assert hashlib.sha256(json.dumps(observation['request'], sort_keys=True, separators=(',', ':')).encode()).hexdigest() == observation['key']
    originals = {o['key']: o['response'] for o in rec['observations'] if 'response' in o}
    for address, mark in ledger['prices'].items():
        assert mark['address'] == address and type(mark['decimals']) is int and 0 <= mark['decimals'] <= 36
        assert D(mark['usd']).is_finite() and D(mark['usd']) > 0
        matches = [a for a in objects(originals[mark['observation_key']])
                   if a.get('address', '').lower() == address and 'price' in a and a['price']]
        assert any(a['decimals'] == mark['decimals'] and D(a['price']['usd']) == D(mark['usd'])
                   and float(a['price']['timestamp']) == mark['timestamp'] for a in matches), address

    def usd(amount, address):
        mark = ledger['prices'][address.lower()]
        return D(integer(amount)) * D(mark['usd']) / D(10) ** mark['decimals']

    def close(a, b):
        # Only floating serialization error; not the production balance tolerance.
        assert abs(D(a) - D(b)) <= max(D('.000001'), abs(D(a))*D('1e-14')), (a, b)

    for address, report in ledger['vaults'].items():
        vault = originals[report['observation_key']]['data']['vaultByAddress']
        state, asset = vault['state'], vault['asset']['address'].lower()
        assert vault['address'].lower() == address and report['asset'] == asset
        total = integer(state['totalAssets'])
        funded = sum(integer(a['supplyAssets']) for a in state['allocation'])
        count = sum(integer(a['supplyAssets']) > 0 for a in state['allocation'])
        assert abs(total-funded) <= max(1, count)
        assert str(total) == report['native_total'] and str(funded) == report['native_funded']
        assert state['totalAssetsUsd'] == report['reported_total_usd']
        close(usd(total, asset), report['normalized_total_usd'])
        assert len(report['allocations']) == len(state['allocation'])
        for allocation in state['allocation']:
            recorded = report['allocations'][allocation['market']['marketId']]
            assert str(integer(allocation['supplyAssets'])) == recorded['native_claim']
            assert allocation['supplyAssetsUsd'] == recorded['reported_usd']
            if integer(allocation['supplyAssets']):
                assert allocation['market']['loanAsset']['address'].lower() == asset
                assert integer(allocation['supplyAssets']) <= integer(allocation['market']['state']['supplyAssets'])

    for mid, report in ledger['markets'].items():
        market = next(m for m in objects(originals[report['observation_key']]) if m.get('marketId') == mid)
        state, loan = market['state'], market['loanAsset']['address'].lower()
        supply, debt, liquidity = [integer(state[k]) for k in ('supplyAssets', 'borrowAssets', 'liquidityAssets')]
        assert debt <= supply and abs(supply-debt-liquidity) <= 1
        assert loan == report['loan_asset']
        for name, amount in (('supply', supply), ('debt', debt), ('liquidity', liquidity)):
            assert str(amount) == report['native_'+name]
        for name in ('supplyAssets', 'borrowAssets', 'liquidityAssets'):
            close(usd(state[name], loan), report['normalized_usd'][name+'Usd'])
        if market.get('collateralAsset'):
            collateral = market['collateralAsset']['address'].lower()
            assert report['collateral_asset'] == collateral
            assert report['native_collateral'] == str(integer(state['collateralAssets']))
            close(usd(state['collateralAssets'], collateral), report['normalized_usd']['collateralAssetsUsd'])
        assert {k: state.get(k) for k in report['reported_usd']} == report['reported_usd']

    # Independently construct the view expected by the established Decimal audit.
    view = copy.deepcopy(rec)
    for observation in view['observations']:
        for item in objects(observation.get('response')):
            if item.get('marketId') in ledger['markets'] and 'state' in item:
                s = item['state']
                loan = item['loanAsset']['address']
                for name in ('supplyAssets', 'borrowAssets', 'liquidityAssets'):
                    s[name+'Usd'] = str(usd(s[name], loan))
                if item.get('collateralAsset'):
                    s['collateralAssetsUsd'] = str(usd(s['collateralAssets'], item['collateralAsset']['address']))
            if 'totalAssets' in item and 'allocation' in item:
                vault = observation['response']['data']['vaultByAddress']
                loan = vault['asset']['address']
                item['totalAssetsUsd'] = str(usd(item['totalAssets'], loan))
                for allocation in item['allocation']:
                    allocation['supplyAssetsUsd'] = str(usd(allocation['supplyAssets'], loan))
    status = (rec.get('analysis') or {}).get('freshness', rec['freshness_at_capture'])
    assert status['risk_usable']
    decision = datetime.fromisoformat(status['checked_at']).timestamp()
    risk_times = [c['observed_at'] for c in status['checks'] if c['kind'] == 'risk']
    assert all(-rec['policy']['future_tolerance_seconds'] <= decision-t <= rec['policy']['risk_seconds'] for t in risk_times)
    assert max(risk_times)-min(risk_times) <= rec['policy']['max_skew_seconds']
    for mark in ledger['prices'].values():
        check = next(c for c in status['checks'] if c['label'] == 'Morpho risk-token price '+mark['address'])
        assert check['observed_at'] == mark['timestamp'] and check['status'] == 'fresh'
        assert check['max_age_seconds'] == rec['policy']['risk_seconds']
    return view


if __name__ == '__main__':
    for arg in sys.argv[1:]:
        rec = json.loads(Path(arg).read_text(encoding='utf-8'))
        audited_view(rec)
        print(json.dumps({'receipt': arg, 'status': 'PASS', 'vaults': len(rec['normalization']['vaults']),
                          'markets': len(rec['normalization']['markets']), 'prices': len(rec['normalization']['prices']),
                          'method': 'Independent native integer balances, Decimal marks and raw HTTP source reconciliation'}))
