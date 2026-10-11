"""Offline browser rehearsal of portfolio edits and their decision receipts."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.verify_receipt import verify

WSTETH = "token:ethereum:0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8501")
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright, expect
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".playwright-mcp/browsers"))
    report = {"verified_at": datetime.now(timezone.utc).isoformat(), "offline": True,
              "interactions": [], "external_requests": [], "js_errors": []}
    code = sorted((ROOT / "blast_radius").rglob("*.py")) + sorted((ROOT / "app").rglob("*.py"))
    code += sorted((ROOT / "app/components/terminal").glob("*"))
    report["source_sha256"] = {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_text(encoding="utf-8").encode()).hexdigest()
                               for p in code if p.is_file()}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1500, "height": 1100}, accept_downloads=True)

        def intercept(route):
            if route.request.url.startswith(args.url):
                route.continue_()
            else:
                report["external_requests"].append(route.request.url)
                route.abort()

        context.route("**/*", intercept)
        page = context.new_page()
        page.set_default_timeout(30000)
        page.on("pageerror", lambda error: report["js_errors"].append(str(error)))

        def checked(name):
            assert not page.locator('[data-testid="stException"]').count()
            assert not report["js_errors"], report["js_errors"]
            report["interactions"].append(name)
            print("PASS", name, flush=True)

        def edit(allocations):
            if not page.locator(".challenge").get_attribute("open") == "":
                page.locator(".challenge summary").click()
            existing = page.locator("[data-remove]").evaluate_all("buttons => buttons.map(b => b.dataset.remove)")
            for pid in existing:
                if pid not in allocations:
                    page.locator(f'[data-remove="{pid}"]').click()
            for pid in allocations:
                if not page.locator(f'[data-size="{pid}"]').count():
                    page.locator("#catalog-instrument").select_option(pid)
                    page.get_by_role("button", name="Add instrument", exact=True).click()
            for field in page.locator("[data-size]").all():
                field.fill(str(allocations.get(field.get_attribute("data-size"), 0)))
            page.get_by_role("button", name="APPLY PORTFOLIO & REDISCOVER").click()
            page.get_by_role("button", name="FIND MY WEAKEST POINT").wait_for()
            expect(page.get_by_role("region", name="Rescue comparison")).to_have_count(0)
            expect(page.locator(".challenge summary")).to_contain_text("Judge allocation active")

        def rescue():
            page.get_by_role("button", name="FIND MY WEAKEST POINT").click()
            page.locator("#dependency").wait_for()
            page.locator("#dependency").select_option(WSTETH)
            expect(page.locator("#dependency")).to_have_value(WSTETH)
            if page.locator("#severity").input_value() != "100":
                page.locator("#severity").fill("100")
                page.locator("#severity").dispatch_event("change")
                expect(page.locator("#severity")).to_have_value("100")
            page.get_by_role("button", name="SIMULATE FAILURE").click()
            page.get_by_role("button", name="BUILD RESCUE PLAN").click()
            page.get_by_role("region", name="Rescue comparison").wait_for()

        def download(name):
            page.get_by_role("button", name="Show Me the Evidence").click()
            with page.expect_download() as result:
                page.get_by_role("button", name="Download decision receipt").click()
            path = ROOT / f"artifacts/browser_challenge_{name}_receipt.json"
            result.value.save_as(str(path))
            verify(path)
            return json.loads(path.read_text(encoding="utf-8"))

        page.goto(args.url)
        page.get_by_role("button", name="FIND MY WEAKEST POINT").wait_for(timeout=60000)
        allocations = {"pt-wsteth": 750_000, "steakhouse-eth": 500_000, "steakhouse-usdt": 1_250_000, "pt-susde": 1_000_000}
        edit(allocations)
        expect(page.get_by_role("region", name="Portfolio financial metrics")).to_contain_text("$3,500,000")
        expect(page.get_by_role("region", name="Portfolio financial metrics")).to_contain_text("4 positions")
        page.locator(".challenge summary").click()
        page.screenshot(path=str(ROOT / "artifacts/screenshots/FireDrill_challenge.png"))
        page.locator(".challenge summary").click()
        rescue()
        expect(page.locator(".status")).to_contain_text("OPTIMAL")
        rec = download("resized")
        assert rec["scenario"]["aum_usd"] == 3_500_000
        assert len(rec["portfolio"]) == 4
        assert len(rec["exit_candidates"]["options"]["pt-wsteth"]) == 16
        assert rec["plan"]["target_met"]
        checked("Resized four-position book rediscovers, stresses, rescues and reproduces its own receipt")
        # Remove the current selected dependency entirely. No stale plan or id.
        edit({"pt-susde": 500_000})
        page.get_by_role("button", name="FIND MY WEAKEST POINT").click()
        page.locator("#dependency").wait_for()
        assert page.locator("#dependency").input_value() != WSTETH
        assert page.locator(f'option[value="{WSTETH}"]').count() == 0
        expect(page.get_by_role("region", name="Portfolio financial metrics")).to_contain_text("1 positions")
        page.get_by_role("button", name="SIMULATE FAILURE").click()
        page.get_by_role("button", name="BUILD RESCUE PLAN").click()
        expect(page.locator(".status")).to_contain_text("OPTIMAL")
        page.locator("#severity").fill("0")
        page.locator("#severity").dispatch_event("change")
        expect(page.locator("#loss-counter")).to_have_attribute("data-target", "0")
        expect(page.get_by_role("region", name="Rescue comparison")).to_have_count(0)
        checked("Removing the selected dependency leaves a valid singleton book; zero shock clears the rescue")
        edit({"pt-wsteth": 2_000_000, "steakhouse-eth": 500_000, "pt-susde": 1_000_000})
        rescue()
        expect(page.locator(".status")).to_contain_text("TARGET INFEASIBLE")
        rec = download("quote_bound")
        assert rec["plan"]["minimum_attainable_proved"]
        options = rec["exit_candidates"]["options"]["pt-wsteth"]
        assert max(o["notional_usd"] for o in options) == 1_000_000
        assert max(o["fraction"] for o in options) == .5
        checked("A $2M PT holding cannot borrow unsupported quotes to meet the $500k target")
        page.locator(".challenge summary").click()
        for field in page.locator("[data-size]").all():
            field.fill("0")
        page.get_by_role("button", name="APPLY PORTFOLIO & REDISCOVER").click()
        expect(page.locator("#challenge-error")).to_contain_text("Keep at least one position")
        expect(page.get_by_role("region", name="Rescue comparison")).to_be_visible()
        checked("Empty-book validation preserves the last valid decision")
        page.get_by_role("button", name="Reset", exact=True).click()
        page.get_by_role("button", name="FIND MY WEAKEST POINT").wait_for()
        expect(page.get_by_role("region", name="Portfolio financial metrics")).to_contain_text("$10,000,000")
        rescue()
        expect(page.get_by_role("region", name="Rescue comparison")).to_contain_text("$499,000")
        expect(page.get_by_role("region", name="Rescue comparison")).to_contain_text("$2,682,047")
        checked("Reset restores the original audited $10M demonstration and rescue")
        page.goto(args.url + "/?fallback=1")
        page.get_by_role("heading", name="Blast Radius — Break My Portfolio").wait_for()
        page.get_by_text("Challenge this portfolio", exact=True).click()
        field = page.get_by_role("spinbutton", name="Pendle PT-wstETH · 2027-12-30", exact=True)
        field.fill("750000")
        page.get_by_role("button", name="Apply portfolio & rediscover").click()
        expect(page.get_by_text("$9,750,000", exact=True)).to_be_visible(timeout=15000)
        page.get_by_role("button", name="Find My Weakest Point", exact=True).click()
        page.get_by_role("button", name="BUILD RESCUE PLAN").click()
        expect(page.locator('[data-testid="stJson"]').first).to_contain_text("optimal")
        checked("Native fallback also recomputes a resized portfolio")
        context.close()
        browser.close()
    assert not report["external_requests"], report["external_requests"]
    report["status"] = "passed"
    (ROOT / "artifacts/challenge_browser_verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("PASS entire portfolio challenge; no external requests", flush=True)


if __name__ == "__main__":
    main()
