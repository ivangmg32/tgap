'use strict';
async function renderPublication(){
  const host=$('publication-content');host.innerHTML='<p class="muted">Loading publication figures…</p>';
  try{const data=await api('/publication');host.innerHTML=`<div class="publication-gallery">${data.figures.map(f=>`<article class="publication-card"><div class="publication-heading"><span class="eyebrow">PAPER FIGURE · REFERENCE</span><h2>${esc(f.title)}</h2><p>${esc(f.description)}</p></div><a href="/api/publication/${esc(f.id)}/png" target="_blank" rel="noopener" aria-label="Open ${esc(f.title)} at full size"><img src="/api/publication/${esc(f.id)}/png" alt="${esc(f.title)}. ${esc(f.description)}" loading="lazy"></a>${easyBlock(f.description)}<p class="publication-scope"><strong>Reading scope:</strong> ${esc(f.scope)}</p><div class="publication-links">${f.formats.map(kind=>`<a class="secondary" href="/api/publication/${esc(f.id)}/${kind}" target="_blank" rel="noopener">Open ${kind.toUpperCase()}${kind==='png'?' at full size':''}</a>`).join('')}</div><details><summary>Figure provenance</summary><p>Source: <code>${esc(f.source)}</code></p><p>SHA256: <code>${esc(f.sha256)}</code></p>${f.metadata.comparability_scope?`<p>${esc(f.metadata.comparability_scope)}</p>`:''}</details></article>`).join('')||'<p>No publication figures have been bundled yet.</p>'}</div>`;}catch(error){host.innerHTML=`<p class="error-text">${esc(error.message)}</p>`;}
}
function relationData(comparison){
  const nodes=state.result.graph.nodes,n=state.result.summary.communities,index=new Map(nodes.map(node=>[String(node.id),node.community]));
  function counts(edges){const matrix=Array.from({length:n},()=>Array(n).fill(0));for(const[a,b]of edges){const i=index.get(String(a)),j=index.get(String(b));if(i===undefined||j===undefined)continue;matrix[i][j]++;if(i!==j)matrix[j][i]++;}return matrix;}
  const before=counts(state.result.graph.edges),after=counts(comparison.edges),sizes=Array(n).fill(0);nodes.forEach(node=>sizes[node.community]++);
  return {n,before,after,sizes};
}
function communityFigure(data){
  const {n,before,after,sizes}=data;let content='';
  function panel(matrix,offset,title){
    const points=Array.from({length:n},(_,i)=>({x:offset+180+Math.cos(2*Math.PI*i/n-Math.PI/2)*105,y:170+Math.sin(2*Math.PI*i/n-Math.PI/2)*105}));
    content+=`<text x="${offset+180}" y="23" text-anchor="middle" font-size="18" fill="#29445f">${title}</text>`;
    const max=Math.max(...matrix.flat(),1);
    for(let i=0;i<n;i++)for(let j=i+1;j<n;j++){if(!matrix[i][j])continue;const a=points[i],b=points[j];content+=`<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="#7b9ebd" stroke-width="${1+7*matrix[i][j]/max}"/><rect x="${(a.x+b.x)/2-17}" y="${(a.y+b.y)/2-12}" width="34" height="24" rx="4" fill="white"/><text x="${(a.x+b.x)/2}" y="${(a.y+b.y)/2+5}" text-anchor="middle" font-size="16" fill="#29445f">${matrix[i][j]}</text>`;}
    points.forEach((p,i)=>{content+=`<circle cx="${p.x}" cy="${p.y}" r="31" fill="${colors[i%colors.length]}" stroke="white" stroke-width="3"/><text x="${p.x}" y="${p.y-2}" text-anchor="middle" fill="white" font-size="18">C${i+1}</text><text x="${p.x}" y="${p.y+16}" text-anchor="middle" fill="white" font-size="12">${sizes[i]} nodes</text><text x="${p.x}" y="${p.y+50}" text-anchor="middle" fill="#566b82" font-size="13">${matrix[i][i]} internal ties</text>`;});
  }
  panel(before,0,'Original communities');panel(after,360,'Transformed communities');
  return svgFrame('Community relationships in the last snapshot',content,720,355);
}
function relationshipMatrix(data){
  const {n,before,after}=data,size=78,width=130+n*size;let content='';
  for(let i=0;i<n;i++){content+=`<text x="${110+i*size+size/2}" y="30" text-anchor="middle" font-size="17" fill="#29445f">C${i+1}</text><text x="82" y="${55+i*size+size/2}" text-anchor="end" font-size="17" fill="#29445f">C${i+1}</text>`;for(let j=0;j<n;j++){const change=after[i][j]-before[i][j];content+=`<rect x="${110+j*size}" y="${45+i*size}" width="${size-3}" height="${size-3}" fill="${change>0?'#d5ece5':change<0?'#f7e1cd':'#eef3f8'}" rx="5"/><text x="${110+j*size+size/2}" y="${45+i*size+size/2+5}" text-anchor="middle" font-size="17" fill="#29445f">${before[i][j]} → ${after[i][j]}</text>`;}}
  return svgFrame('Connection counts between communities',content,width,65+n*size);
}
function degreeFigure(comparison){
  const nodes=state.result.graph.nodes,degree=new Map(nodes.map(node=>[String(node.id),0]));comparison.edges.forEach(([a,b])=>{degree.set(String(a),(degree.get(String(a))||0)+1);degree.set(String(b),(degree.get(String(b))||0)+1);});
  const max=Math.max(...nodes.map(node=>Math.max(node.degree,degree.get(String(node.id)))),1),x=v=>90+v/max*535,y=v=>275-v/max*220;let content='';
  for(let i=0;i<5;i++){const value=max*i/4;content+=`<line x1="90" x2="625" y1="${y(value)}" y2="${y(value)}" stroke="#e4edf5"/><text x="77" y="${y(value)+5}" text-anchor="end" font-size="15" fill="#566b82">${number(value)}</text><text x="${x(value)}" y="302" text-anchor="middle" font-size="15" fill="#566b82">${number(value)}</text>`;}
  content+=`<line x1="${x(0)}" y1="${y(0)}" x2="${x(max)}" y2="${y(max)}" stroke="#97acbf" stroke-dasharray="6 4"/>`;
  nodes.forEach(node=>{const after=degree.get(String(node.id));content+=`<circle cx="${x(node.degree)}" cy="${y(after)}" r="4.5" fill="${colors[node.community%colors.length]}" opacity=".65"><title>${esc(node.id)}: ${node.degree} → ${after} connections</title></circle>`;});
  content+='<text x="355" y="333" text-anchor="middle" font-size="17" fill="#566b82">Connections per node before the change</text><text x="21" y="165" transform="rotate(-90 21 165)" text-anchor="middle" font-size="17" fill="#566b82">Connections after the change</text>';
  return svgFrame('Node connections before and after',content,720,350);
}
function renderRelationships(index=0){
  const comparison=visualComparisons()[index],data=relationData(comparison),nodes=state.result.graph.nodes;
  const degrees=new Map(nodes.map(n=>[String(n.id),0]));comparison.edges.forEach(([a,b])=>{degrees.set(String(a),(degrees.get(String(a))||0)+1);degrees.set(String(b),(degrees.get(String(b))||0)+1);});
  const changed=nodes.filter(n=>n.degree!==degrees.get(String(n.id))).length;
  const scope=comparison.valid_for_analysis?'These figures show the actual graph relationships in this test, not individual node or edge importance.':'This change failed its validity checks. These relationships are diagnostic and cannot support a valid model explanation.';
  $('result-body').innerHTML='<div class="visual-intro"><h3>How are the graph’s parts connected?</h3><p>Explore community ties and node connections for the selected change. These are structural relationships in the last snapshot.</p></div>'+comparisonTools('relationship-change',index)+figureCard('community-relationships',`${comparison.concept} · ${comparison.direction}`,'Community circles summarize the full graph.',communityFigure(data),'Line labels count cross-community ties; thicker lines represent more ties within each panel. C1, C2, … match the community colors in Network.','Each circle is a group of nodes. A line means the groups have connections between them. Read the numbers to compare before and after; a thicker line is not an importance score.')+figureCard('community-matrix','Connections between each pair of groups','Each cell reads original count → transformed count.',relationshipMatrix(data),'Diagonal cells count internal ties once. Off-diagonal cells mirror the same cross-community ties; do not add both halves.','Green cells gained connections; orange cells lost connections. Gray cells stayed the same. The numbers describe graph structure, not model prediction values.')+figureCard('node-degree-relationships','Who gained or lost connections?','All nodes are included; hover over a point to inspect it.',degreeFigure(comparison),'Several nodes can occupy the same point. The dashed diagonal marks an unchanged number of connections.',`${changed} of ${nodes.length} nodes changed their number of connections. Points above the dashed line gained connections; points below it lost connections. Points on the line kept the same count, even if their neighbors changed.`)+`<p class="result-note">${esc(scope)} Open the explanation above for how the model responded, or History to inspect earlier snapshots.</p>`;
  $('relationship-change').onchange=e=>renderRelationships(Number(e.target.value));wireFigureDownloads();
}
