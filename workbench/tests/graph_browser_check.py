"""Graph explorer regression and scale checks. Requires Playwright + Chromium.

Runs without a server or participant data. Checks topology, exact diffs, linked
cameras, labels, collapsed cards, mobile/touch behavior and complete exports.
"""
import argparse
import io
import json
import math
from pathlib import Path
import random
import shutil
import tempfile
import time
import zipfile

from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--browser', default=shutil.which('google-chrome') or shutil.which('chromium'))
parser.add_argument('--output', type=Path, default=Path(tempfile.mkdtemp(prefix='tgap-graph-check-')))
parser.add_argument('--skip-scale', action='store_true')
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
root = Path(__file__).resolve().parents[2]


def fixture(count=24, dense=False):
    import networkx as nx
    rng = random.Random(42)
    graph = nx.planted_partition_graph(3, count//3, .45 if not dense else .01, .035 if not dense else .001, seed=42) if not dense else None
    if graph is not None:
        positions = nx.spring_layout(graph, seed=42, iterations=80)
        pairs = [list(e) for e in graph.edges()]
    else:
        positions = {}
        for i in range(count):
            group=i%5
            radius=math.sqrt((i//5+.5)/(count/5))*.4
            angle=i*2.39996
            positions[i]=(math.cos(group*math.tau/5)+radius*math.cos(angle), math.sin(group*math.tau/5)+radius*math.sin(angle))
        pairs_set=set()
        while len(pairs_set)<count*5:
            u=rng.randrange(count);v=(u+rng.choice([5,10,15,20,25,30,35]))%count if rng.random()<.85 else rng.randrange(count)
            if u!=v:pairs_set.add(tuple(sorted((u,v))))
        pairs=[list(e) for e in sorted(pairs_set)]
    pair_set={tuple(sorted(e)) for e in pairs}
    added=[]
    for u in range(min(count,100)):
        v=(u+count//2)%count
        if tuple(sorted((u,v))) not in pair_set:
            added.append([u,v])
        if len(added)>=(25 if dense else 2):break
    removed=pairs[:25 if dense else 2]
    nodes=[dict(id=i,label=('Actor '+str(i) if not dense else 'Researcher '+str(i)),community=i//(count//3) if not dense else i%5,x=float(positions[i][0]),y=float(positions[i][1])) for i in range(count)]
    snapshots=[dict(label='Window 1',edges=pairs,added=added,removed=removed),dict(label='Window 2 · no edits',edges=pairs,added=[],removed=[])]
    return dict(id='local_graph',data=dict(view=dict(nodes=nodes,snapshots=snapshots,community_labels=['Group A','Group B','Group C'] if not dense else ['Team '+str(i+1) for i in range(5)])))


def load(page, chart, collapsed=False):
    page.set_content('<main style="max-width:1520px;margin:24px auto;padding:0 12px"><div id="g-report"></div></main>')
    page.add_style_tag(path=str(root/'workbench/static/style.css'))
    page.evaluate("window.pageHelp={};window.esc=s=>String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));window.$=id=>document.getElementById(id)")
    for name in ['vendor/cytoscape-3.35.0.min.js','network-explorer.js','guided.js']:
        page.add_script_tag(path=str(root/'workbench/static'/name))
    page.evaluate('''({chart,collapsed})=>{
      G.cat={datasets:[],models:[],concepts:[],inventory:{charts:[],groups:[]},glossary:{metrics:{}}};
      chart.status='ok';chart.renderer='network';chart.title='Which connections did TGAP change?';chart.paper='Local graph';chart.explanation=Object.fromEntries(G_PARTS.map(([key])=>[key,'Test fixture']));
      G.job='browser-test';G.snapshot=0;G.result={guided:{spec:{dataset:'Test network',model:'test',direction:'increase',delta:.1,seed:42},selected_concept:'Density',charts:[chart]}};
      $('g-report').innerHTML=gChartCard(chart);document.querySelector('#chart-local_graph').open=!collapsed;gWireResultsInner();
    }''',dict(chart=chart,collapsed=collapsed))
    if not collapsed:
        expected=1 if len(chart['data']['view']['nodes'])>1500 else 2
        page.wait_for_function(f"document.querySelector('.nx-explorer')._network?.debug().renderers==={expected}")
        page.wait_for_function("[...document.querySelectorAll('[data-nx-footer]')].some(e=>e.textContent.includes('node names'))")


def debug(page):
    return page.evaluate("document.querySelector('.nx-explorer')._network.debug()")


def assert_labels(page):
    data=debug(page)
    for side,labels in data['labels'].items():
        for i,a in enumerate(labels):
            for b in labels[i+1:]:
                assert a['x']+a['w']<=b['x'] or b['x']+b['w']<=a['x'] or a['y']+a['h']<=b['y'] or b['y']+b['h']<=a['y'], (side,a,b)


metrics={}
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=args.browser,headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport=dict(width=1740,height=1120),device_scale_factor=1)
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    chart=fixture()
    load(page,chart)
    before=debug(page)
    assert before['nodes']==24
    assert page.locator('[data-g-png="g-fig-local_graph"]').count()==1
    assert page.locator('[data-g-svg="g-fig-local_graph"]').count()==1
    assert before['visibleEdges']['before']==len(chart['data']['view']['snapshots'][0]['edges'])
    assert before['visibleEdges']['after']==len(chart['data']['view']['snapshots'][0]['edges'])
    # Coordinates must remain an affine transform of the supplied spring layout,
    # rather than becoming a grid/circle or being recomputed for each snapshot.
    positions=dict(before['positions']);raw=chart['data']['view']['nodes']
    for axis in ['x','y']:
        ratios=[(positions[str(n['id'])][axis]-positions['0'][axis])/(n[axis]-raw[0][axis]) for n in raw[1:] if abs(n[axis]-raw[0][axis])>1e-9]
        assert max(ratios)-min(ratios)<1e-6
    assert_labels(page)
    page.screenshot(path=str(args.output/'desktop.png'),full_page=True)
    # Names themselves are selectable, not just the tiny node bodies.
    label=next(l for l in debug(page)['labels']['before'] if l['kind']=='node')
    page.locator('[data-nx-stage=before]').click(position=dict(x=label['x']+label['w']/2,y=label['y']+label['h']/2))
    assert debug(page)['state']['node']==label['id']
    page.locator('[data-nx=clear]').click()
    page.locator('[data-nx=zoom-in]').click()
    page.wait_for_timeout(150)
    camera=debug(page)['cameras']
    assert abs(camera[0]['zoom']-camera[1]['zoom'])<1e-6
    assert abs(camera[0]['x']-camera[1]['x'])<1e-6
    # Real drag/pan and keyboard operation, with linked cameras.
    stage=page.locator('[data-nx-stage=before]');box=stage.bounding_box()
    page.mouse.move(box['x']+30,box['y']+30);page.mouse.down();page.mouse.move(box['x']+100,box['y']+70,steps=8);page.mouse.up()
    stage.focus();page.keyboard.press('ArrowLeft')
    camera=debug(page)['cameras'];assert abs(camera[0]['x']-camera[1]['x'])<1e-6
    page.locator('[data-nx=fit]').click()
    page.locator('[data-nx=next-change]').click()
    page.wait_for_timeout(150)
    detail=page.locator('[data-nx=detail]').inner_text()
    assert 'Present' in detail and 'Absent' in detail
    assert_labels(page)
    assert page.locator('[data-nx=change-position]').inner_text().startswith('Change 1 /')
    page.locator('[data-nx=scope]').select_option('changes')
    filtered=debug(page)
    assert filtered['visibleEdges']['before']==2 and filtered['visibleEdges']['after']==2
    page.locator('[data-nx=scope]').select_option('all')
    page.locator('[data-nx-mode=overlay]').click()
    page.wait_for_function("document.querySelector('.nx-explorer')._network.debug().renderers===1")
    assert debug(page)['visibleEdges']['overlay']==len(chart['data']['view']['snapshots'][0]['edges'])+2
    page.screenshot(path=str(args.output/'overlay.png'),full_page=True)
    page.locator('[data-nx=search]').fill('23')
    page.get_by_role('button',name='Actor 23 ID 23',exact=True).click()
    assert debug(page)['state']['node']=='23'
    assert 'Actor 23' in page.locator('[data-nx=detail]').inner_text()
    page.locator('[data-nx=node-neighborhood]').click()
    assert debug(page)['state']['scope']=='neighborhood'
    page.locator('[data-nx=clear]').click()
    original_positions=debug(page)['positions']
    page.get_by_role('button',name='Next snapshot',exact=True).click()
    assert debug(page)['state']['index']==1
    assert debug(page)['positions']==original_positions
    assert page.get_by_role('button',name='Next snapshot',exact=True).is_disabled()
    assert 'No connections changed' in page.locator('[data-nx=change-list]').inner_text()
    page.get_by_role('button',name='Previous snapshot',exact=True).click()
    page.locator('[data-nx=time]').focus();page.keyboard.press('ArrowRight')
    assert debug(page)['state']['index']==1
    assert page.locator('[data-nx=time]').evaluate('(e)=>document.activeElement===e')
    page.keyboard.press('ArrowLeft');assert debug(page)['state']['index']==0
    page.locator('.nx-register>summary').click()
    page.locator('[data-nx=status]').select_option('all')
    assert page.locator('[data-nx=rows] tr').count()<=30
    page.locator('[data-nx=edge-search]').fill('Actor 23')
    assert page.locator('[data-nx=rows]').inner_text().count('Actor 23')>0
    with page.expect_download() as saved:page.locator('[data-nx=csv]').click()
    saved.value.save_as(args.output/'connections.csv')
    assert len((args.output/'connections.csv').read_text(encoding='utf-8-sig').splitlines())==before['edges']+1
    # The full-graph export must work without a mounted/visible renderer.
    svg=page.evaluate("gExportSvg($('g-fig-local_graph'))")
    assert svg.count('<line ')>=before['visibleEdges']['before']+before['visibleEdges']['after']
    (args.output/'network-export.svg').write_text(svg)
    data=page.evaluate("async()=>Array.from(new Uint8Array(await (await gPngBlob($('g-fig-local_graph'))).arrayBuffer()))")
    assert bytes(data).startswith(b'\x89PNG');(args.output/'network-export.png').write_bytes(bytes(data))
    # Bulk export with one network and a collapsed ordinary chart.
    page.evaluate('''()=>{
      window.gEvent=()=>{};window.toast=message=>{throw new Error(message)};
      document.body.insertAdjacentHTML('beforeend','<button id="g-export-images">Export all charts</button><button id="g-report-html"></button><button id="g-print"></button>');
      $('g-report').insertAdjacentHTML('beforeend','<details><div class="figure-canvas" id="g-fig-extra">'+gFrame('Extra chart',gText(20,30,'Test chart'),780,80)+'</div></details>');
      $('g-report').insertAdjacentHTML('beforeend','<div data-chart="reference"><div class="g-published"><img alt="Published reference" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jZp0AAAAASUVORK5CYII="></div></div>');
      gWireResults();
    }''')
    with page.expect_download() as saved:page.locator('#g-export-images').click()
    saved.value.save_as(args.output/'all-charts.zip')
    with zipfile.ZipFile(args.output/'all-charts.zip') as archive:
        assert len(archive.namelist())==3
        assert all(archive.read(name).startswith(b'\x89PNG') for name in archive.namelist())
    page.set_viewport_size(dict(width=390,height=844))
    page.locator('[data-nx-mode=compare]').click()
    page.locator('[data-nx=fit]').click()
    page.wait_for_timeout(200)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert_labels(page)
    page.screenshot(path=str(args.output/'mobile.png'),full_page=True)
    page.locator('[data-nx-mode=overlay]').click()
    assert page.locator('[data-nx-stage=overlay]').bounding_box()['width']<390
    # Hidden chart initialization and export, then opening the chart.
    hidden_page=browser.new_page(viewport=dict(width=1440,height=1000))
    load(hidden_page,chart,collapsed=True)
    assert debug(hidden_page)['renderers']==0
    assert '<line ' in hidden_page.evaluate("gExportSvg($('g-fig-local_graph'))")
    hidden_page.locator('summary').first.click()
    hidden_page.wait_for_function("document.querySelector('.nx-explorer')._network.debug().renderers===2")
    hidden_page.close()
    csp=browser.new_page(viewport=dict(width=1280,height=900));load(csp,chart)
    csp.evaluate('''document.head.insertAdjacentHTML('beforeend',`<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'">`)''')
    assert csp.evaluate("async()=>(await gPngBlob($('g-fig-local_graph'))).size")>1000
    csp.close()
    # Real touch input: pinch changes the graph camera and a touch selection
    # remains available through the same searchable inspector on a phone.
    mobile_context=browser.new_context(viewport=dict(width=390,height=844),has_touch=True,is_mobile=True)
    mobile=mobile_context.new_page();mobile.on('pageerror',lambda e:errors.append(str(e)))
    load(mobile,chart)
    mobile.locator('[data-nx-mode=overlay]').tap()
    stage=mobile.locator('[data-nx-stage=overlay]');stage.scroll_into_view_if_needed();box=stage.bounding_box()
    cdp=mobile_context.new_cdp_session(mobile)
    cx=box['x']+box['width']/2;cy=box['y']+box['height']/2
    old_zoom=debug(mobile)['cameras'][0]['zoom']
    cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':cx-30,'y':cy,'id':1},{'x':cx+30,'y':cy,'id':2}]})
    for distance in [40,55,70]:
        cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':cx-distance,'y':cy,'id':1},{'x':cx+distance,'y':cy,'id':2}]})
    cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
    assert debug(mobile)['cameras'][0]['zoom']>old_zoom
    mobile_context.close()
    # Empty graphs and hostile/long names must not crash or become HTML.
    boundary=browser.new_page(viewport=dict(width=1280,height=900))
    boundary.on('pageerror',lambda e:errors.append(str(e)))
    empty=dict(id='local_graph',data=dict(view=dict(nodes=[],snapshots=[dict(label='Empty',edges=[],added=[],removed=[])],community_labels=[])))
    load(boundary,empty)
    assert debug(boundary)['nodes']==0
    assert 'No nodes' in boundary.locator('[data-nx-side=before]').inner_text()
    boundary.close()
    odd=browser.new_page(viewport=dict(width=1280,height=900));odd.on('pageerror',lambda e:errors.append(str(e)))
    hostile='<img src=x onerror="window.__network_xss=1"> & node'
    long_name='Long researcher name 👩🏽‍🔬 '*20
    odd_chart=dict(id='local_graph',data=dict(view=dict(nodes=[dict(id=0,label=hostile,community=0,x=0,y=0),dict(id=1,label='Isolated participant',community=0,x=1,y=0),dict(id=2,label=long_name,community=0,x=.5,y=1)],snapshots=[dict(label='Boundary cases',edges=[[0,0],[0,1]],removed=[[0,1]],added=[[1,2]])],community_labels=['Group & <test>'])))
    load(odd,odd_chart)
    assert odd.locator('.nx-explorer img').count()==0
    odd.locator('[data-nx=search]').fill('2')
    odd.locator('[data-nx-node="2"]').click()
    assert long_name.strip() in odd.locator('[data-nx=detail]').inner_text()
    assert odd.evaluate('window.__network_xss === undefined')
    assert '<path d="M ' in odd.evaluate("gExportSvg($('g-fig-local_graph'))")
    assert_labels(odd)
    odd.close()
    if not args.skip_scale:
        scale_page=browser.new_page(viewport=dict(width=1740,height=1120))
        scale_page.on('pageerror',lambda e:errors.append(str(e)))
        dense=fixture(5000,dense=True)
        started=time.monotonic();load(scale_page,dense);metrics['5000_nodes_25000_edges_mount_seconds']=round(time.monotonic()-started,3)
        data=debug(scale_page)
        assert data['nodes']==5000 and data['visibleEdges']['overlay']==25025
        assert scale_page.locator('canvas').count()<20
        assert scale_page.locator('[data-nx=rows] tr').count()<=30
        assert scale_page.locator('.nx-change-item').count()<=8
        assert_labels(scale_page)
        started=time.monotonic();scale_page.locator('[data-nx=zoom-in]').click();scale_page.wait_for_timeout(100);metrics['dense_zoom_seconds']=round(time.monotonic()-started,3)
        scale_page.locator('[data-nx=scope]').select_option('changes')
        assert debug(scale_page)['visibleEdges']['overlay']==50
        scale_page.locator('[data-nx=fit-changes]').click()
        scale_page.screenshot(path=str(args.output/'dense-changes.png'),full_page=True)
        scale_page.locator('[data-nx=scope]').select_option('all');scale_page.locator('[data-nx=fit]').click()
        scale_page.screenshot(path=str(args.output/'dense-overview.png'),full_page=True)
        # Pagination must bound DOM size without dropping underlying connections.
        scale_page.locator('.nx-register>summary').click();scale_page.locator('[data-nx=status]').select_option('all')
        assert '25,025 matching' in scale_page.locator('[data-nx=page-status]').inner_text()
        scale_page.locator('[data-nx=page-next]').click()
        assert 'page 2 /' in scale_page.locator('[data-nx=page-status]').inner_text()
        assert scale_page.locator('[data-nx=rows] tr').count()==30
        scale_page.locator('[data-nx-mode=compare]').click()
        data=debug(scale_page)
        assert data['renderers']==2 and data['visibleEdges']['before']==25000 and data['visibleEdges']['after']==25000
        scale_page.close()
    assert not errors,errors
    browser.close()
(args.output/'metrics.json').write_text(json.dumps(metrics,indent=2))
print('PASS: topology, exact changes, linked cameras, pan/zoom, collision-free labels, search, neighborhoods, snapshot navigation, paginated register, collapsed cards, mobile layout, full SVG/PNG, bulk ZIP and dense graph scale')
print(json.dumps(metrics))
