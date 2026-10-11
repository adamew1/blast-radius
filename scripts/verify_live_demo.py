"""Browser rehearsal of the shared live terminal and authentic saved recovery."""
import json
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
    output = ROOT/"artifacts/live"
    output.mkdir(parents=True, exist_ok=True)
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "js_errors": [], "checks": [], "api_mocks": False}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 1100}, accept_downloads=True)
        page.set_default_timeout(45000)
        page.on("pageerror", lambda exc: report["js_errors"].append(str(exc)))

        def checked(name):
            assert not page.locator('[data-testid="stException"]').count(), page.locator('[data-testid="stException"]').all_text_contents()
            assert not report["js_errors"], report["js_errors"]
            report["checks"].append(name)
            print("PASS", name, flush=True)

        def workflow(name):
            page.get_by_role("button", name="FIND MY WEAKEST POINT", exact=False).click()
            page.get_by_role("button", name="SIMULATE FAILURE", exact=False).click()
            page.get_by_role("button", name="BUILD RESCUE PLAN", exact=False).click()
            expect(page.get_by_role("region", name="Rescue comparison")).to_contain_text("REDUCE Hakutora USDC 45%")
            page.get_by_role("button", name="Show Me the Evidence", exact=False).click()
            expect(page.get_by_text("Protection:", exact=True)).to_be_visible()
            with page.expect_download() as download:
                page.get_by_role("button", name="Download live observation receipt").click()
            path = output/(name+"_receipt.json")
            download.value.save_as(str(path))
            verify(path)
            rec = json.loads(path.read_text())
            report[name] = {"receipt_sha256": rec["receipt_sha256"], "classification": rec["classification"],
                            "presentation_context": rec.get("presentation_context"),
                            "freshness": rec["analysis"]["freshness"], "loss_usd": rec["analysis"]["scenario"]["loss_usd"],
                            "accounted_loss_usd": rec["analysis"]["plan"]["audit"]["accounted_loss_usd"]}
            checked(name+": Discover, Attack, Collapse, Rescue, Prove and receipt replay")
            page.locator('[data-testid="stMain"]').evaluate("el => { el.scrollTop = 0; }")
            page.screenshot(path=str(output/(name+".png")), full_page=True)

        page.goto("http://localhost:8501")
        page.get_by_role("button", name="FIND MY WEAKEST POINT", exact=False).wait_for()
        page.get_by_text("Live Mode", exact=True).click()
        page.get_by_role("button", name="Start live demo", exact=True).click()
        page.get_by_role("button", name="FIND MY WEAKEST POINT", exact=False).wait_for(timeout=210000)
        workflow("live_demo")
        # A lock must clear the previous recommendation and produce honest infeasibility.
        page.get_by_role("checkbox", name="Hakutora USDC", exact=True).check()
        expect(page.get_by_role("region", name="Rescue comparison")).to_have_count(0)
        page.get_by_role("button", name="BUILD RESCUE PLAN", exact=False).click()
        expect(page.get_by_text("TARGET INFEASIBLE", exact=False)).to_be_visible()
        checked("Live lock invalidates the previous plan and reports infeasibility")
        page.get_by_role("button", name="Replay saved API run", exact=True).click()
        expect(page.get_by_text("HISTORICAL REPLAY", exact=False).first).to_be_visible()
        workflow("saved_demo")
        assert report["saved_demo"]["presentation_context"]["fresh_at_replay"] is False
        page.get_by_role("slider", name="Failure severity", exact=True).fill("25")
        expect(page.get_by_role("region", name="Rescue comparison")).to_have_count(0)
        expect(page.get_by_role("slider", name="Failure severity", exact=True)).to_have_value("25")
        checked("Partial severity change clears the saved plan and preserves 25%")
        page.locator('[data-testid="stMain"]').evaluate("el => { el.scrollTop = 0; }")
        page.get_by_role("button", name="Reset", exact=True).click()
        expect(page.get_by_role("button", name="FIND MY WEAKEST POINT", exact=False)).to_be_enabled()
        page.get_by_role("button", name="FIND MY WEAKEST POINT", exact=False).click()
        expect(page.get_by_role("button", name="SIMULATE FAILURE", exact=False)).to_be_enabled()
        checked("Reset returns to discovery with responsive controls")
        page.get_by_role("button", name="Use offline Snapshot Mode", exact=True).click()
        page.get_by_role("button", name="FIND MY WEAKEST POINT", exact=False).click()
        page.get_by_role("button", name="SIMULATE FAILURE", exact=False).click()
        page.get_by_role("button", name="BUILD RESCUE PLAN", exact=False).click()
        expect(page.get_by_role("region", name="Rescue comparison")).to_contain_text("$499,000")
        checked("Snapshot fallback retains the original baseline and interface")
        browser.close()
    report["status"] = "PASS"
    (output/"live_demo_browser_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
