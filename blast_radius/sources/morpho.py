"""Morpho Blue GraphQL client (free, no key; complexity cap 1M). Verified schema.

Schema gotchas (from probe): filter is `listed:true` (not whitelisted); market id is
`marketId` (not uniqueKey); allocations live under `state.allocation`; vault keyed by
`address` (no id). `lltv` is a 1e18 BigInt string.
"""
from __future__ import annotations

from .cache import cached_post

URL = "https://blue-api.morpho.org/graphql"

_VAULT_FIELDS = """
  address name symbol
  asset { symbol address decimals }
  chain { id network }
  state {
    totalAssetsUsd apy netApy fee
    allocation {
      supplyAssetsUsd supplyCapUsd
      market {
        marketId lltv
        loanAsset { symbol address }
        collateralAsset { symbol address }
        oracle { address }
        state { utilization supplyAssetsUsd borrowAssetsUsd liquidityAssetsUsd collateralAssetsUsd }
      }
    }
  }
"""


def vaults(chain_ids=(1,), first: int = 100) -> list[dict]:
    q = (
        """
    query($chainIds:[Int!], $first:Int!){
      vaults(first:$first, where:{chainId_in:$chainIds, listed:true},
             orderBy:TotalAssetsUsd, orderDirection:Desc){
        items { %s }
      }
    }"""
        % _VAULT_FIELDS
    )
    data = cached_post(
        URL,
        {"query": q, "variables": {"chainIds": list(chain_ids), "first": first}},
        label="morpho_vaults",
    )
    return data["data"]["vaults"]["items"]


def vault_by_address(address: str, chain_id: int = 1) -> dict:
    q = (
        """
    query($address:String!, $chainId:Int!){
      vaultByAddress(address:$address, chainId:$chainId){ %s }
    }"""
        % _VAULT_FIELDS
    )
    data = cached_post(
        URL,
        {"query": q, "variables": {"address": address, "chainId": chain_id}},
        label=f"morpho_vault:{address}",
    )
    return data["data"]["vaultByAddress"]


def vault_history(address: str, chain_id: int, start: int, end: int, interval: str = "DAY") -> dict:
    """Historical share price / TVL for the replay (VaultHistory timeseries)."""
    q = """
    query($address:String!, $chainId:Int!, $opt:TimeseriesOptions){
      vaultByAddress(address:$address, chainId:$chainId){
        name
        historicalState {
          sharePriceUsd(options:$opt){ x y }
          totalAssetsUsd(options:$opt){ x y }
        }
      }
    }"""
    opt = {"startTimestamp": start, "endTimestamp": end, "interval": interval}
    data = cached_post(
        URL,
        {"query": q, "variables": {"address": address, "chainId": chain_id, "opt": opt}},
        label=f"morpho_vault_hist:{address}",
    )
    return data["data"]["vaultByAddress"]
