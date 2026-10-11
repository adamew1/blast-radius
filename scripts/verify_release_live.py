"""Real-browser Live Mode rehearsal; no API mocks or injected observations."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.verify_receipt import verify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://localhost:8501')
    args = parser.parse_args()
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(ROOT/'.playwright-mcp/browsers'))
    from playwright.sync_api import sync_playwright, expect
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'js_errors': [], 'interactions': [],
              'fresh_capture_passed': False, 'external_browser_requests': [], 'api_mocks': False}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1500, 'height': 1100}, accept_downloads=True)

        def route(request):
            if request.request.url.startswith(args.url):
                request.continue_()
            else:
                report['external_browser_requests'].append(request.request.url)
                request.abort()

        context.route('**/*', route)
        page = context.new_page()
        page.set_default_timeout(45000)
        page.on('pageerror', lambda exc: report['js_errors'].append(str(exc)))

        def checked(name):
            assert not page.locator('[data-testid="stException"]').count(), page.locator('[data-testid="stException"]').all_text_contents()
            assert not report['js_errors'], report['js_errors']
            report['interactions'].append(name)
            print('PASS', name, flush=True)

        def select_hakutora(url):
            page.goto(url)
            page.get_by_role('button', name='FIND MY WEAKEST POINT').wait_for()
            expect(page.get_by_role('radio', name='Snapshot Mode', exact=True)).to_be_checked()
            page.get_by_text('Live Mode', exact=True).click()
            page.get_by_role('button', name='Load $1M Hakutora live example', exact=True).click()
            expect(page.get_by_role('combobox', name='Maximum risk-data age (minutes)')).to_have_value('15')
            expect(page.locator('[data-testid="stStatusWidget"]')).not_to_be_visible()
            page.get_by_role('button', name='Fetch fresh data & discover', exact=True).click()
            page.get_by_role('button', name='Download live observation receipt').wait_for(timeout=210000)

        select_hakutora(args.url)
        expect(page.locator('[data-testid="stStatusWidget"]')).not_to_be_visible()
        if page.get_by_role('button', name='Calculate indicative model rescue').count():
            picker = page.get_by_role('combobox', name='Attack dependency', exact=True)
            picker.fill('cbBTC')
            picker.press('ArrowDown')
            picker.press('ArrowDown')
            picker.press('Enter')
            expect(picker).to_have_value('cbBTC')
            page.get_by_role('button', name='Calculate indicative model rescue').click()
            expect(page.locator('[data-testid="stJson"]').filter(has_text='indicative model rescue; not executable')).to_be_visible()
            with page.expect_download() as result:
                page.get_by_role('button', name='Download live observation receipt').click()
            path = ROOT/'artifacts/live/release_hakutora_browser_receipt.json'
            result.value.save_as(str(path))
            verify(path)
            rec = json.loads(path.read_text(encoding='utf-8'))
            assert rec['analysis']['freshness']['risk_usable'] and rec['analysis']['freshness']['execution_usable']
            assert rec['analysis']['plan']['audit']['verified'] and not rec['analysis']['plan']['executable']
            report['fresh_capture_passed'] = True
            report['receipt'] = path.relative_to(ROOT).as_posix()
            report['freshness'] = rec['analysis']['freshness']
            checked('Real Hakutora browser capture, cbBTC shock, indicative rescue and downloaded receipt replay')
            slider = page.get_by_role('slider', name='Intrinsic shock (%)')
            slider.focus()
            slider.press('Home')
            expect(page.locator('[data-testid="stMetric"]').filter(has_text='Conditional scenario loss')).to_contain_text('$0.00')
            expect(page.locator('[data-testid="stJson"]').filter(has_text='indicative model rescue; not executable')).to_have_count(0)
            checked('Live severity change clears the previous recommendation')
            field = page.get_by_role('spinbutton', name='Morpho Hakutora USDC', exact=True)
            field.fill('1050000')
            field.press('Enter')
            expect(page.get_by_text('Portfolio or quote grid changed. Refresh before analysis.', exact=True)).to_be_visible()
            expect(page.get_by_role('button', name='Calculate indicative model rescue')).to_have_count(0)
            checked('Live allocation change hides prior scenario and recommendation until refreshed')
        else:
            report['fresh_capture_rejection'] = page.locator('[data-testid="stAlert"]').all_text_contents()
            checked('Fresh request rejected without presenting a current recommendation')
        page.get_by_role('button', name='Use offline Snapshot Mode', exact=True).click()
        page.get_by_role('button', name='FIND MY WEAKEST POINT').wait_for()
        checked('One-click fallback returns from Live Mode to the original offline demonstration')
        page.close()
        page = context.new_page()
        page.on('pageerror', lambda exc: report['js_errors'].append(str(exc)))
        page.goto(args.url)
        page.get_by_role('button', name='FIND MY WEAKEST POINT').wait_for()
        page.get_by_text('Live Mode', exact=True).click()
        page.get_by_role('button', name='Fetch fresh data & discover').click()
        page.get_by_role('button', name='Download live observation receipt').wait_for(timeout=210000)
        with page.expect_download() as result:
            page.get_by_role('button', name='Download live observation receipt').click()
        path = ROOT/'artifacts/live/release_full_book_browser_receipt.json'
        result.value.save_as(str(path))
        verify(path)
        full = json.loads(path.read_text(encoding='utf-8'))
        report['full_book_freshness'] = full['freshness_at_capture']
        if not full['freshness_at_capture']['risk_usable']:
            expect(page.get_by_text('Live analysis rejected.', exact=False)).to_be_visible()
            expect(page.get_by_role('button', name='Calculate indicative model rescue')).to_have_count(0)
            checked('Real full-book rejected inputs produce a downloadable receipt and no current recommendation')
        else:
            checked('Real full-book acquisition passed risk checks; no rescue certification asserted by this check')
        page.get_by_role('button', name='Use offline Snapshot Mode', exact=True).click()
        page.get_by_role('button', name='FIND MY WEAKEST POINT').click()
        page.get_by_role('button', name='SIMULATE FAILURE').click()
        page.get_by_role('button', name='BUILD RESCUE PLAN').click()
        expect(page.get_by_role('region', name='Rescue comparison')).to_contain_text('$499,000')
        checked('Snapshot discovery, stress and rescue recover immediately after the full-book request')
        assert not report['external_browser_requests'], report['external_browser_requests']
        context.close()
        browser.close()
    report['status'] = 'PASS'
    (ROOT/'artifacts/release_live_browser_verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
