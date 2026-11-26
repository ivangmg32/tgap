/* TGAP network comparison. Cytoscape owns topology, interaction and Canvas rendering;
 * a screen-space label layer keeps names legible without moving graph coordinates. */
'use strict';
window.TgapNetwork = (() => {
  const palette = ['#4b71a5', '#31958b', '#a67c39', '#8d6da9', '#668d46', '#b46888'];
  const colors = {added:'#2463b4', removed:'#b95628', unchanged:'#bbc9d9', selected:'#152d49'};
  const models = new WeakMap(), entries = new Map();
  let serial = 0, active = null;
  const html = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const edgeKey = e => JSON.stringify(e.map(String).sort());
  const nameOf = n => String(n.label ?? n.name ?? n.id);
  const colorOf = n => palette[((Number(n.community)||0)%palette.length+palette.length)%palette.length];
  const nodeId = id => 'n:' + String(id);
  const nodeName = (m,id) => nameOf(m.nodes.get(String(id)) || {id});
  const badge = status => `<span class="nx-badge nx-${status}">${status === 'added' ? '+ Added' : status === 'removed' ? '− Removed' : 'Unchanged'}</span>`;

  function modelFor(view) {
    if (models.has(view)) return models.get(view);
    const nodes = new Map(view.nodes.map(n => [String(n.id),n]));
    const keys = new Set();
    view.snapshots.forEach(s => [...s.edges,...s.added,...s.removed].forEach(e=>keys.add(edgeKey(e))));
    const ids = new Map([...keys].sort().map((key,i)=>[key,'E'+(i+1)]));
    const xs = view.nodes.map(n=>Number(n.x)).filter(Number.isFinite), ys = view.nodes.map(n=>Number(n.y)).filter(Number.isFinite);
    let xmin=Infinity,xmax=-Infinity,ymin=Infinity,ymax=-Infinity;
    xs.forEach(x=>{xmin=Math.min(xmin,x);xmax=Math.max(xmax,x);});
    ys.forEach(y=>{ymin=Math.min(ymin,y);ymax=Math.max(ymax,y);});
    const span = Math.max(xmax-xmin,ymax-ymin) || 1;
    const positions = new Map(view.nodes.map((n,i)=>[String(n.id), {
      x:Number.isFinite(Number(n.x)) ? (Number(n.x)-(xmin+xmax)/2)/span*1000 : Math.cos(i*2.39996)*Math.sqrt(i+1)*14,
      y:Number.isFinite(Number(n.y)) ? (Number(n.y)-(ymin+ymax)/2)/span*1000 : Math.sin(i*2.39996)*Math.sqrt(i+1)*14,
    }]));
    const snapshots = view.snapshots.map(s => {
      const removed = new Set(s.removed.map(edgeKey)), added = new Set(s.added.map(edgeKey));
      const edges = [...new Map([...s.edges,...s.removed,...s.added].map(e=>[edgeKey(e),e])).entries()].map(([key,e])=>({key,id:ids.get(key),u:String(e[0]),v:String(e[1]),status:removed.has(key)?'removed':added.has(key)?'added':'unchanged'}));
      const byKey=new Map(edges.map(e=>[e.key,e])), adjacent=new Map(view.nodes.map(n=>[String(n.id),[]]));
      const touched = new Set();
      edges.forEach(e=>{
        adjacent.get(e.u)?.push(e); if(e.u!==e.v) adjacent.get(e.v)?.push(e);
        if(e.status!=='unchanged'){touched.add(e.u);touched.add(e.v);}
      });
      const changes=edges.filter(e=>e.status!=='unchanged');
      return {...s,edges,byKey,adjacent,touched,changes,unchanged:edges.length-changes.length};
    });
    const m={view,nodes,positions,snapshots,ids};models.set(view,m);return m;
  }
  function render(chart,index) {
    active?.destroy(); active=null;
    const m=modelFor(chart.data.view), token=String(++serial);
    const state={index:Math.max(0,Math.min(index ?? m.snapshots.length-1,m.snapshots.length-1)),mode:(m.nodes.size>1500 || m.snapshots[0]?.edges.length>8000)?'overlay':'compare',scope:'all',labels:'auto',node:null,edge:null,page:0,status:'changes',query:'',camera:null};
    entries.set(token,{m,state});
    while(entries.size>8)entries.delete(entries.keys().next().value);
    return `<section class="nx-explorer" data-nx-token="${token}" aria-label="Interactive network comparison">
      <div class="nx-title"><div><span class="nx-eyebrow">NETWORK EXPLORER</span><h4>Follow every connection.</h4><p>The same network. The same positions. See exactly what changed.</p></div><span class="nx-linked">⌁ Linked views</span></div>
      <div class="nx-timeline"><button type="button" data-nx="previous" class="secondary" aria-label="Previous snapshot">← Previous</button><div><label for="nx-time-${token}">Snapshot <strong data-nx="time-label"></strong></label><input id="nx-time-${token}" data-nx="time" type="range" min="0" max="${Math.max(0,m.snapshots.length-1)}" value="${state.index}"><div class="nx-spark" data-nx="spark" aria-label="Change volume by snapshot"></div></div><button type="button" data-nx="next" class="secondary" aria-label="Next snapshot">Next →</button></div>
      <div class="nx-stats" data-nx="stats" role="status"></div>
      <div class="nx-tools"><div class="nx-segment" role="group" aria-label="Network view"><button type="button" data-nx-mode="compare" aria-pressed="${state.mode==='compare'}">Before / After</button><button type="button" data-nx-mode="overlay" aria-pressed="${state.mode==='overlay'}">Changes overlay</button></div><label>Show <select data-nx="scope"><option value="all">Entire network</option><option value="context">Changes + neighbors</option><option value="changes">Changed connections</option><option value="neighborhood">Selected neighborhood</option></select></label><label>Labels <select data-nx="labels"><option value="auto">Adaptive</option><option value="changes">Changes & selection</option><option value="off">Selection only</option></select></label><div class="nx-zoom" role="group" aria-label="Graph zoom"><button type="button" data-nx="zoom-out" aria-label="Zoom out">−</button><button type="button" data-nx="fit">Fit graph</button><button type="button" data-nx="zoom-in" aria-label="Zoom in">+</button><button type="button" data-nx="fit-changes">Focus changes</button></div></div>
      <div class="nx-workspace"><div class="nx-main"><div class="nx-search"><label for="nx-search-${token}">Find a node</label><input type="search" id="nx-search-${token}" data-nx="search" placeholder="Search by name or exact ID…" autocomplete="off"><div class="nx-search-results" data-nx="search-results"></div></div>
      <div class="nx-panels" data-nx="panels">${['before','after','overlay'].map(side=>`<section class="nx-panel" data-nx-side="${side}" ${(state.mode==='overlay'?side!=='overlay':side==='overlay')?'hidden':''}><header><div><span class="nx-panel-dot ${side}"></span><strong>${side==='before'?'Original':side==='after'?'Transformed':'Changes on the network'}</strong></div><span data-nx-count="${side}"></span></header><div class="nx-stage" data-nx-stage="${side}" tabindex="0" role="application" aria-label="${side} network. Drag to pan; pinch or use zoom buttons. Arrow keys pan, plus and minus zoom; Escape clears selection."><div class="nx-cy"></div><canvas class="nx-labels" aria-hidden="true"></canvas><div class="nx-stage-empty" hidden></div><span class="nx-stage-hint">Drag to pan · pinch to zoom</span></div><footer data-nx-footer="${side}"></footer></section>`).join('')}</div>
      <div class="nx-legend"><span><i class="nx-line added"></i>Added</span><span><i class="nx-line removed"></i>Removed</span><span><i class="nx-line unchanged"></i>Unchanged</span><span><i class="nx-ring"></i>Changed endpoint</span>${(m.view.community_labels||[]).map((label,i)=>`<span><i class="nx-community" style="background:${palette[i%palette.length]}"></i>${html(label)}</span>`).join('')}</div><p class="nx-help" data-nx="visibility">Names appear as space allows. Zoom or select to inspect. Every node and edge remains available in search and the register.</p></div>
      <aside class="nx-inspector" aria-label="Selected element and changes"><div class="nx-inspector-head"><span class="nx-eyebrow">DETAILS ON DEMAND</span><button type="button" data-nx="clear" class="text-button">Clear</button></div><div data-nx="detail" aria-live="polite"></div><div class="nx-change-nav"><button type="button" data-nx="prev-change" aria-label="Previous changed edge">←</button><span data-nx="change-position">Inspect a change</span><button type="button" data-nx="next-change" aria-label="Next changed edge">→</button></div><h5>Changed connections <span data-nx="change-total"></span></h5><div data-nx="change-list" class="nx-change-list"></div><button type="button" data-nx="more-changes" class="text-button">Show more changes</button></aside></div>
      <details class="nx-register"><summary>Connection register <span data-nx="register-total"></span></summary><div class="nx-register-tools"><label>Connection status <select data-nx="status"><option value="changes">Changes</option><option value="all">All connections</option><option value="added">Added</option><option value="removed">Removed</option><option value="unchanged">Unchanged</option></select></label><label>Find a connection <input type="search" data-nx="edge-search" placeholder="Edge ID or endpoint name"></label><button type="button" data-nx="csv" class="secondary">Download all connections · CSV</button></div><div class="nx-table-scroll"><table class="g-table"><thead><tr><th>Edge</th><th>From</th><th>To</th><th>Status</th><th>Before</th><th>After</th></tr></thead><tbody data-nx="rows"></tbody></table></div><div class="nx-pagination"><button type="button" data-nx="page-prev" class="secondary">← Previous page</button><span data-nx="page-status" role="status"></span><button type="button" data-nx="page-next" class="secondary">Next page →</button></div></details>
    </section>`;
  }

  // Shared screen-space collision index. The renderer and SVG exporter use this
  // same packer: zoom changes label density, never the graph's topology/layout.
  function packLabels(nodes,edges,width,height,measure,options={}) {
    const cells=new Map(),size=40,labels=[],priority=options.priority||new Set();
    const fits=b=>b.x>=6&&b.y>=6&&b.x+b.w<=width-6&&b.y+b.h<=height-6;
    const keys=b=>{const out=[];for(let x=Math.floor(b.x/size);x<=Math.floor((b.x+b.w)/size);x++)for(let y=Math.floor(b.y/size);y<=Math.floor((b.y+b.h)/size);y++)out.push(x+':'+y);return out;};
    const reserve=b=>keys(b).forEach(k=>{if(!cells.has(k))cells.set(k,[]);cells.get(k).push(b);});
    const free=b=>fits(b)&&keys(b).every(k=>(cells.get(k)||[]).every(a=>b.x+b.w+3<a.x||a.x+a.w+3<b.x||b.y+b.h+3<a.y||a.y+a.h+3<b.y));
    const visible=nodes.filter(n=>n.x>=-10&&n.y>=-10&&n.x<=width+10&&n.y<=height+10);
    visible.forEach(n=>reserve({x:n.x-n.r-2,y:n.y-n.r-2,w:2*n.r+4,h:2*n.r+4}));
    const sorted=[...visible].sort((a,b)=>(priority.has(b.id)-priority.has(a.id))||(b.important-a.important)||(b.degree-a.degree)||a.id.localeCompare(b.id));
    const place=(text,x,y,w,h,color,kind,id,anchor)=>{
      const box={x,y,w,h};if(!free(box))return false;
      reserve(box);labels.push({...box,text,color,kind,id,anchor});return true;
    };
    const placeNode = n => {
      if(options.mode==='off'&&!priority.has(n.id))return;
      if(options.mode==='changes'&&!n.important&&!priority.has(n.id))return;
      const full=n.name, maxWidth=priority.has(n.id)?Math.min(width-20,360):Math.min(width*.45,190);
      let chars=Array.from(full),text=full;while(chars.length>1&&measure(text)>maxWidth){chars.pop();text=chars.join('')+'…';}
      const w=measure(text)+12,h=22,d=n.r+5;
      const candidates=[[n.x+d,n.y-h/2],[n.x-w-d,n.y-h/2],[n.x-w/2,n.y-d-h],[n.x-w/2,n.y+d],[n.x+d,n.y+d],[n.x-w-d,n.y-d-h],[n.x+d,n.y-d-h],[n.x-w-d,n.y+d]];
      if (visible.length<=80 || priority.has(n.id) || n.important) {
        const max = priority.has(n.id) ? 180 : 100;
        for(let radius=28;radius<=max;radius+=24) {
          for(const [dx,dy] of [[1,0],[-1,0],[0,-1],[0,1],[.7,.7],[-.7,-.7],[.7,-.7],[-.7,.7]]) candidates.push([n.x+dx*radius-w/2,n.y+dy*radius-h/2]);
        }
      }
      for(const [x,y] of candidates)if(place(text,x,y,w,h,'#203b55','node',n.id,{x:n.x,y:n.y}))break;
    };
    sorted.filter(n=>n.important||priority.has(n.id)).forEach(placeNode);
    // Reserve the selected edge first, then changed edges. Unchanged edge names
    // are shown on selection, so a dense graph doesn't become a wall of text.
    const sortedEdges=[...edges].sort((a,b)=>(Number(b.selected)-Number(a.selected))||a.id.localeCompare(b.id));
    for(const e of sortedEdges){
      if(!e.selected&&(options.mode==='off'||e.status==='unchanged'))continue;
      const text=e.selected?`${e.id} · ${e.status}`:e.id,w=measure(text)+14,h=21;
      const mx=(e.a.x+e.b.x)/2,my=(e.a.y+e.b.y)/2;
      for(const [dx,dy] of [[0,-13],[0,13],[-24,-26],[24,26],[-42,0],[42,0]]){
        if(place(text,mx-w/2+dx,my-h/2+dy,w,h,colors[e.status],'edge',e.key,{x:mx,y:my}))break;
      }
    }
    sorted.filter(n=>!n.important&&!priority.has(n.id)).forEach(placeNode);
    return labels;
  }

  function mount(host,options={}) {
    const root=host?.querySelector('.nx-explorer');if(!root||root._network)return;
    const entry=entries.get(root.dataset.nxToken);if(!entry)return;
    if(typeof cytoscape!=='function'){root.innerHTML='<p role="alert">The graph engine could not load. Reload to try again; full data are available in the JSON export.</p>';return;}
    const {m,state}=entry, cyBySide=new Map(), observers=[];
    let destroyed=false,syncing=false,changeLimit=8,raf=0,searchTimer=0;
    const $=key=>root.querySelector(`[data-nx="${key}"]`), snap=()=>m.snapshots[state.index];
    const sizes=new Map(),labelState=new Map();
    const schedule=()=>{if(!raf)raf=requestAnimationFrame(()=>{raf=0;if(!destroyed)drawLabels();});};
    const cameraOf=cy=>({zoom:cy.zoom(),x:(cy.width()/2-cy.pan().x)/cy.zoom(),y:(cy.height()/2-cy.pan().y)/cy.zoom()});
    const setCamera=(cy,c)=>cy.viewport({zoom:c.zoom,pan:{x:cy.width()/2-c.x*c.zoom,y:cy.height()/2-c.y*c.zoom}});
    function syncFrom(source){
      if(syncing||destroyed)return;syncing=true;state.camera=cameraOf(source);
      cyBySide.forEach(cy=>{if(cy!==source)setCamera(cy,state.camera);});syncing=false;schedule();
    }
    function visibleSide(side){return state.mode==='overlay'?side==='overlay':side!=='overlay';}
    function allowedNodes(){
      const s=snap();if(state.scope==='all')return null;
      let ids=new Set();
      if(state.scope==='neighborhood'){
        if(state.node){ids.add(state.node);(s.adjacent.get(state.node)||[]).forEach(e=>{ids.add(e.u);ids.add(e.v);});}
        else if(state.edge){const e=s.byKey.get(state.edge);if(e){ids.add(e.u);ids.add(e.v);}}
        else return null;
      }else{
        ids=new Set(s.touched);
        if(state.scope==='context')s.touched.forEach(id=>(s.adjacent.get(id)||[]).forEach(e=>{ids.add(e.u);ids.add(e.v);}));
      }
      return ids;
    }
    function edgeVisible(e,side,allowed){
      if(side==='before'&&e.status==='added'||side==='after'&&e.status==='removed')return false;
      if(state.scope==='changes'&&e.status==='unchanged')return false;
      return !allowed||(allowed.has(e.u)&&allowed.has(e.v));
    }
    function elements(side){
      const s=snap(), out=[];
      m.nodes.forEach((n,id)=>out.push({group:'nodes',data:{id:nodeId(id),raw:id,color:colorOf(n),degree:(s.adjacent.get(id)||[]).length},position:m.positions.get(id),classes:s.touched.has(id)?'touched':''}));
      s.edges.forEach(e=>{if(side==='before'&&e.status==='added'||side==='after'&&e.status==='removed')return;
        if(!m.nodes.has(e.u)||!m.nodes.has(e.v))return;
        out.push({group:'edges',data:{id:'edge:'+e.id,source:nodeId(e.u),target:nodeId(e.v),key:e.key,status:e.status},classes:e.status});
      });return out;
    }
    function initStage(stage){
      const side=stage.dataset.nxStage;if(destroyed||cyBySide.has(side)||!visibleSide(side)||stage.clientWidth<2||stage.closest('details:not([open])'))return;
      const dense=m.nodes.size>1200||snap().edges.length>6000;
      const cy=cytoscape({container:stage.querySelector('.nx-cy'),elements:elements(side),layout:{name:'preset',fit:false},minZoom:.04,maxZoom:18,pixelRatio:dense?1:Math.min(devicePixelRatio||1,2),boxSelectionEnabled:false,textureOnViewport:dense,autoungrabify:true,selectionType:'single',desktopTapThreshold:8,touchTapThreshold:12,hideEdgesOnViewport:false,style:[
        {selector:'node',style:{'background-color':'data(color)','width':dense?7:10,'height':dense?7:10,'border-width':1.5,'border-color':'#ffffff','overlay-opacity':0,'label':'','z-index':3}},
        {selector:'node.touched',style:{'border-width':3,'border-color':'#466d96','width':dense?10:14,'height':dense?10:14}},
        {selector:'edge',style:{'width':dense?.65:1.1,'line-color':colors.unchanged,'opacity':dense?.28:.55,'curve-style':'haystack','haystack-radius':0,'overlay-opacity':0,'label':'','z-index':1}},
        {selector:'edge.added',style:{'line-color':colors.added,'width':3,'opacity':1,'z-index':6,'curve-style':'straight'}},
        {selector:'edge.removed',style:{'line-color':colors.removed,'line-style':'dashed','width':3,'opacity':1,'z-index':6,'curve-style':'straight'}},
        {selector:'edge:loop',style:{'curve-style':'bezier','loop-direction':'-45deg','loop-sweep':'60deg'}},
        {selector:'.muted',style:{'opacity':.10}},
        {selector:'edge.focused',style:{'width':4,'opacity':1,'z-index':8}},
        {selector:'node.focused',style:{'border-color':colors.selected,'border-width':3,'width':18,'height':18,'opacity':1,'z-index':9}},
        {selector:'.excluded',style:{'display':'none'}},
      ]});
      cyBySide.set(side,cy);
      cy.on('viewport',()=>syncFrom(cy));cy.on('render',schedule);
      cy.on('tap','node',event=>selectNode(event.target.data('raw'),false));
      cy.on('tap','edge',event=>selectEdge(event.target.data('key'),false));
      cy.on('tap',event=>{if(event.target===cy)clear();});
      let down=null;
      stage.onpointerdown=event=>{down={x:event.clientX,y:event.clientY};};
      stage.onclick=event=>{
        if(!down||Math.hypot(event.clientX-down.x,event.clientY-down.y)>6)return;
        const rect=stage.getBoundingClientRect(),x=event.clientX-rect.left,y=event.clientY-rect.top;
        const label=(labelState.get(side)||[]).find(l=>x>=l.x&&x<=l.x+l.w&&y>=l.y&&y<=l.y+l.h);
        if(label){if(label.kind==='node')selectNode(label.id,false);else selectEdge(label.id,false);}
      };
      cy.on('mouseover','node, edge',()=>stage.style.cursor='pointer');cy.on('mouseout','node, edge',()=>stage.style.cursor='grab');
      stage.onkeydown=event=>{
        if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','+','=','-','Escape','0'].includes(event.key))event.preventDefault();
        if(event.key==='Escape')clear();else if(event.key==='0')fit();else if(event.key==='+'||event.key==='=')zoom(1.4);else if(event.key==='-')zoom(1/1.4);
        else if(event.key.startsWith('Arrow'))cy.panBy({x:event.key==='ArrowLeft'?60:event.key==='ArrowRight'?-60:0,y:event.key==='ArrowUp'?60:event.key==='ArrowDown'?-60:0});
      };
      if(state.camera)setCamera(cy,state.camera);else fit();
      schedule();return true;
    }
    function primary(){return [...cyBySide.entries()].find(([side])=>visibleSide(side))?.[1];}
    function fit(ids){
      const cy=primary();if(!cy)return;
      const collection=ids?cy.collection([...ids].map(id=>cy.getElementById(nodeId(id)))):cy.nodes().filter(n=>!n.hasClass('excluded'));
      if(collection.empty())return;
      cy.fit(collection,Math.min(65,cy.width()*.15));
      if(ids&&cy.zoom()>2.5)cy.zoom({level:2.5,renderedPosition:{x:cy.width()/2,y:cy.height()/2}});
      syncFrom(cy);
    }
    function zoom(ratio){const cy=primary();if(cy)cy.zoom({level:Math.max(cy.minZoom(),Math.min(cy.maxZoom(),cy.zoom()*ratio)),renderedPosition:{x:cy.width()/2,y:cy.height()/2}});}
    function applyFilters(){
      const allowed=allowedNodes(),s=snap(),selected=new Set();
      if(state.node){selected.add(state.node);(s.adjacent.get(state.node)||[]).forEach(e=>{selected.add(e.u);selected.add(e.v);});}
      if(state.edge){const e=s.byKey.get(state.edge);if(e){selected.add(e.u);selected.add(e.v);}}
      cyBySide.forEach((cy,side)=>{
        cy.batch(()=>{
          cy.nodes().forEach(n=>{const id=n.data('raw');n.toggleClass('excluded',!!allowed&&!allowed.has(id));n.toggleClass('focused',id===state.node||!!state.edge&&selected.has(id));n.toggleClass('muted',selected.size>0&&!selected.has(id));});
          cy.edges().forEach(el=>{const e=s.byKey.get(el.data('key'));el.toggleClass('excluded',!edgeVisible(e,side,allowed));const focused=e.key===state.edge||!!state.node&&(e.u===state.node||e.v===state.node);el.toggleClass('focused',focused);el.toggleClass('muted',selected.size>0&&!focused);});
        });
        const visibleEdges=cy.edges().filter(e=>!e.hasClass('excluded')).length;
        const total=side==='before'?s.edges.length-s.added.length:side==='after'?s.edges.length-s.removed.length:s.edges.length;
        const empty=root.querySelector(`[data-nx-stage="${side}"] .nx-stage-empty`);
        empty.hidden=cy.nodes().some(n=>!n.hasClass('excluded'));
        empty.textContent=m.nodes.size?'No changed connections in this snapshot. Choose Entire network to inspect the unchanged network.':'No nodes are available in this network.';
        root.querySelector(`[data-nx-count="${side}"]`).textContent=`${visibleEdges.toLocaleString()} / ${total.toLocaleString()} edges`;
      });
      const visibleNodes=allowed?allowed.size:m.nodes.size;
      $('visibility').textContent=`${visibleNodes.toLocaleString()} of ${m.nodes.size.toLocaleString()} nodes retained by this filter. ${state.scope==='all'?'All connections are retained.':'A view filter is active; the full graph is retained and available under Entire network.'} Labels never overlap; zoom, search or select for exact names. Graph positions stay fixed across snapshots.`;
      schedule();
    }
    function labelItems(cy,side){
      const s=snap(),nodes=[],edges=[],priority=new Set(),allowed=allowedNodes(),pan=cy.pan(),z=cy.zoom();
      if(state.node)priority.add(state.node);
      if(state.edge){const e=s.byKey.get(state.edge);if(e){priority.add(e.u);priority.add(e.v);}}
      const dense=m.nodes.size>1200||s.edges.length>6000;
      const projected=new Map();
      m.nodes.forEach((n,id)=>{
        if(allowed&&!allowed.has(id))return;
        const model=m.positions.get(id),p={x:model.x*z+pan.x,y:model.y*z+pan.y};projected.set(id,p);
        const r=(priority.has(id)?9:s.touched.has(id)?(dense?5:7):(dense?3.5:5))*z;
        nodes.push({id,name:nameOf(n),x:p.x,y:p.y,r:Math.max(2,r),important:s.touched.has(id)?1:0,degree:(s.adjacent.get(id)||[]).length});
      });
      const candidates=state.edge&&s.byKey.get(state.edge)?.status==='unchanged'?[...s.changes,s.byKey.get(state.edge)]:s.changes;
      candidates.forEach(e=>{
        if(!edgeVisible(e,side,allowed))return;
        const a=projected.get(e.u),b=projected.get(e.v);if(a&&b)edges.push({...e,a,b,selected:state.edge===e.key});
      });return {nodes,edges,priority};
    }
    function drawLabels(){
      cyBySide.forEach((cy,side)=>{
        if(!visibleSide(side))return;
        const stage=root.querySelector(`[data-nx-stage="${side}"]`),canvas=stage.querySelector('.nx-labels'),w=stage.clientWidth,h=stage.clientHeight,dpr=Math.min(devicePixelRatio||1,2);
        if(!w||!h)return;
        if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);}
        const ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);ctx.font='600 12px Arial, sans-serif';
        const items=labelItems(cy,side),labels=packLabels(items.nodes,items.edges,w,h,text=>ctx.measureText(text).width,{priority:items.priority,mode:state.labels});
        labels.forEach(l=>{
          const nearest={x:Math.max(l.x,Math.min(l.x+l.w,l.anchor.x)),y:Math.max(l.y,Math.min(l.y+l.h,l.anchor.y))};
          if(Math.hypot(nearest.x-l.anchor.x,nearest.y-l.anchor.y)>13){ctx.beginPath();ctx.moveTo(l.anchor.x,l.anchor.y);ctx.lineTo(nearest.x,nearest.y);ctx.strokeStyle=l.kind==='edge'?l.color:'#9eafc0';ctx.lineWidth=.7;ctx.stroke();}
        });
        labels.forEach(l=>{
          ctx.fillStyle=l.kind==='edge'?'#ffffff':'rgba(255,255,255,.94)';ctx.beginPath();ctx.roundRect(l.x,l.y,l.w,l.h,5);ctx.fill();
          if(l.kind==='edge'){ctx.strokeStyle=l.color;ctx.lineWidth=.8;ctx.stroke();}
          ctx.fillStyle=l.color;ctx.fillText(l.text,l.x+6,l.y+15);
        });
        labelState.set(side,labels);
        const count=labels.filter(l=>l.kind==='node').length;
        const footer=root.querySelector(`[data-nx-footer="${side}"]`);
        const text=`${count.toLocaleString()} node names visible · ${Math.round(cy.zoom()*100)}% zoom · select any connection for endpoints`;
        if(footer.textContent!==text)footer.textContent=text;
      });
    }
    function detail(){
      const s=snap();
      if(state.edge){const e=s.byKey.get(state.edge);if(e){
        $('detail').innerHTML=`${badge(e.status)}<h4>${html(e.id)}</h4><p class="nx-endpoints">${html(nodeName(m,e.u))}<span>↔</span>${html(nodeName(m,e.v))}</p><dl><dt>Before</dt><dd>${e.status==='added'?'Absent':'Present'}</dd><dt>After</dt><dd>${e.status==='removed'?'Absent':'Present'}</dd></dl><button type="button" class="secondary" data-nx="focus-selected">Locate endpoints</button>`;
      }}else if(state.node){
        const n=m.nodes.get(state.node),adj=s.adjacent.get(state.node)||[],added=adj.filter(e=>e.status==='added').length,removed=adj.filter(e=>e.status==='removed').length;
        $('detail').innerHTML=`<span class="nx-badge nx-unchanged">Node retained</span><h4>${html(nameOf(n))}</h4><p class="nx-node-id">ID ${html(state.node)} · ${html(m.view.community_labels?.[n.community]||'')}</p><dl><dt>Before degree</dt><dd>${adj.length-added}</dd><dt>After degree</dt><dd>${adj.length-removed}</dd><dt>Connections changed</dt><dd>+${added} / −${removed}</dd></dl><button type="button" class="secondary" data-nx="node-neighborhood">Explore neighbors</button>`;
      }else $('detail').innerHTML='<div class="nx-empty-icon">⌖</div><h4>Inspect the network</h4><p>Select a node or connection for its exact name, endpoints and before/after status. Search also finds nodes whose labels are hidden.</p>';
      const focus=$('focus-selected');if(focus)focus.onclick=()=>{const e=s.byKey.get(state.edge);if(e)fit(new Set([e.u,e.v]));};
      const neighbor=$('node-neighborhood');if(neighbor)neighbor.onclick=()=>{state.scope='neighborhood';$('scope').value=state.scope;applyFilters();fit(allowedNodes());};
      const index=s.changes.findIndex(e=>e.key===state.edge);
      $('change-position').textContent=index<0?`${s.changes.length} changes`:`Change ${index+1} / ${s.changes.length}`;
      $('prev-change').disabled=$('next-change').disabled=!s.changes.length;
      $('change-total').textContent=s.changes.length;
      $('change-list').innerHTML=s.changes.length?s.changes.slice(0,changeLimit).map(e=>`<button type="button" class="nx-change-item ${state.edge===e.key?'is-selected':''}" data-nx-edge="${html(e.key)}"><span>${badge(e.status)}<small>${html(e.id)}</small></span><strong>${html(nodeName(m,e.u))}<span> ↔ </span>${html(nodeName(m,e.v))}</strong></button>`).join(''):'<p class="nx-quiet">No connections changed in this snapshot.</p>';
      $('more-changes').hidden=s.changes.length<=changeLimit;
      root.querySelectorAll('[data-nx-edge]').forEach(b=>b.onclick=()=>selectEdge(b.dataset.nxEdge,true));
    }
    function selectEdge(key,focus){state.edge=key;state.node=null;applyFilters();detail();register();if(focus){const e=snap().byKey.get(key);if(e)fit(new Set([e.u,e.v]));}}
    function selectNode(id,focus){state.node=id;state.edge=null;applyFilters();detail();register();if(focus)fit(new Set([id]));}
    function clear(){state.node=null;state.edge=null;if(state.scope==='neighborhood'){state.scope='all';$('scope').value='all';}applyFilters();detail();register();}
    function register(){
      const s=snap(),q=state.query.toLocaleLowerCase();
      const filtered=s.edges.filter(e=>(state.status==='all'||state.status==='changes'&&e.status!=='unchanged'||state.status===e.status)&&(!q||[e.id,nodeName(m,e.u),nodeName(m,e.v),e.u,e.v].some(v=>v.toLocaleLowerCase().includes(q))));
      const pages=Math.max(1,Math.ceil(filtered.length/30));state.page=Math.max(0,Math.min(state.page,pages-1));
      $('rows').innerHTML=filtered.slice(state.page*30,state.page*30+30).map(e=>`<tr><td><button type="button" class="text-button" aria-label="Inspect ${html(e.id)}" data-nx-register-edge="${html(e.key)}">${html(e.id)}</button></td><td>${html(nodeName(m,e.u))}</td><td>${html(nodeName(m,e.v))}</td><td>${badge(e.status)}</td><td>${e.status==='added'?'Absent':'Present'}</td><td>${e.status==='removed'?'Absent':'Present'}</td></tr>`).join('')||'<tr><td colspan="6">No connections match this filter.</td></tr>';
      $('register-total').textContent=`· ${s.edges.length.toLocaleString()} total`;
      $('page-status').textContent=`${filtered.length.toLocaleString()} matching · page ${state.page+1} / ${pages}`;
      $('page-prev').disabled=state.page===0;$('page-next').disabled=state.page===pages-1;
      root.querySelectorAll('[data-nx-register-edge]').forEach(b=>b.onclick=()=>selectEdge(b.dataset.nxRegisterEdge,true));
    }
    function snapshot(index){
      state.index=Math.max(0,Math.min(index,m.snapshots.length-1));state.edge=null;state.node=null;state.page=0;changeLimit=8;
      options.onSnapshot?.(state.index);
      cyBySide.forEach((cy,side)=>{cy.batch(()=>{cy.elements().remove();cy.add(elements(side));});});
      updateSummary();applyFilters();detail();register();
    }
    function updateSummary(){
      const s=snap();$('time').value=state.index;$('time-label').textContent=`${state.index+1} / ${m.snapshots.length} · ${s.label}`;
      $('previous').disabled=state.index===0;$('next').disabled=state.index===m.snapshots.length-1;
      $('stats').innerHTML=`<div><b>${m.nodes.size.toLocaleString()}</b><span>nodes retained</span></div><div class="nx-stat-added"><b>+${s.added.length.toLocaleString()}</b><span>added connections</span></div><div class="nx-stat-removed"><b>−${s.removed.length.toLocaleString()}</b><span>removed connections</span></div><div><b>${s.unchanged.toLocaleString()}</b><span>unchanged connections</span></div>`;
      const max=Math.max(1,...m.snapshots.map(s=>s.changes.length));
      $('spark').innerHTML=m.snapshots.map((s,i)=>`<button type="button" data-nx-snapshot="${i}" aria-label="Snapshot ${i+1}, ${html(s.label)}, ${s.changes.length} changes" aria-current="${i===state.index?'step':'false'}"><i style="height:${4+16*s.changes.length/max}px"></i></button>`).join('');
      root.querySelectorAll('[data-nx-snapshot]').forEach(b=>b.onclick=()=>snapshot(Number(b.dataset.nxSnapshot)));
    }
    root.querySelectorAll('[data-nx-mode]').forEach(b=>b.onclick=()=>{
      state.mode=b.dataset.nxMode;
      root.querySelectorAll('[data-nx-mode]').forEach(btn=>btn.setAttribute('aria-pressed',String(btn.dataset.nxMode===state.mode)));
      root.querySelectorAll('[data-nx-side]').forEach(p=>{p.hidden=!visibleSide(p.dataset.nxSide);});
      for (const [side,cy] of cyBySide) {
        if(!visibleSide(side)){cy.destroy();cyBySide.delete(side);labelState.delete(side);}
      }
      root.querySelectorAll('.nx-stage').forEach(initStage);
      cyBySide.forEach(cy=>{cy.resize();if(state.camera)setCamera(cy,state.camera);});applyFilters();
    });
    $('scope').onchange=()=>{state.scope=$('scope').value;applyFilters();};
    $('labels').onchange=()=>{state.labels=$('labels').value;schedule();};
    $('previous').onclick=()=>snapshot(state.index-1);$('next').onclick=()=>snapshot(state.index+1);
    $('time').oninput=()=>snapshot(Number($('time').value));
    $('fit').onclick=()=>fit();$('fit-changes').onclick=()=>{if(snap().touched.size)fit(snap().touched);};
    $('zoom-in').onclick=()=>zoom(1.5);$('zoom-out').onclick=()=>zoom(1/1.5);$('clear').onclick=clear;
    $('prev-change').onclick=()=>cycle(-1);$('next-change').onclick=()=>cycle(1);
    function cycle(step){const changes=snap().changes;if(!changes.length)return;const current=changes.findIndex(e=>e.key===state.edge),i=current<0?(step>0?0:changes.length-1):(current+step+changes.length)%changes.length;selectEdge(changes[i].key,true);}
    $('more-changes').onclick=()=>{changeLimit+=8;detail();};
    $('status').onchange=()=>{state.status=$('status').value;state.page=0;register();};
    $('edge-search').oninput=()=>{state.query=$('edge-search').value;state.page=0;register();};
    $('page-prev').onclick=()=>{state.page--;register();};$('page-next').onclick=()=>{state.page++;register();};
    $('search').oninput=()=>{
      clearTimeout(searchTimer);searchTimer=setTimeout(()=>{
        if(destroyed)return;const q=$('search').value.trim().toLocaleLowerCase();
        if(!q){$('search-results').innerHTML='';return;}
        const matches=[...m.nodes.entries()].filter(([id,n])=>id.toLocaleLowerCase().includes(q)||nameOf(n).toLocaleLowerCase().includes(q)).sort(([a],[b])=>Number(b.toLocaleLowerCase()===q)-Number(a.toLocaleLowerCase()===q));
        $('search-results').innerHTML=matches.slice(0,8).map(([id,n])=>`<button type="button" data-nx-node="${html(id)}"><strong>${html(nameOf(n))}</strong><small>ID ${html(id)}</small></button>`).join('')+`<span>${matches.length.toLocaleString()} matches${matches.length>8?' · refine your search':''}</span>`;
        root.querySelectorAll('[data-nx-node]').forEach(b=>b.onclick=()=>{selectNode(b.dataset.nxNode,true);$('search-results').innerHTML='';});
      },100);
    };
    $('search').onkeydown=e=>{if(e.key==='Enter')$('search-results').querySelector('button')?.click();if(e.key==='Escape')$('search-results').innerHTML='';};
    $('csv').onclick=()=>{
      const csv=s=>`"${String(s).replaceAll('"','""')}"`;
      const rows=[['edge_id','source_id','source_name','target_id','target_name','status','before','after'],...snap().edges.map(e=>[e.id,e.u,nodeName(m,e.u),e.v,nodeName(m,e.v),e.status,e.status==='added'?'absent':'present',e.status==='removed'?'absent':'present'])];
      const blob=new Blob(['\ufeff'+rows.map(row=>row.map(csv).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'});
      const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`tgap-connections-snapshot-${state.index+1}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);
    };
    const observer=new ResizeObserver(records=>{
      if(destroyed)return;
      let created=false;
      records.forEach(({target})=>{
        created=!!initStage(target)||created;const cy=cyBySide.get(target.dataset.nxStage);if(!cy||target.clientWidth<2)return;
        const key=target.dataset.nxStage,old=sizes.get(key),size=`${target.clientWidth}:${target.clientHeight}`;
        if(old!==size){sizes.set(key,size);const camera=state.camera;cy.resize();if(camera)setCamera(cy,camera);}
      });if(created)applyFilters();else schedule();
    });
    const onToggle = event => {
      if(event.target instanceof HTMLDetailsElement && event.target.contains(root) && event.target.open) {
        requestAnimationFrame(()=>{if(!destroyed){root.querySelectorAll('.nx-stage').forEach(initStage);cyBySide.forEach(cy=>cy.resize());applyFilters();}});
      }
    };
    document.addEventListener('toggle',onToggle,true);
    observers.push(observer);root.querySelectorAll('.nx-stage').forEach(stage=>{observer.observe(stage);initStage(stage);});
    updateSummary();applyFilters();detail();register();
    const controller={
      destroy(){if(destroyed)return;destroyed=true;document.removeEventListener('toggle',onToggle,true);cancelAnimationFrame(raf);clearTimeout(searchTimer);observers.forEach(o=>o.disconnect());cyBySide.forEach(cy=>cy.destroy());cyBySide.clear();},
      debug(){return {state:{...state},nodes:m.nodes.size,edges:snap().edges.length,renderers:cyBySide.size,positions:[...m.positions],labels:Object.fromEntries(labelState),cameras:[...cyBySide].filter(([s])=>visibleSide(s)).map(([side,cy])=>({side,...cameraOf(cy)})),visibleEdges:Object.fromEntries([...cyBySide].map(([side,cy])=>[side,cy.edges().filter(e=>!e.hasClass('excluded')).length]))};},
      snapshot, selectNode, selectEdge,
    };
    root._network=controller;active=controller;
  }

  function exportSvg(host,provenance='') {
    const root=host.querySelector('.nx-explorer'),entry=entries.get(root?.dataset.nxToken);if(!entry)return '';
    const {m,state}=entry,s=m.snapshots[state.index];
    const W=2200,H=1320,pw=1060,ph=1000,top=145;
    const context=document.createElement('canvas').getContext('2d');context.font='600 13px Arial,sans-serif';
    let svg=`<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" style="font-family:Arial,sans-serif"><rect width="100%" height="100%" fill="#fff"/><text x="40" y="42" font-size="27" font-weight="700" fill="#203b55">Network comparison · ${html(s.label)}</text><text x="40" y="76" font-size="17" fill="#526880">Snapshot ${state.index+1}/${m.snapshots.length} · ${m.nodes.size} nodes retained · +${s.added.length} added · −${s.removed.length} removed · ${s.unchanged} unchanged</text>`;
    let minx=Infinity,miny=Infinity,maxx=-Infinity,maxy=-Infinity;
    m.positions.forEach(p=>{minx=Math.min(minx,p.x);miny=Math.min(miny,p.y);maxx=Math.max(maxx,p.x);maxy=Math.max(maxy,p.y);});
    if(!m.positions.size){minx=miny=0;maxx=maxy=1;}
    const scale=Math.min((pw-160)/(maxx-minx||1),(ph-160)/(maxy-miny||1));
    const projected=new Map([...m.positions].map(([id,p])=>[id,{x:pw/2+(p.x-(minx+maxx)/2)*scale,y:ph/2+(p.y-(miny+maxy)/2)*scale}]));
    ['before','after'].forEach((side,i)=>{
      const offset=40+i*1100;svg+=`<g transform="translate(${offset} ${top})"><rect width="${pw}" height="${ph}" rx="16" fill="#fbfcfe" stroke="#dde5ed"/><text x="24" y="32" font-size="20" font-weight="700" fill="#203b55">${side==='before'?'Original · before':'Transformed · after'}</text>`;
      const edges=s.edges.filter(e=>(side!=='before'||e.status!=='added')&&(side!=='after'||e.status!=='removed')&&projected.has(e.u)&&projected.has(e.v));
      const nodes=[...m.nodes].map(([id,n])=>({id,name:nameOf(n),...projected.get(id),r:s.touched.has(id)?7:4,important:s.touched.has(id)?1:0,degree:(s.adjacent.get(id)||[]).length}));
      const drawEdge=e=>{const a=projected.get(e.u),b=projected.get(e.v);if(e.u===e.v)return `<path d="M ${a.x} ${a.y} C ${a.x-44} ${a.y-64}, ${a.x+44} ${a.y-64}, ${a.x} ${a.y}" fill="none" stroke="${colors[e.status]}" stroke-width="2" ${e.status==='removed'?'stroke-dasharray="7 5"':''}><title>${html(e.id+' · '+nodeName(m,e.u)+' · '+e.status)}</title></path>`;return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="${colors[e.status]}" stroke-width="${e.status==='unchanged'?.7:2.5}" opacity="${e.status==='unchanged'?.35:1}" ${e.status==='removed'?'stroke-dasharray="7 5"':''}><title>${html(e.id+' · '+nodeName(m,e.u)+' ↔ '+nodeName(m,e.v)+' · '+e.status)}</title></line>`;};
      svg+=edges.filter(e=>e.status==='unchanged').map(drawEdge).join('')+edges.filter(e=>e.status!=='unchanged').map(drawEdge).join('');
      svg+=nodes.map(n=>`<circle cx="${n.x}" cy="${n.y}" r="${n.r}" fill="${colorOf(m.nodes.get(n.id))}" stroke="${n.important?'#486888':'white'}" stroke-width="${n.important?2.5:1}"><title>${html(n.name)}</title></circle>`).join('');
      const labelEdges=edges.filter(e=>e.status!=='unchanged'||e.key===state.edge).map(e=>({...e,a:projected.get(e.u),b:projected.get(e.v),selected:e.key===state.edge}));
      const priority=new Set([state.node].filter(Boolean));if(state.edge){const e=s.byKey.get(state.edge);if(e){priority.add(e.u);priority.add(e.v);}}
      const labels=packLabels(nodes,labelEdges,pw,ph-32,text=>context.measureText(text).width,{priority,mode:'auto'});
      labels.forEach(l=>{
        const x=Math.max(l.x,Math.min(l.x+l.w,l.anchor.x)),y=Math.max(l.y,Math.min(l.y+l.h,l.anchor.y));
        if(Math.hypot(x-l.anchor.x,y-l.anchor.y)>13)svg+=`<line x1="${l.anchor.x}" y1="${l.anchor.y}" x2="${x}" y2="${y}" stroke="#9eafc0" stroke-width=".7"/>`;
      });
      labels.forEach(l=>{svg+=`<rect x="${l.x}" y="${l.y}" width="${l.w}" height="${l.h}" rx="4" fill="white" fill-opacity=".96" ${l.kind==='edge'?`stroke="${l.color}"`:''}/><text x="${l.x+6}" y="${l.y+15}" font-size="13" font-weight="600" fill="${l.color}">${html(l.text)}</text>`;});
      svg+=`<text x="24" y="${ph-12}" font-size="13" fill="#526880">Full network · ${edges.length.toLocaleString()} connections · ${labels.filter(l=>l.kind==='node').length} collision-free node labels</text></g>`;
    });
    svg+=`<g transform="translate(40 1190)"><line x1="0" x2="40" y1="0" y2="0" stroke="${colors.added}" stroke-width="3"/><text x="50" y="5" fill="#203b55">Added</text><line x1="150" x2="190" y1="0" y2="0" stroke="${colors.removed}" stroke-width="3" stroke-dasharray="7 5"/><text x="200" y="5" fill="#203b55">Removed</text><text x="360" y="5" fill="#526880">Every edge is retained. Full endpoint names and statuses are available in the connection CSV / JSON.</text></g>`;
    svg+=`<text x="40" y="1235" font-size="14" fill="#526880">${html((m.view.community_labels||[]).map((name,i)=>`${i+1}: ${name}`).join(' · '))}</text><text x="40" y="1270" font-size="14" fill="#526880">${html(provenance.slice(0,250))}</text></svg>`;
    return svg;
  }
  function destroy(){active?.destroy();active=null;entries.clear();}
  return {render,mount,exportSvg,destroy,packLabels};
})();
