"""End-to-end checks against serve_test_instance.py (loopback fixture only)."""
import json
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'verification'
OUT.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=shutil.which("google-chrome") or shutil.which("chromium"))
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8093/#applications')
    page.locator('#login-form').wait_for(state='visible')
    page.fill('#username','admin');page.fill('#password','test-admin-pass');page.fill('#captcha-answer','ABC234')
    page.click('#sign-in')
    expect(page.locator('#shell')).to_be_visible()
    page.click('[data-view=applications]')
    expect(page.locator('#view-applications')).to_be_visible()
    expect(page.locator('#ai-dataset option')).to_have_count(13)
    # The new form never writes the laboratory's settings or result state.
    original=page.evaluate('JSON.stringify(spec())')
    page.select_option('#ai-dataset','decaying-bridge')
    page.click('#ai-run')
    expect(page.locator('#ai-network-chart svg')).to_be_visible(timeout=100000)
    expect(page.locator('#ai-status')).to_contain_text('آماده')
    assert page.locator('#ai-results .ai-card').count()==8
    assert page.locator('#ai-results .ai-help').count()==7
    assert page.evaluate('JSON.stringify(spec())')==original
    assert page.evaluate('state.result') is None
    assert page.locator('#ai-results table').count()==7
    assert page.evaluate('(()=>{const ids=[...document.querySelectorAll("#view-applications [id]")].map(e=>e.id);return new Set(ids).size===ids.length;})()')
    assert page.locator('#ai-network-chart svg circle').count()==20
    assert not errors,errors
    page.screenshot(path=str(OUT/'applications-desktop.png'),full_page=True)
    for fmt in ['svg','png']:
        with page.expect_download() as download:
            page.locator(f'#ai-history [data-ai-{fmt}]').click()
        target=OUT/f'applications-chart.{fmt}'
        download.value.save_as(target)
        assert target.stat().st_size>100
    with page.expect_download() as download:page.click('#ai-csv')
    download.value.save_as(OUT/'applications-tables.csv')
    assert 'backtest' in (OUT/'applications-tables.csv').read_text(encoding='utf-8-sig')
    with page.expect_download() as download:page.get_by_text('دانلود همه داده‌ها و تنظیمات (JSON)',exact=True).click()
    download.value.save_as(OUT/'applications-result.json')
    saved=json.loads((OUT/'applications-result.json').read_text())
    assert saved['spec']['dataset']=='decaying-bridge'
    page.select_option('#ai-network-mode','0')
    page.fill('#ai-window','0')
    page.dispatch_event('#ai-window','input')
    assert page.locator('#ai-network-chart svg line').count()>0
    page.click('#ai-play')
    expect(page.locator('#ai-play')).to_have_text('توقف پخش')
    page.click('#ai-play')
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile page overflow'
    page.screenshot(path=str(OUT/'applications-mobile.png'),full_page=True)
    page.set_viewport_size({'width':1440,'height':1000})
    # Reload and reopen a saved application job.
    job=page.evaluate('applicationState.job')
    page.reload()
    expect(page.locator('#ai-saved option[value="'+job+'"]')).to_be_attached()
    page.select_option('#ai-saved',job)
    expect(page.locator('#ai-network-chart svg')).to_be_visible()
    # Settings edits do not silently relabel the saved plots.
    page.select_option('#ai-model','slope_bridge')
    expect(page.locator('#ai-status')).to_contain_text('اجرای قبلی')
    page.click('#ai-run')
    expect(page.locator('#ai-forecast-chart')).to_contain_text('پیش‌بینی نمی‌کند',timeout=100000)
    # Real fixture, every concept, and an explicitly invalid scenario.
    page.select_option('#ai-dataset','decentraland')
    page.select_option('#ai-model','trend_bridge')
    page.fill('#ai-delta','25')
    for checkbox in page.locator('[name=ai-concept]').all():checkbox.check()
    page.click('#ai-run')
    expect(page.locator('#ai-status')).to_contain_text('آماده',timeout=120000)
    assert page.evaluate('applicationState.result.spec.dataset')=='decentraland'
    invalid=page.evaluate('applicationState.result.applications.scenarios.findIndex(s=>!s.valid)')
    assert invalid>=0
    page.select_option('#ai-network-mode',str(invalid))
    expect(page.locator('#ai-network-chart')).to_contain_text('نامعتبر')
    assert page.locator('#ai-network-chart svg circle').count()<=100
    page.screenshot(path=str(OUT/'applications-real-data.png'),full_page=True)
    # Visit the old laboratory and run its original workflow.
    page.click('[data-view=laboratory]')
    expect(page.locator('#view-laboratory')).to_be_visible()
    page.click('#run')
    expect(page.locator('#result-content')).to_be_visible(timeout=100000)
    assert page.evaluate('state.result.summary.valid_rows')==6
    assert page.evaluate('state.result.applications === undefined')
    page.click('[data-view=applications]')
    expect(page.locator('#ai-network-chart svg')).to_be_visible()
    page.click('#logout')
    expect(page.locator('#login')).to_be_visible()
    assert page.evaluate('applicationState.result') is None
    assert page.locator('#applications-content').inner_text()==''
    assert not errors,errors
    (OUT/'applications-browser.json').write_text(json.dumps({'passed':True,'page_errors':errors,'checks':['real worker','7 explained chart sections','graph time and scenario views','SVG PNG CSV JSON downloads','independent laboratory state','saved history','slope semantics','mobile overflow','laboratory regression','logout cleanup']},indent=2))
    browser.close()
print('Application browser checks passed.')
