"""Cache primary documentation used to extend the scan's manual map."""
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from blast_radius.sources.cache import cached_text

URLS = [
    "https://docs.apyx.fi/technical-overview/protocol-contracts-overview.md",
    "https://apyx-labs.github.io/evm-contracts/",
    "https://docs.infinifi.xyz/dev-docs/contracts.md",
    "https://docs.infinifi.xyz/dev-docs/tokens/staked-token.md",
    "https://docs.infinifi.xyz/risk-disclosures.md",
    "https://docs.re.xyz/products/smart-contracts.md",
    "https://docs.re.xyz/products/about-reusd.md",
    "https://docs.re.xyz/products/about-reusde.md",
    "https://docs.strata.markets/technical-documentation/contracts-details.md",
    "https://docs.strata.markets/markets/ethena-usde/srusde.md",
    "https://docs.3jane.xyz/developers/addresses.md",
    "https://docs.3jane.xyz/usd3-susd3/suppliers.md",
    "https://docs.sierra.money/building-with-sierra/blockchain-addresses.md",
    "https://docs.sierra.money/our-flagship-lvt-sierra/reserve-strategy.md",
    "https://docs.usdd.io/introduction/collateral-asset-contract-addresses.md",
    "https://www.wbtc.network/about",
    "https://docs.originprotocol.com/registry/contracts/oeth-registry.md",
    "https://docs.originprotocol.com/security-and-risk/risk-framework.md",
]

if __name__ == "__main__":
    for url in URLS:
        text = cached_text(url)
        print(url, len(text))
