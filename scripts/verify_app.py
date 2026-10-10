"""Offline browser smoke test. Launch run.ps1 with BLAST_RADIUS_OFFLINE=1 first.

Requires the optional development package playwright and its Chromium browser.
Writes artifacts/verification.json and artifacts/screenshots/*.png.
"""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def contracts():
    b = json.loads((ROOT / "artifacts/backtest_results.json").read_text(encoding="utf-8"))
    s = json.loads((ROOT / "artifacts/market_scan.json").read_text(encoding="utf-8"))
    assert {"with_stream", "without_stream"} <= b["headline"].keys()
    assert len(b["events"]) >= 4 and any(not e["hit"] for e in b["events"])
    assert {"false_alarms", "rule_vs_ml", "rule", "params", "split"} <= b.keys()
    assert b["false_alarms"]["n_pairs"] >= 3
    assert s["n_positions"] == s["n_eligible"] and not s["errors"]
    assert len(s["top10"]) == min(10, s["n_positions"])
    assert 0 <= s["coverage"]["fully_looked_through_pct"] <= 100
    assert abs(sum(r["size_usd"] for r in s["positions"]) - s["total_scanned_usd"]) < .01
    for cohort in ("with_stream", "without_stream"):
        rows = b["events"] if cohort == "with_stream" else [e for e in b["events"] if e["cohort"] != "development"]
        assert b["headline"][cohort]["total_saved_vs_naive_usd"] == sum(e["saved_vs_naive_usd"] or 0 for e in rows)
    return {"events": len(b["events"]), "non_development_crises": b["n_triggers_out_of_sample"],
            "positions": s["n_positions"], "contracts": "passed"}


def main():
    from playwright.sync_api import expect, sync_playwright
    output = ROOT / "artifacts/screenshots"
    output.mkdir(exist_ok=True)
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".playwright-mcp/browsers"))
    report = dict(verified_at=datetime.now(timezone.utc).isoformat(),
                  app_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                  offline=True, browser="local Playwright Chromium (MCP unavailable)",
                  artifacts=contracts(), pages=[], interactions=[], external_requests=[])
    source_files = sorted(set(ROOT.glob("app/**/*.py")) | set(ROOT.glob("blast_radius/**/*.py"))
                          | set(ROOT.glob("data/manual/*.yaml")) | set(ROOT.glob("data/backtest/*.yaml"))
                          | {ROOT / "config.yaml"})
    report["source_sha256"] = {
        str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
        for path in source_files
    }
    report["source_hash_normalization"] = "UTF-8 text with line endings normalized to LF"
    cases = [
        ("Home", "/", "💥 Blast Radius", 0),
        ("Position", "/Position", "Position risk & dependency look-through", 2),
        ("Portfolio", "/Portfolio", "Portfolio — shared dependencies & ranked actions", 1),
        ("Replay", "/Replay_Stream", "Replay — Stream Finance → Elixir deUSD contagion", 2),
        ("Track_Record", "/Track_Record", "Track Record — does the signal generalise?", 8),
        ("Market_Scan", "/Market_Scan", "Market Scan — shared dependencies across Ethereum", 1),
    ]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1500, "height": 1100}, device_scale_factor=1)
        def block_external(route):
            if not route.request.url.startswith(("http://localhost:8501", "ws://localhost:8501")):
                report["external_requests"].append(route.request.url)
                route.abort()
            else:
                route.continue_()
        context.route("**/*", block_external)
        page = context.new_page()
        page.set_default_timeout(60000)
        js_errors = []
        page.on("pageerror", lambda error: js_errors.append(str(error)))

        def check():
            errors = page.locator('[data-testid="stException"]').all_text_contents()
            assert not errors, errors
            assert not js_errors, js_errors

        def screenshot(name):
            check()
            page.screenshot(path=str(output / f"{name}.png"), full_page=True)

        for name, path, heading, charts in cases:
            page.goto("http://localhost:8501" + path, wait_until="domcontentloaded")
            page.get_by_role("heading", name=heading, exact=True).wait_for()
            if charts:
                page.wait_for_function("n => document.querySelectorAll('[data-testid=stPlotlyChart] .js-plotly-plot').length >= n", arg=charts)
            else:
                page.get_by_text("Incident base rates by DefiLlama category", exact=False).wait_for()
            page.locator('[data-testid="stSpinner"]').wait_for(state="hidden")
            screenshot(name)
            report["pages"].append(dict(name=name, path=path, charts=charts, exceptions=0,
                                        screenshot=f"artifacts/screenshots/{name}.png"))
            print(f"PASS {name}", flush=True)

            if name == "Position":
                page.get_by_text("Simulate failure", exact=True).click()
                page.wait_for_function("() => document.querySelectorAll('[data-testid=stPlotlyChart] .js-plotly-plot').length >= 3")
                screenshot("Position_what_if")
                report["interactions"].append("Position what-if toggle renders forced-shock results")
                page.get_by_text("Simulate failure", exact=True).click()
                page.get_by_role("combobox").first.click()
                page.get_by_role("option", name="Morpho Smokehouse USDT", exact=True).click()
                page.get_by_text("vault TVL", exact=False).first.wait_for()
                page.locator('[data-testid="stSpinner"]').wait_for(state="hidden")
                screenshot("Position_Morpho")
                report["interactions"].append("Position selector renders Smokehouse USDT")
            if name == "Replay":
                slider = page.get_by_role("slider").first
                slider.focus()
                slider.press("Home")
                expect(slider).to_have_value("0")
                page.get_by_text("2025-11-01", exact=True).last.wait_for()
                screenshot("Replay_Nov_1")
                for i in range(6):
                    slider.press("ArrowRight")
                    expect(slider).to_have_value(str(i + 1))
                page.get_by_text("2025-11-07", exact=True).last.wait_for()
                screenshot("Replay_Nov_7")
                report["interactions"].append("Replay slider navigates to Nov 1 and Nov 7")
        # Navigation is verified via actual sidebar links too, not just direct URLs.
        nav = page.locator('[data-testid="stSidebarNav"] a').all()
        assert len(nav) == 6, f"Expected 6 sidebar links, found {len(nav)}"
        nav[0].click()
        page.get_by_role("heading", name="💥 Blast Radius", exact=True).wait_for()
        check()
        report["interactions"].append("Six-page sidebar navigation returns to Home")
        browser.close()
    report["status"] = "passed"
    (ROOT / "artifacts/verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("All six pages and interactions passed with external browser requests blocked.")


if __name__ == "__main__":
    main()
