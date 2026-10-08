"""Operator browser smoke test. Credentials are read locally, never printed."""
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

parser=argparse.ArgumentParser()
parser.add_argument('--url',default='http://127.0.0.1:8091')
parser.add_argument('--account-file',type=Path)
parser.add_argument('--captcha-answer',help='Answer for an isolated deterministic CAPTCHA fixture only.')
parser.add_argument('--no-screenshots',action='store_true',help='Run functional checks without optional page captures.')
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
account=next(line.split(':') for line in (args.account_file or root/'users.txt').read_text(encoding='utf-8').splitlines() if line and not line.startswith('#'))
artifacts=root/'verification'
artifacts.mkdir(exist_ok=True)
def save_screenshot(**kwargs):
    if not args.no_screenshots:
        page.screenshot(**kwargs)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--disable-gpu','--disable-renderer-backgrounding',
        '--disable-backgrounding-occluded-windows','--disable-background-timer-throttling',
        '--disable-features=CalculateNativeWinOcclusion'])
    page=browser.new_page(viewport=dict(width=1440,height=1100))
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(args.url)
    page.locator('#login-form').wait_for()
    save_screenshot(path=str(artifacts/'login-desktop.png'),full_page=True)
    if not args.captcha_answer:raise RuntimeError('Browser automation needs the isolated test CAPTCHA fixture.')
    page.set_viewport_size(dict(width=390,height=844))
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Login mobile overflow'
    page.set_viewport_size(dict(width=1440,height=1100))
    page.click('#auth-register')
    page.fill('#username','browser_'+__import__('uuid').uuid4().hex[:10])
    page.fill('#password','Browser test passphrase 123!')
    page.fill('#confirm-password','Browser test passphrase 123!')
    expect(page.locator('#sign-in')).to_be_enabled()
    page.fill('#captcha-answer','WRONG')
    page.click('#sign-in')
    expect(page.locator('#login-error')).to_contain_text('incorrect or expired')
    expect(page.locator('#sign-in')).to_be_enabled()
    page.fill('#captcha-answer',args.captcha_answer)
    page.click('#sign-in')
    expect(page.locator('#shell')).to_be_visible()
    expect(page.locator('#view-guide')).to_be_visible()
    assert page.evaluate('state.user.role')=='participant'
    page.click('#logout')
    page.click('#auth-login')
    expect(page.locator('#sign-in')).to_be_enabled()
    page.fill('#username',account[0]);page.fill('#password',account[1])
    page.fill('#captcha-answer',args.captcha_answer)
    page.click('#sign-in')
    page.locator('#shell').wait_for(state='visible')
    expect(page.locator('#view-guide')).to_be_visible()
    save_screenshot(path=str(artifacts/'tutorial-desktop.png'),full_page=True)
    page.click('#begin-tutorial')
    expect(page.locator('#tutorial-lab-banner')).to_be_visible()
    assert 'click Run experiment' in page.locator('#tutorial-lab-banner').inner_text()
    page.locator('#dataset option').nth(12).wait_for(state='attached')
    save_screenshot(path=str(artifacts/'laboratory-desktop.png'),full_page=True)
    injected={'count':0}
    def temporary_throttle(route):
        if route.request.method=='GET' and injected['count']==0:
            injected['count']+=1
            route.fulfill(status=429,headers={'Content-Type':'application/json','Retry-After':'1'},body='{"detail":"Temporary test throttle"}')
        else:route.continue_()
    page.route('**/api/experiments/*',temporary_throttle)
    page.click('#tutorial-run-now')
    expect(page.locator('#result-content')).to_be_visible(timeout=60000)
    assert injected['count']==1
    page.unroute('**/api/experiments/*',temporary_throttle)
    expect(page.locator('#tutorial-lab-banner')).to_contain_text('Now read the figures.')
    expect(page.locator('#explanation-summary')).to_contain_text('The prediction responded to Bridge Width')
    assert page.locator('.explanation-concept').count()==3
    with page.expect_download() as saved:
        page.click('#download-explanation')
    explanation=Path(saved.value.path()).read_text(encoding='utf-8')
    assert 'Original prediction: 8' in explanation and 'Normalized impact: +8' in explanation
    checks=page.evaluate('''() => {
      const invalid=structuredClone(state.result);
      invalid.rows.forEach(r=>{r.valid_for_analysis=false;r.reason='Infeasible';r.status='edge_count_infeasible';r.prediction_change=null;r.impact=null;});
      const noop=structuredClone(state.result);
      noop.rows.forEach(r=>{r.noop=true;r.prediction_change=0;r.impact=0;});
      return [explanationContent(invalid).summary,explanationContent(noop).summary];
    }''')
    assert 'cannot support a concept explanation' in checks[0]
    assert 'does not establish concept sensitivity' in checks[1]
    assert page.locator('.figure-card').count()==4
    assert page.locator('.figure-card .easy-meaning').count()==4
    expect(page.locator('#impact-0').locator('..')).to_contain_text('The model’s answer went from 8 to 9')
    with page.expect_download() as saved:
        page.locator('[data-save-svg="prediction-changes"]').click()
    assert saved.value.suggested_filename.endswith('.svg')
    assert '<svg' in Path(saved.value.path()).read_text(encoding='utf-8')
    with page.expect_download() as saved:
        page.locator('[data-save-png="prediction-changes"]').click()
    assert saved.value.suggested_filename.endswith('.png')
    assert Path(saved.value.path()).read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    save_screenshot(path=str(artifacts/'results-desktop.png'),full_page=True)
    for tab in ('network','trajectory','program'):
        page.click(f'[data-result="{tab}"]')
        assert page.locator('#result-body').inner_text()
        if tab=='network':
            expect(page.locator('#result-body .easy-meaning')).to_contain_text('connections')
            assert page.locator('#network-change option').count()==6
            page.select_option('#network-change','1')
            save_screenshot(path=str(artifacts/'network-comparison.png'),full_page=True)
        if tab=='trajectory':
            assert page.locator('#result-body .easy-meaning').count()==1
            page.select_option('#history-change','1')
            page.select_option('#trajectory-metric','edges')
            save_screenshot(path=str(artifacts/'history-comparison.png'),full_page=True)
    assert 'makeScenario' in page.locator('#generated-code').input_value()
    page.click('[data-result="relationships"]')
    assert page.locator('#result-body .figure-card').count()==3
    assert page.locator('#relationship-change option').count()==6
    counts=page.evaluate('relationData(visualComparisons()[0])')
    assert counts['before'][0][1]==8 and counts['after'][0][1]==9
    assert sum(counts['sizes'])==20
    page.click('[data-result="figures"]')
    page.click('#open-live-figures')
    expect(page.locator('#result-body')).to_contain_text('No saved paper image is used here')
    assert page.locator('.live-figure-section').count()>=6
    assert page.locator('#live-node-network svg').count()==1
    assert page.locator('#live-edge-time svg').count()==1
    page.locator('.live-figure-section').nth(3).locator('summary').click()
    assert page.locator('[id^="live-beeswarm-"] svg').count()==3
    assert page.locator('[id^="live-boxplot-"] svg').count()==3
    with page.expect_download() as saved:
        page.locator('[data-save-svg="live-beeswarm-0"]').click()
    assert '<svg' in Path(saved.value.path()).read_text(encoding='utf-8')
    page.click('[data-result="relationships"]')
    page.select_option('#relationship-change','1')
    save_screenshot(path=str(artifacts/'relationships-desktop.png'),full_page=True)
    page.evaluate('state.savedComparisons=state.result.comparisons;delete state.result.comparisons')
    page.click('[data-result="trajectory"]')
    assert 'older saved experiment' in page.locator('#result-body').inner_text()
    page.click('[data-result="network"]')
    assert page.locator('#network-comparison svg').count()==1
    page.evaluate('state.result.comparisons=state.savedComparisons')
    page.evaluate('state.savedAnalyses=state.result.analyses;delete state.result.analyses')
    page.click('[data-result="detailed"]')
    expect(page.locator('#result-body')).to_contain_text('Run it again')
    page.evaluate('state.result.analyses=state.savedAnalyses')
    page.locator('#custom-details summary').click()
    page.click('#custom-starter')
    page.click('#run')
    expect(page.locator('#run')).to_be_enabled(timeout=60000)
    assert not page.locator('#experiment-error').inner_text(),page.locator('#experiment-error').inner_text()
    assert 'Remove one edge' in page.locator('#result-body').inner_text()
    page.click('[data-result="concepts"]')
    assert page.locator('.concept-result').count()==4
    assert page.locator('.direction-cell .easy-meaning').count()==8
    page.fill('#custom-code','')
    if not page.locator('#seed').is_visible():
        page.locator('details').filter(has=page.locator('#seed')).locator('summary').click()
    for dataset,model,delta,seed in [('decaying-bridge','trend_bridge',25,17),('bitcoin-alpha','persistence_density',2,0),('three_communities','slope_bridge',50,42)]:
        # Use an available real fixture rather than assume punctuation in its ID.
        if dataset=='bitcoin-alpha':
            dataset=page.evaluate("state.catalogue.datasets.find(d=>d.family==='real').id")
        page.select_option('#dataset',dataset);page.select_option('#model',model)
        page.locator('#delta').evaluate('(el,v)=>{el.value=v;el.dispatchEvent(new Event("input",{bubbles:true}));}',str(delta))
        page.fill('#seed',str(seed));page.click('#run')
        expect(page.locator('#run')).to_be_enabled(timeout=60000)
        assert not page.locator('#experiment-error').inner_text(),page.locator('#experiment-error').inner_text()
        actual=page.evaluate('state.result.spec')
        assert actual['dataset']==dataset and actual['model']==model and actual['seed']==seed and actual['delta']==delta/100
        page.click('[data-result="detailed"]')
        assert page.locator('#result-body svg').count()>0

    page.click('[data-view="examples"]')
    assert page.locator('.example-card').count()==6
    page.click('[data-view="guide"]')
    assert page.locator('.guide-step').count()==5
    page.click('[data-view="docs"]')
    expect(page.locator('#view-docs .page-help[open]')).to_have_count(1)
    assert 'Supported Python subset' in page.locator('#docs-content').inner_text()
    page.click('[data-view="publication"]')
    expect(page.locator('.publication-card')).to_have_count(12)
    expect(page.locator('.publication-card img').first).to_be_visible()
    expect(page.locator('.publication-card img').first).to_have_js_property('complete',True)
    assert page.locator('.publication-card img').first.evaluate('(img)=>img.complete && img.naturalWidth>0')
    save_screenshot(path=str(artifacts/'publication-desktop.png'))
    page.click('[data-view="study"]')
    assert 'recorded pilot' in page.locator('#study-content').inner_text()
    page.set_viewport_size(dict(width=390,height=844))
    page.click('[data-view="guide"]')
    save_screenshot(path=str(artifacts/'tutorial-mobile.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Tutorial mobile horizontal overflow'
    page.click('[data-view="laboratory"]')
    page.click('[data-result="figures"]')
    save_screenshot(path=str(artifacts/'laboratory-mobile.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile horizontal overflow'
    page.click('[data-result="relationships"]')
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Relationships mobile overflow'
    page.click('[data-result="detailed"]')
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Live figures mobile overflow'
    page.click('[data-view="publication"]')
    expect(page.locator('.publication-card')).to_have_count(12)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Publication mobile overflow'
    browser.close()
    if errors:raise AssertionError(errors)
    print('Browser verified: tutorial-first login, figures, SVG/PNG exports, network/history selectors, numeric/custom results, examples, page instructions, docs, study and mobile layout; no JavaScript errors.')
