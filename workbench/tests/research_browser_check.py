"""Actual Chromium verification of the protected research dashboard."""
import io,json,zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];URL='http://127.0.0.1:8095'
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--disable-gpu','--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows','--disable-features=CalculateNativeWinOcclusion'])
    page=browser.new_page(viewport=dict(width=1440,height=1100));errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(URL);page.fill('#username','admin');page.fill('#password','test-admin-pass');expect(page.locator('#sign-in')).to_be_enabled();page.fill('#captcha-answer','ABC234');page.locator('#captcha-answer').press('Enter');expect(page.locator('#shell')).to_be_visible()
    page.click('[data-view="researcher"]');expect(page.locator('#research-filters')).to_be_visible()
    assert page.locator('.research-chart-grid .figure-card').count()==12
    assert page.evaluate('researchState.data.summary.sessions')==2
    assert page.evaluate('researchState.data.summary.unique_participants')==1
    assert page.locator('#research-accuracy').locator('..').inner_text().find('bridge 1/2')>=0
    with page.expect_download() as pending:page.click('#research-export-zip')
    with zipfile.ZipFile(pending.value.path()) as archive:
        report=json.loads(archive.read('report.json'));assert report['summary']['sessions']==2
        assert json.loads(archive.read('metadata.json'))['task_definitions']['bridge']['answer']=='increase'
    with page.expect_download() as pending:page.click('[data-research-svg="research-accuracy"]')
    assert '<svg' in Path(pending.value.path()).read_text()
    with page.expect_download() as pending:page.click('[data-research-png="research-accuracy"]')
    assert Path(pending.value.path()).read_bytes().startswith(b'\x89PNG')
    page.click('[data-research-tab="sessions"]');assert page.locator('.research-data-table tbody tr').count()==2
    page.locator('.research-data-table tbody tr').filter(has_text='complete').locator('button').click()
    expect(page.locator('#research-detail')).to_contain_text('<script>audit</script>')
    assert page.locator('#research-detail script').count()==0
    page.click('[data-research-tab="responses"]');assert page.locator('.research-data-table tbody tr').count()==3
    page.fill('#research-search','history');assert page.locator('.research-data-table tbody tr').count()==1
    page.click('[data-research-tab="experiments"]');assert page.locator('.research-data-table tbody tr').count()==2
    page.locator('.research-data-table tbody tr').filter(has_text='complete').locator('button').click()
    expect(page.locator('#research-save-job')).to_be_visible()
    assert page.locator('#research-job-response svg').count()==1
    with page.expect_download() as pending:page.click('#research-save-job')
    assert json.loads(Path(pending.value.path()).read_text())['result']['baseline']==8
    page.click('[data-research-tab="impacts"]');assert page.locator('.research-data-table tbody tr').count()==2
    page.fill('#research-search','infeasible');expect(page.locator('.research-data-table')).to_contain_text('Not available')
    page.locator('#research-filters select').select_option('complete');page.locator('#research-filters button').click()
    expect(page.locator('#research-filters')).to_be_visible();assert page.evaluate('researchState.data.summary.sessions')==1
    page.locator('#research-filters input[name=start]').fill('1900-01-01');page.locator('#research-filters input[name=end]').fill('1900-01-02');page.locator('#research-filters button').click()
    expect(page.locator('#research-filters')).to_be_visible();assert page.evaluate('researchState.data.summary.sessions')==0
    page.click('[data-research-tab="overview"]');expect(page.locator('#research-accuracy')).to_contain_text('No observations')
    page.set_viewport_size(dict(width=390,height=844))
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),'Chart mobile overflow'
    page.click('[data-research-tab="experiments"]');assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),'Table mobile overflow'
    page.locator('#research-filters input[name=start]').fill('2026-06-01');page.locator('#research-filters input[name=end]').fill('2026-06-02');page.locator('#research-filters select').select_option('all');page.locator('#research-filters button').click();expect(page.locator('#research-filters')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),'Populated table mobile overflow'
    cached=page.evaluate('researchState.data');held=[]
    page.route('**/api/admin/report?*',lambda route:held.append(route))
    with page.expect_request('**/api/admin/report?*'):
        page.locator('#research-filters button').click()
    page.click('#logout');expect(page.locator('#login')).to_be_visible()
    assert held
    held[0].fulfill(status=200,content_type='application/json',body=json.dumps(cached))
    page.wait_for_timeout(200)
    assert page.evaluate('researchState.data') is None
    assert not page.locator('#researcher-content').inner_text()
    assert not errors,errors
    browser.close()
(ROOT/'verification'/'research-browser-result.json').write_text(json.dumps(dict(passed=True,charts=12,errors=errors,checks=['protected researcher login','cohort and repeated visitors','charts','ZIP provenance','SVG/PNG','feedback XSS escaping','search','saved experiment and full JSON','invalid nulls','date/status filters','empty cohort','mobile charts/tables','logout clears cached records and ignores stale responses']),indent=2))
print('Research browser E2E passed: 12 charts, details, filtered exports, provenance, privacy-safe display and mobile; no JavaScript errors.')
