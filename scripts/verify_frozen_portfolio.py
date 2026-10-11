"""Rehearse the Snapshot-only application with the user's five holdings."""
import json
import hashlib
import os
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.verify_receipt import verify


def main():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT/".playwright-mcp/browsers"))
    from playwright.sync_api import sync_playwright, expect
    amounts = {"steakhouse-eth": 100_000, "gauntlet-usdc-prime": 150_000,
               "hakutora-usdc": 150_000, "yearn-og-usdc": 100_000,
               "catalog-pt-0xc5f938a8ef5f3bf9e72f5aa094baf5e03f4727d3": 500_000}
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "js_errors": [],
              "external_browser_requests": [], "api_mocks": False, "portfolio": amounts}
    output = ROOT/"artifacts/live"
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1500, "height": 1100}, accept_downloads=True)

        def route(request):
            if request.request.url.startswith("http://localhost:8501"):
                request.continue_()
            else:
                report["external_browser_requests"].append(request.request.url)
                request.abort()

        context.route("**/*", route)
        page = context.new_page()
        page.set_default_timeout(30000)
        page.on("pageerror", lambda exc: report["js_errors"].append(str(exc)))
        page.goto("http://localhost:8501")
        page.get_by_role("button", name="FIND MY WEAKEST POINT", exact=False).wait_for()
        expect(page.get_by_text("Live Mode", exact=True)).to_have_count(0)
        expect(page.get_by_role("button", name="Fetch fresh data & discover", exact=True)).to_have_count(0)
        page.locator(".challenge summary").click()
        while page.locator("[data-remove]").count():
            page.locator("[data-remove]").first.click()
        for pid, amount in amounts.items():
            page.locator("#catalog-instrument").select_option(pid)
            page.get_by_role("button", name="Add instrument", exact=True).click()
            page.locator(f'[data-size="{pid}"]').fill(str(amount))
        page.get_by_role("button", name="APPLY PORTFOLIO & REDISCOVER", exact=False).click()
        expect(page.get_by_role("region", name="Portfolio financial metrics")).to_contain_text("$1,000,000")
        expect(page.get_by_text("FROZEN EVIDENCE", exact=True)).to_be_visible()
        page.get_by_role("button", name="FIND MY WEAKEST POINT", exact=False).click()
        page.get_by_role("button", name="SIMULATE FAILURE", exact=False).click()
        page.get_by_role("button", name="BUILD RESCUE PLAN", exact=False).click()
        expect(page.get_by_role("region", name="Rescue comparison")).to_be_visible()
        page.get_by_role("button", name="Show Me the Evidence", exact=False).click()
        with page.expect_download() as result:
            page.get_by_role("button", name="Download decision receipt", exact=True).click()
        path = output/"user_frozen_portfolio_receipt.json"
        result.value.save_as(str(path))
        verify(path)
        rec = json.loads(path.read_text(encoding="utf-8"))
        assert {p["id"]: p["size_usd"] for p in rec["portfolio"]} == amounts
        report["receipt_file_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        report["scenario_loss_usd"] = rec["scenario"]["loss_usd"]
        report["accounted_loss_usd"] = rec["plan"]["audit"]["accounted_loss_usd"]
        report["snapshot_only"] = True
        report["status"] = "PASS"
        assert not report["js_errors"] and not page.locator('[data-testid="stException"]').count()
        assert not report["external_browser_requests"]
        page.screenshot(path=str(output/"user_frozen_portfolio.png"), full_page=True)
        browser.close()
    (ROOT/"artifacts/frozen_portfolio_browser_verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("PASS: exact five holdings, $1M, all five stages, receipt replay, no external browser requests or JS errors")


if __name__ == "__main__":
    main()
