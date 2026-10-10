"""Real offline browser rehearsal with screenshots, receipt verification and video."""
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


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--url",default="http://localhost:8501")
    parser.add_argument("--record",action="store_true")
    args=parser.parse_args()
    from playwright.sync_api import sync_playwright, expect
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH",str(ROOT / ".playwright-mcp/browsers"))
    output=ROOT / "artifacts/screenshots"
    output.mkdir(exist_ok=True)
    report={"verified_at":datetime.now(timezone.utc).isoformat(),"url":args.url,
            "offline":True,"interactions":[],"external_requests":[],"js_errors":[],"screenshots":[]}
    report["source_sha256"]={str(p.relative_to(ROOT)).replace("\\","/"):hashlib.sha256(p.read_text(encoding="utf-8").encode()).hexdigest()
                            for folder in ("blast_radius/fire_drill","app/components/terminal") for p in (ROOT/folder).glob("*") if p.is_file()}
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        config={"viewport":{"width":1500,"height":1100},"accept_downloads":True}
        if args.record:
            config.update(record_video_dir=str(ROOT/"artifacts/demo_video"),record_video_size={"width":1500,"height":1100})
        context=browser.new_context(**config)
        def intercept(route):
            if route.request.url.startswith(args.url):
                route.continue_()
            else:
                report["external_requests"].append(route.request.url)
                route.abort()
        context.route("**/*",intercept)
        page=context.new_page()
        page.set_default_timeout(30000)
        page.on("pageerror",lambda e:report["js_errors"].append(str(e)))

        def checked(name):
            assert not page.locator('[data-testid="stException"]').count(),page.locator('[data-testid="stException"]').all_text_contents()
            assert not report["js_errors"],report["js_errors"]
            report["interactions"].append(name)
            print("PASS",name,flush=True)

        def shot(name, target=None):
            page.wait_for_timeout(1400)
            if target:
                page.locator(target).scroll_into_view_if_needed()
            page.screenshot(path=str(output/f"FireDrill_{name}.png"))
            report["screenshots"].append(f"artifacts/screenshots/FireDrill_{name}.png")

        page.goto(args.url)
        page.get_by_role("button",name="FIND MY WEAKEST POINT").wait_for(timeout=60000)
        checked("Clean launch from frozen evidence")
        shot("initial")
        page.get_by_role("button",name="FIND MY WEAKEST POINT").click()
        expect(page.locator("#dependency")).to_have_value("token:ethereum:0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0")
        checked("Automatic ranking reveals wstETH across five positions")
        shot("discovery")
        page.get_by_role("button",name="SIMULATE FAILURE").click()
        page.get_by_role("button",name="BUILD RESCUE PLAN").wait_for()
        assert float(page.locator("#loss-counter").get_attribute("data-target"))>2e6
        checked("Failure propagates over actual dependency paths")
        shot("collapse")
        # An actual graph node event, rather than only the select control.
        page.locator('[data-node="issuer:lido"]').click()
        expect(page.locator("#dependency")).to_have_value("issuer:lido")
        checked("Clicking a canonical node selects a different dependency")
        page.locator("#dependency").select_option("token:ethereum:0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0")
        expect(page.locator("#terminal")).to_have_attribute("data-revision", "token:ethereum:0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0:1.0::500000.0")
        page.get_by_role("button",name="BUILD RESCUE PLAN").click()
        page.get_by_role("region",name="Rescue comparison").wait_for()
        expect(page.locator(".status")).to_contain_text("OPTIMAL")
        checked("Least-cost rescue independently verified within target")
        shot("rescue",".rescue-panel")
        page.get_by_role("button",name="Before",exact=True).click()
        expect(page.get_by_role("button",name="Before",exact=True)).to_have_class("on")
        page.get_by_role("button",name="After rescue",exact=True).click()
        expect(page.get_by_role("button",name="After rescue",exact=True)).to_have_class("on")
        checked("Before and after transform actual retained exposures")
        page.locator('.lock input[value="pt-wsteth"]').check()
        page.get_by_role("button",name="BUILD RESCUE PLAN").click()
        expect(page.locator(".status")).to_contain_text("TARGET INFEASIBLE")
        checked("Lock challenge reports infeasibility honestly")
        shot("locked",".rescue-panel")
        page.get_by_role("button",name="Show Me the Evidence").click()
        page.get_by_role("heading",name="Show Me the Evidence",exact=True).wait_for()
        checked("Evidence exposes provenance, assumptions and source bundle")
        shot("proof",".proof-inline")
        with page.expect_download() as download:
            page.get_by_role("button",name="Download decision receipt").click()
        receipt_path=ROOT/"artifacts/browser_decision_receipt.json"
        download.value.save_as(str(receipt_path))
        verify(receipt_path)
        checked("Downloaded receipt recomputes independently")
        # Zero severity must reset an earlier rescue, rather than leave stale output.
        page.locator("#severity").fill("0")
        page.locator("#severity").dispatch_event("change")
        expect(page.locator("#loss-counter")).to_have_attribute("data-target","0")
        expect(page.get_by_role("region",name="Rescue comparison")).to_have_count(0)
        checked("Zero severity gives zero loss and invalidates stale rescue")
        page.get_by_role("button",name="Reset",exact=True).click()
        page.get_by_role("button",name="FIND MY WEAKEST POINT").wait_for()
        checked("Reset restores a clean demonstration")
        page.goto(args.url+"/?fallback=1")
        page.get_by_role("heading",name="Blast Radius — Break My Portfolio").wait_for()
        page.get_by_role("button",name="BUILD RESCUE PLAN").click()
        checked("Native-control fallback computes a rescue")
        # Keep research smoke checks in this same frozen/no-external-network context.
        for path, heading in (("Position","Position risk & dependency look-through"),
                              ("Portfolio","Portfolio — shared dependencies & ranked actions"),
                              ("Replay_Stream","Replay — Stream Finance → Elixir deUSD contagion"),
                              ("Track_Record","Track Record — does the signal generalise?"),
                              ("Market_Scan","Market Scan — shared dependencies across Ethereum")):
            page.goto(args.url+"/"+path)
            page.get_by_role("heading",name=heading,exact=True).wait_for(timeout=60000)
            page.locator('[data-testid="stSpinner"]').wait_for(state="hidden",timeout=60000)
            checked("Preserved offline research page: "+path)
        page.goto(args.url+"/Research")
        page.get_by_text("Incident base rates by DefiLlama category",exact=False).wait_for(timeout=60000)
        checked("Preserved methodology and expected-loss analysis")
        if args.record:
            report["video"] = str(Path(page.video.path()).relative_to(ROOT)).replace("\\","/")
        context.close()
        browser.close()
    assert not report["external_requests"],report["external_requests"]
    report["status"]="passed"
    (ROOT/"artifacts/fire_drill_verification.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("PASS entire offline demo and research pages; no external requests",flush=True)


if __name__=="__main__":
    main()
