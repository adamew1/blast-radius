"""Offline browser proof of adding instruments outside the original portfolio."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.verify_receipt import verify


def main():
    from playwright.sync_api import sync_playwright, expect
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".playwright-mcp/browsers"))
    url = "http://localhost:8501"
    catalog = json.loads((ROOT / "data/fire_drill/catalog.json").read_text())["positions"]
    report = {"verified_at": datetime.now(timezone.utc).isoformat(), "external_requests": [], "js_errors": [], "interactions": []}
    paths = sorted((ROOT/"blast_radius").rglob("*.py")) + sorted((ROOT/"app").rglob("*.py"))
    paths += sorted((ROOT/"app/components/terminal").glob("*"))
    report["source_sha256"] = {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_text(encoding="utf-8").encode()).hexdigest() for p in paths if p.is_file()}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1500, "height": 1100}, accept_downloads=True)

        def intercept(route):
            if route.request.url.startswith(url):
                route.continue_()
            else:
                report["external_requests"].append(route.request.url)
                route.abort()

        context.route("**/*", intercept)
        page = context.new_page()
        page.set_default_timeout(30000)
        page.on("pageerror", lambda error: report["js_errors"].append(str(error)))

        def checked(name):
            assert not page.locator('[data-testid="stException"]').count(), page.locator('[data-testid="stException"]').all_text_contents()
            assert not report["js_errors"], report["js_errors"]
            report["interactions"].append(name)
            print("PASS", name, flush=True)

        def download(name):
            if page.get_by_role("button", name="Show Me the Evidence").count():
                page.get_by_role("button", name="Show Me the Evidence").click()
            with page.expect_download() as result:
                page.get_by_role("button", name="Download decision receipt").click()
            path = ROOT / f"artifacts/browser_catalog_{name}_receipt.json"
            result.value.save_as(str(path))
            verify(path)
            return json.loads(path.read_text(encoding="utf-8"))

        page.goto(url)
        page.get_by_role("button", name="FIND MY WEAKEST POINT").wait_for(timeout=60000)
        page.locator(".challenge summary").click()
        expect(page.locator(".challenge")).to_contain_text("14 admitted Ethereum instruments")
        # Dynamic add refuses an eleventh row; it does not silently hide a holding.
        page.get_by_role("button", name="Add instrument", exact=True).click()
        expect(page.locator("#challenge-error")).to_contain_text("maximum ten")
        while page.locator("[data-remove]").count():
            page.locator("[data-remove]").first.click()
        for position in catalog:
            page.locator("#catalog-instrument").select_option(position["id"])
            page.get_by_role("button", name="Add instrument", exact=True).click()
            page.locator(f'[data-size="{position["id"]}"]').fill("750000" if "4a5067" in position["id"] else "500000")
        page.screenshot(path=str(ROOT / "artifacts/screenshots/FireDrill_catalog.png"))
        page.get_by_role("button", name="APPLY PORTFOLIO & REDISCOVER").click()
        page.get_by_role("button", name="FIND MY WEAKEST POINT").wait_for()
        expect(page.get_by_role("region", name="Portfolio financial metrics")).to_contain_text("$2,250,000")
        expect(page.get_by_role("region", name="Portfolio financial metrics")).to_contain_text("4 positions")
        checked("Removed the prepared book and constructed a four-position book entirely from new catalog instruments")
        page.get_by_role("button", name="FIND MY WEAKEST POINT").click()
        page.locator("#dependency").wait_for()
        for name, token in (("wsteth", "0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0"),
                            ("apyusd", "0x38eeb52f0771140d10c4e9a9a72349a329fe8a6a"),
                            ("usd3", "0x056b269eb1f75477a8666ae8c7fe01b64dd55ecc")):
            page.locator("#dependency").select_option("token:ethereum:" + token)
            expect(page.locator("#dependency")).to_have_value("token:ethereum:" + token)
            page.get_by_role("button", name="SIMULATE FAILURE" if name == "wsteth" else "REPLAY FAILURE").click()
            page.locator("#limit").fill("200000")
            page.get_by_role("button", name="BUILD RESCUE PLAN").click()
            expect(page.locator(".status")).to_contain_text("OPTIMAL")
            rec = download(name)
            assert rec["receipt_schema"] == "blast-radius-decision-v3"
            assert {p["id"] for p in rec["portfolio"]} == {p["id"] for p in catalog}
            expected = json.loads((ROOT / f"artifacts/catalog_{name}_receipt.json").read_text())
            for key in ("accounted_loss_usd", "protection_cost_usd", "capital_sold_usd"):
                assert abs(rec["plan"]["audit"][key] - expected["plan"]["audit"][key]) <= .02
            checked(f"Discovered {name}, propagated the real paths, optimized and reproduced the all-new-book receipt")
        # Removing a new instrument clears the selected dependency and its plan.
        page.locator(".challenge summary").click()
        removed = next(p for p in catalog if "4a5067" in p["id"])
        page.locator(f'[data-remove="{removed["id"]}"]').click()
        page.get_by_role("button", name="APPLY PORTFOLIO & REDISCOVER").click()
        expect(page.get_by_role("region", name="Rescue comparison")).to_have_count(0)
        page.get_by_role("button", name="FIND MY WEAKEST POINT").click()
        page.locator("#dependency").wait_for()
        expect(page.locator('option[value="token:ethereum:0x056b269eb1f75477a8666ae8c7fe01b64dd55ecc"]')).to_have_count(0)
        checked("Removing a newly added PT removes its dependency and invalidates its previous rescue")
        page.get_by_role("button", name="Reset", exact=True).click()
        expect(page.get_by_role("region", name="Portfolio financial metrics")).to_contain_text("$10,000,000")
        page.get_by_role("button", name="FIND MY WEAKEST POINT").click()
        page.get_by_role("button", name="SIMULATE FAILURE").click()
        page.get_by_role("button", name="BUILD RESCUE PLAN").click()
        expect(page.get_by_role("region", name="Rescue comparison")).to_contain_text("$499,000")
        checked("Reset from an all-new book restores the audited default rescue")
        # The native fallback must also admit an instrument beyond the ten originals.
        page.goto(url + "/?fallback=1")
        page.get_by_role("heading", name="Blast Radius — Break My Portfolio").wait_for()
        page.get_by_role("button", name="BUILD RESCUE PLAN").wait_for()
        expect(page.locator('[data-testid="stStatusWidget"]')).not_to_be_visible(timeout=30000)
        page.get_by_text("Challenge this portfolio", exact=True).click()
        picker = page.get_by_role("combobox", name="Portfolio instruments (maximum ten)")
        picker.click()
        picker.fill("Pendle PT-apyUSD")
        page.get_by_role("option", name="Pendle PT-apyUSD", exact=False).click()
        page.keyboard.press("Escape")
        # Selection reruns Streamlit to create the new allocation field. Wait
        # for that render before editing or submitting the allocation form.
        added = page.get_by_role("spinbutton", name="Pendle PT-apyUSD", exact=False)
        expect(added).to_be_visible(timeout=30000)
        expect(page.locator('[data-testid="stStatusWidget"]')).not_to_be_visible(timeout=30000)
        added.fill("750000")
        removed_field = page.get_by_role("spinbutton", name="Pendle PT-sUSDS · 2026-11-26", exact=True)
        removed_field.fill("0")
        removed_field.press("Tab")
        page.get_by_role("button", name="Apply portfolio & rediscover").click()
        expect(page.get_by_text("$9,750,000", exact=True)).to_be_visible(timeout=30000)
        page.get_by_role("button", name="Find My Weakest Point", exact=True).click()
        expect(page.locator('[data-testid="stStatusWidget"]')).not_to_be_visible(timeout=30000)
        page.get_by_role("button", name="BUILD RESCUE PLAN").click()
        expect(page.locator('[data-testid="stJson"]').first).to_contain_text("catalog-pt-")
        checked("Native fallback adds a catalog PT and runs discovery and rescue")
        context.close()
        browser.close()
    assert not report["external_requests"], report["external_requests"]
    report["status"], report["offline"] = "passed", True
    (ROOT / "artifacts/catalog_browser_verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("PASS complete catalog demonstration; no external requests", flush=True)


if __name__ == "__main__":
    main()
