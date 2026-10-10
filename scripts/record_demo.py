"""Record the real two-minute presentation, with clearly editorial captions.

Requires a running local app. No financial values or responses are injected.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--url",default="http://localhost:8501")
    args=parser.parse_args()
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH",str(ROOT/".playwright-mcp/browsers"))
    from playwright.sync_api import sync_playwright, expect
    output=ROOT/"artifacts/demo_video"
    output.mkdir(exist_ok=True)
    report={"recorded_at":datetime.now(timezone.utc).isoformat(),"url":args.url,
            "external_requests":[],"js_errors":[],"stages":[],"caption_classification":"editorial; no financial values injected"}
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        context=browser.new_context(viewport={"width":1500,"height":1100},
                                   record_video_dir=str(output),record_video_size={"width":1500,"height":1100})
        def intercept(route):
            if route.request.url.startswith(args.url):
                route.continue_()
            else:
                report["external_requests"].append(route.request.url)
                route.abort()
        context.route("**/*",intercept)
        page=context.new_page()
        page.on("pageerror",lambda e:report["js_errors"].append(str(e)))
        page.goto(args.url)
        page.get_by_role("button",name="FIND MY WEAKEST POINT").wait_for(timeout=60000)
        start=time.monotonic()
        def hold(until):
            while time.monotonic()-start<until:
                page.wait_for_timeout(min(500,int((until-(time.monotonic()-start))*1000)+1))
        def caption(title,text):
            report["stages"].append({"title":title,"at_seconds":round(time.monotonic()-start,2)})
            page.evaluate("""({title,text})=>{
                let c=document.getElementById('demo-caption');
                if(!c){c=document.createElement('div');c.id='demo-caption';document.body.append(c);}
                Object.assign(c.style,{position:'fixed',bottom:'12px',left:'50%',transform:'translateX(-50%)',
                  width:'min(1000px,90vw)',padding:'12px 18px',background:'#07131ff2',border:'1px solid #3a7568',
                  borderRadius:'7px',color:'#d2e7e1',font:'15px Segoe UI, sans-serif',zIndex:'999999',pointerEvents:'none',
                  boxShadow:'0 8px 30px #0008'});
                c.replaceChildren();const b=document.createElement('b');b.style.color='#4adbc0';b.textContent=title+'  ';
                c.append(b,document.createTextNode(text));
            }""",{"title":title,"text":text})
        caption("THE ILLUSION", "Ten investments. Ten million dollars. What if five of them share a hidden bet?")
        hold(12)
        page.get_by_role("button",name="FIND MY WEAKEST POINT").click()
        expect(page.locator("#dependency")).to_have_value("token:ethereum:0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0")
        caption("DISCOVER", "Computed from the graph: wstETH connects a Pendle position and four Morpho vaults.")
        print("DISCOVER",flush=True)
        hold(30)
        page.get_by_role("button",name="SIMULATE FAILURE").click()
        page.get_by_role("button",name="BUILD RESCUE PLAN").wait_for()
        caption("ATTACK → COLLAPSE", "A hypothetical total-loss shock. Actual dependency paths. Conditional loss, not a forecast.")
        print("COLLAPSE",flush=True)
        hold(50)
        page.get_by_role("button",name="BUILD RESCUE PLAN").click()
        page.get_by_role("region",name="Rescue comparison").wait_for()
        expect(page.locator(".status")).to_contain_text("OPTIMAL")
        expect(page.get_by_role("region",name="Rescue comparison")).to_contain_text("$499,000")
        caption("RESCUE", "Protect before failure: the least-cost reduction plan within captured quotes and shared liquidity bounds.")
        hold(55)
        page.locator(".rescue-panel").scroll_into_view_if_needed()
        print("RESCUE",flush=True)
        hold(80)
        page.locator('.lock input[value="pt-wsteth"]').check()
        page.get_by_role("button",name="BUILD RESCUE PLAN").click()
        expect(page.locator(".status")).to_contain_text("TARGET INFEASIBLE")
        expect(page.locator(".status")).to_contain_text("$1,004,800")
        page.locator(".rescue-panel").scroll_into_view_if_needed()
        caption("CHALLENGE", "Lock PT-wstETH. The target is now infeasible. The system shows the attainable result honestly.")
        print("CHALLENGE",flush=True)
        hold(95)
        page.get_by_role("button",name="Show Me the Evidence").click()
        page.locator(".proof-inline").scroll_into_view_if_needed()
        caption("PROVE", "Sources, timestamps, RPC-verified decimals and explicit assumptions. Download and independently verify the decision.")
        print("PROVE",flush=True)
        hold(102)
        page.get_by_role("tab",name="Model & receipt").click()
        page.get_by_role("tab",name="Model & receipt").scroll_into_view_if_needed()
        expect(page.locator('[data-testid="stJson"]').filter(has_text="pt_underlying_claim_override").last).to_be_visible()
        hold(110)
        page.get_by_role("tab",name="Dependencies & coefficients").click()
        page.locator('[data-testid="stExpander"]').filter(has_text="Pendle PT-wstETH").first.locator("summary").click()
        hold(120)
        assert not page.locator('[data-testid="stException"]').count()
        assert not report["external_requests"],report["external_requests"]
        assert not report["js_errors"],report["js_errors"]
        report["story_duration_seconds"]=round(time.monotonic()-start,2)
        video=page.video
        context.close()
        target=output/"blast-radius-two-minute.webm"
        video.save_as(str(target))
        original=Path(video.path())
        if original!=target:
            original.unlink(missing_ok=True)
        browser.close()
    report["video"]="artifacts/demo_video/blast-radius-two-minute.webm"
    report["video_sha256"]=hashlib.sha256(target.read_bytes()).hexdigest()
    report["status"]="PASS"
    (output/"recording_manifest.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    (output/"README.md").write_text("# Offline demonstration\n\n`blast-radius-two-minute.webm` records actual browser interactions. Captions are editorial; all financial results come from the Python engine.\n\nRe-record with `scripts/record_demo.py --url <local-url>`.\n",encoding="utf-8")
    print(f"Saved {target}",flush=True)


if __name__=="__main__":
    main()
