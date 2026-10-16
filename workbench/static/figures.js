'use strict';
function easyResult(row){
  if(!row.valid_for_analysis)return 'This test did not meet the rules for a fair comparison. We cannot use it to explain the model. It does not mean the model had no response.';
  if(row.noop)return 'This attempt did not change the measured feature or the model’s answer. Try a different amount. This test cannot tell us whether the model cares about this feature.';
  if(row.prediction_change===0)return 'We changed the graph, but the model’s answer stayed the same. For this particular change, the model did not respond. A different change could give a different result.';
  const higher=row.prediction_change>0;
  return `The model’s answer went from ${number(row.baseline)} to ${number(row.prediction)}. That is ${number(Math.abs(row.prediction_change))} ${higher?'higher':'lower'}. In this test, changing this feature made the model give a ${higher?'larger':'smaller'} answer.`;
}
function easyBlock(text){return `<div class="easy-meaning"><strong>What this means</strong><p>${esc(text)}</p></div>`;}
function easyConcept(name){return state.result.rows.filter(r=>r.concept===name).map(row=>`${row.direction==='increase'?'Trying to increase':'Trying to decrease'} ${name}: ${easyResult(row)}`).join(' ');}
function easyHistory(comparison,metric){
  if(!comparison.valid_for_analysis)return 'The lines show what happened, but this test failed its checks. Do not use it to draw a conclusion about the model.';
  if(!comparison.trajectory)return 'We only saved the original history for this older run. Run the experiment again to compare the two lines.';
  const before=state.result.trajectory,after=comparison.trajectory;
  const changed=before.filter((r,i)=>Math.abs(r[metric]-after[i][metric])>1e-10).length;
  if(!changed)return 'The two lines match: this measure stayed the same at every time step. Other graph features may still have changed.';
  const oldLast=before.at(-1)[metric],newLast=after.at(-1)[metric];
  return `This measure changed at ${changed} of ${before.length} time steps. ${Math.abs(oldLast-newLast)<1e-10?'The final value stayed the same, so the change is in the past.':`The final value went from ${number(oldLast)} to ${number(newLast)}.`} These lines show the graph’s history; the model’s answer is explained above.`;
}
function explanationContent(result){
  const model=state.catalogue.models.find(m=>m.id===result.spec.model)?.name||result.spec.model;
  const dataset=state.catalogue.datasets.find(d=>d.id===result.spec.dataset)?.name||result.spec.dataset;
  const concepts=[...new Set(result.rows.map(row=>row.concept))].map(name=>{
    const rows=result.rows.filter(row=>row.concept===name),valid=rows.filter(row=>row.valid_for_analysis);
    const moved=valid.some(row=>row.prediction_change!==0),tested=valid.some(row=>!row.noop);
    const status=moved?'Prediction responded':tested?'No response in these tests':valid.length?'No effective change':'No valid evidence';
    const kind=moved?'response':tested?'unchanged':'excluded';
    const observations=rows.map(row=>{
      const direction=row.direction==='increase'?'Increase':'Decrease';
      if(!row.valid_for_analysis)return `${direction}: excluded from the explanation (${row.status.replaceAll('_',' ')}). ${row.reason||'This perturbation did not pass its validity checks.'}`;
      if(row.noop)return `${direction}: the tested request changed neither the measured property nor the prediction. This is a no-op, not evidence that the model ignores this concept.`;
      const achieved=row.achieved_delta===null?'Achieved property change was not measured.':`Achieved property change: ${row.delta_mode==='absolute'?number(row.achieved_delta,true)+' absolute units':number(row.achieved_delta*100,true)+'%'}.`;
      return `${direction}: prediction ${number(row.baseline)} → ${number(row.prediction)} (difference ${number(row.prediction_change,true)}). ${achieved} Normalized impact: ${number(row.impact,true)}${row.normalizer==='requested'?' (requested-change normalization)':''}.`;
    });
    return {name,status,kind,observations,partial:valid.length<rows.length};
  });
  const responded=concepts.filter(c=>c.kind==='response').map(c=>c.name);
  const valid=result.rows.filter(r=>r.valid_for_analysis),effective=valid.filter(r=>!r.noop);
  const summary=responded.length?`The prediction responded to ${responded.join(', ')} in the valid tested changes.`:effective.length?'The prediction stayed unchanged across the valid effective changes tested in this run.':valid.length?'The valid requests produced no effective change, so this run does not establish concept sensitivity.':'None of the tested changes passed validity checks, so this run cannot support a concept explanation.';
  const scope='This explanation describes sensitivity to the selected concepts and tested changes. It does not decompose the baseline into additive contributions or establish real-world causation. Untested concepts may also affect the prediction.';
  return {model,dataset,concepts,summary,scope};
}
function renderExplanation(){
  const r=state.result,e=explanationContent(r);
  let host=$('explanation-summary');if(!host){host=document.createElement('section');host.id='explanation-summary';$('result-content').prepend(host);}
  host.innerHTML=`<div class="explanation-title"><div><span class="eyebrow">TGAP · CONCEPT-LEVEL MODEL EXPLANATION</span><h2>What does this prediction respond to?</h2></div><button class="text-button" id="download-explanation">Save explanation</button></div><p class="explanation-context">Explaining <strong>${esc(e.model)}</strong> on <strong>${esc(e.dataset)}</strong>. The original prediction is <strong>${number(r.baseline)}</strong>.</p><div class="explanation-conclusion"><span>Your explanation</span><p>${esc(e.summary)}</p></div><div class="explanation-evidence">${e.concepts.map(c=>`<article class="explanation-concept ${c.kind}"><div><h3>${esc(c.name)}</h3><span class="explanation-label">${esc(c.status)}</span></div><ul>${c.observations.map(o=>`<li>${esc(o)}</li>`).join('')}</ul>${easyBlock(easyConcept(c.name))}${c.partial?'<p class="partial-evidence">This concept has excluded directions. Interpret only the valid observations above.</p>':''}</article>`).join('')}</div><details class="explanation-scope"><summary>How to interpret this explanation</summary><p>Read each concept in its own perturbation units. Zero prediction response after a real change differs from a no-op. Excluded directions provide no valid quantitative evidence.</p><p>${esc(e.scope)}</p></details><p class="explanation-next">Explore the evidence below: <strong>Figures</strong> visualize responses, <strong>Numbers</strong> show sensitivity scores, and <strong>Network / History</strong> show the graph changes tested.</p>`;
  $('download-explanation').onclick=()=>downloadText(`TGAP explanation of a model prediction\nModel: ${e.model}\nDataset: ${e.dataset}\nOriginal prediction: ${number(r.baseline)}\nSeed: ${r.spec.seed}\nRun: ${r.request_hash}\n\n${e.summary}\n\n${e.concepts.map(c=>`${c.name} — ${c.status}\n${c.observations.join('\n')}`).join('\n\n')}\n\n${e.scope}\n`,'tgap-explanation-'+r.request_hash.slice(0,8)+'.txt','text/plain');
}
const pageHelp = {
  publication:['How to read the paper figures','These charts were generated by the research publication workflow. Read each caption and scope note before interpreting it. Open the full-size PNG for detail or download the PDF. Superseded charts are omitted. For graphs from your own experiment, use the Relationships result tab.'],
  guide:['Learn before you run','Read the overview, then follow the five tutorial steps below. Each step opens a prepared experiment in the Laboratory. You can return here at any time; your results stay saved.'],
  laboratory:['How this page works','Choose an ecosystem and prediction model, select concepts, and set the requested change. Run the experiment, then explore Figures, Numbers, Network, History and Relationships. Download images or export the Python program and data. The custom editor defines an additional graph concept.'],
  examples:['How to use an example','Open a card to load its dataset, model and transformations into the Laboratory. Nothing runs until you press Run experiment. Inspect the figures, then change one setting and run again. Every run is saved to your private history.'],
  study:['How the guided study works','Participation is optional. Read the consent information before starting. Open and run the suggested experiment for each task, inspect its results, and return here to answer. Finish with a custom transformer and your feedback; withdrawal removes your saved records.'],
  docs:['Find the explanation you need','Choose a topic below for definitions, result interpretation, supported custom Python, datasets, local installation and privacy. The tutorial introduces the workflow; this reference explains the details behind it.'],
  researcher:['How to review the pilot','Review participation stages and completion counts, then download sessions, task responses or experiment logs for analysis. Exports use pseudonymous participant IDs. Add or change login accounts in the operator’s users.txt file.']
};
function renderPageHelp(view){
  const section=$('view-'+view);let help=section.querySelector('.page-help');
  if(!help){help=document.createElement('details');help.className='page-help';section.insertBefore(help,section.querySelector('.page-intro, .hero')?.nextSibling||section.firstChild);}
  const [title,text]=pageHelp[view];help.innerHTML=`<summary>${esc(title)} <span>Page instructions</span></summary><p>${esc(text)}</p>`;
  help.open=view!=='guide';
}
function visualComparisons(){
  return state.result.comparisons||[{concept:state.result.graph.transformation,direction:'increase',valid_for_analysis:true,legacy:true,
    edges:state.result.graph.edges.filter(e=>!state.result.graph.removed.some(r=>edgeKey(...r)===edgeKey(...e))).concat(state.result.graph.added),
    added:state.result.graph.added,removed:state.result.graph.removed}];
}
function edgeKey(a,b){return JSON.stringify([String(a),String(b)].sort());}
function svgFrame(title,content,width=720,height=350){
  const r=state.result,caption=`TGAP | ${r.spec.dataset} | ${r.spec.model} | seed ${r.spec.seed} | ${r.request_hash.slice(0,8)}`;
  function wrap(text,size){const max=Math.max(12,Math.floor((width-30)/(size*.62)));const lines=[];let line='';for(const word of text.split(' ')){if(line.length+word.length+1>max&&line){lines.push(line);line='';}if(word.length>max){if(line){lines.push(line);line='';}for(let i=0;i<word.length;i+=max)lines.push(word.slice(i,i+max));}else line+=(line?' ':'')+word;}if(line)lines.push(line);return lines;}
  const titles=wrap(title,18),footers=wrap(caption,14),header=18+titles.length*22,total=header+height+footers.length*18+20;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${total}" role="img" aria-label="${esc(title)}" style="font-family:Arial,sans-serif;background:white"><title>${esc(title)}</title><rect width="${width}" height="${total}" fill="white"/>${titles.map((line,i)=>`<text x="15" y="${24+i*22}" font-size="18" font-weight="bold" fill="#29445f">${esc(line)}</text>`).join('')}<g transform="translate(0 ${header})">${content}</g>${footers.map((line,i)=>`<text x="15" y="${header+height+22+i*18}" font-size="14" fill="#61748c">${esc(line)}</text>`).join('')}</svg>`;
}
function figureCard(id,title,description,svg,caption,meaning=''){return `<figure class="figure-card"><div class="figure-heading"><h3>${esc(title)}</h3><div class="figure-downloads"><button class="text-button" data-save-svg="${id}">SVG</button><button class="text-button" data-save-png="${id}">PNG</button></div></div><p>${esc(description)}</p><div class="figure-canvas" id="${id}">${svg}</div>${meaning?easyBlock(meaning):''}<figcaption>${esc(caption)}</figcaption></figure>`;}
function wireFigureDownloads(){
  document.querySelectorAll('[data-save-svg]').forEach(button=>button.onclick=()=>{const svg=$(button.dataset.saveSvg).querySelector('svg');downloadText(new XMLSerializer().serializeToString(svg),`tgap-${state.job.slice(0,8)}-${button.dataset.saveSvg}.svg`,'image/svg+xml');});
  document.querySelectorAll('[data-save-png]').forEach(button=>button.onclick=async()=>{
    try{const svg=$(button.dataset.savePng).querySelector('svg');const image=new Image();const xml=new XMLSerializer().serializeToString(svg);
      await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=reject;image.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(xml);});
      const box=svg.viewBox.baseVal;const canvas=document.createElement('canvas');canvas.width=box.width*2;canvas.height=box.height*2;canvas.getContext('2d').drawImage(image,0,0,canvas.width,canvas.height);
      const anchor=document.createElement('a');anchor.download=`tgap-${state.job.slice(0,8)}-${button.dataset.savePng}.png`;anchor.href=canvas.toDataURL('image/png');anchor.click();
    }catch{toast('Could not create the PNG. Download the SVG instead.');}
  });
}
function predictionFigure(){
  const rows=state.result.rows,height=95+rows.length*38;
  const max=Math.max(...rows.filter(r=>r.valid_for_analysis).map(r=>Math.abs(r.prediction_change)),.000001);
  const center=460,scale=190/max;let content='';
  for(let i=0;i<5;i++){const value=(i-2)*max/2,x=center+value*scale;content+=`<line x1="${x}" x2="${x}" y1="25" y2="${height-50}" stroke="${i===2?'#8b9db3':'#e8eef5'}"/><text x="${x}" y="${height-30}" text-anchor="middle" font-size="15" fill="#60738c">${number(value,true)}</text>`;}
  rows.forEach((row,i)=>{const y=40+i*38;content+=`<text x="15" y="${y+5}" font-size="16" fill="#29445f">${esc(row.concept)} · ${row.direction==='increase'?'increase':'decrease'}</text>`;
    if(!row.valid_for_analysis){content+=`<text x="${center}" y="${y+5}" text-anchor="middle" font-size="15" fill="#a67330">Excluded: ${esc(row.status.replaceAll('_',' '))}</text>`;return;}
    const value=row.prediction_change,x=center+value*scale;
    content+=value===0?`<circle cx="${center}" cy="${y}" r="4" fill="#7f91a8"/>`:`<rect x="${Math.min(x,center)}" y="${y-9}" width="${Math.abs(x-center)}" height="18" rx="3" fill="${value>0?'#345f92':'#b56c38'}"/>`;
    content+=`<text x="${value>=0?x+8:x-8}" y="${y+5}" text-anchor="${value>=0?'start':'end'}" font-size="15" fill="#29445f">${number(value,true)}</text>`;
  });
  content+=`<text x="460" y="${height-9}" text-anchor="middle" font-size="15" fill="#60738c">Prediction after change − original prediction (model output units)</text>`;
  return svgFrame('Prediction changes for tested concepts',content,760,height);
}
function impactFigures(){
  return [...new Set(state.result.rows.map(r=>r.concept))].map((name,index)=>{
    const rows=state.result.rows.filter(r=>r.concept===name),max=Math.max(...rows.filter(r=>r.valid_for_analysis).map(r=>Math.abs(r.impact)),.000001);
    let content='<line x1="85" x2="420" y1="125" y2="125" stroke="#9caec3"/>';
    rows.forEach((row,i)=>{const x=160+i*190;content+=`<text x="${x}" y="232" text-anchor="middle" fill="#61748c" font-size="16">${row.direction==='increase'?'Increase':'Decrease'}</text>`;
      if(!row.valid_for_analysis){content+=`<text x="${x}" y="100" text-anchor="middle" fill="#a67330" font-size="15">Excluded</text>`;return;}
      const size=Math.abs(row.impact)/max*77,y=row.impact>=0?125-size:125;
      content+=`<rect x="${x-26}" y="${y}" width="52" height="${Math.max(size,1)}" fill="${row.impact>=0?'#345f92':'#b56c38'}" rx="3"/><text x="${x}" y="${row.impact>=0?y-10:y+size+19}" text-anchor="middle" font-size="17" fill="#29445f">${number(row.impact,true)}</text>`;
    });
    return figureCard(`impact-${index}`,name,'Normalized model sensitivity',svgFrame(name+' normalized sensitivity',content,520,260),`Each concept has its own scale. ${rows[0].delta_mode==='absolute'?'Absolute property units':'Relative property change'}; do not rank concepts across these panels.`,easyConcept(name));
  }).join('');
}
function renderFigures(){
  $('result-body').innerHTML='<div class="visual-intro"><h3>Your experiment, illustrated</h3><p>Start with the prediction-change figure. Open Network for structural edits and History for temporal changes. Each figure can be saved as an image.</p></div>'+figureCard('prediction-changes','How did the prediction respond?','All valid rows share the same model output units.',predictionFigure(),'Blue increases and orange decreases refer to the prediction difference, not the requested direction. Invalid rows are excluded; a point on zero means no model response.',explanationContent(state.result).summary+' Each bar shows how much the answer moved. Bars to the right mean a larger answer; bars to the left mean a smaller answer. Excluded tests do not count as zero.')+'<div class="figure-grid">'+impactFigures()+'</div><p class="result-note">These figures describe this run, not an average over repeated trials. Normalized sensitivity panels use independent scales. Numeric details and validity reasons remain available in Numbers.</p><p class="paper-output-link"><a href="#publication">Browse the paper publication figures &rarr;</a> &middot; Open Relationships for community connections in this run.</p>';
  $('result-body').insertAdjacentHTML('afterbegin','<section class="live-figures-invitation"><div><span class="eyebrow">DRAWN FROM YOUR OWN TEST</span><h3>Explore your publication-style explanation figures</h3><p>Node and edge explanations, time-step responses, dependence plots and sensitivity distributions use measurements from this run.</p></div><button class="primary" id="open-live-figures">Open my paper-style figures</button></section>');$('open-live-figures').onclick=()=>{state.resultTab='detailed';renderResults();};
  wireFigureDownloads();
}
function comparisonTools(id,index){return `<div class="chart-tools"><label for="${id}">Tested change</label><select id="${id}">${visualComparisons().map((c,i)=>`<option value="${i}" ${i===index?'selected':''}>${esc(c.concept)} · ${c.direction}${c.valid_for_analysis?'':' · excluded'}</option>`).join('')}</select></div>`;}
function networkFigure(comparison){
  const graph=state.result.graph,nodes=[...graph.nodes].sort((a,b)=>b.degree-a.degree).slice(0,80),selected=new Set(nodes.map(n=>String(n.id))),index=new Map(nodes.map(n=>[String(n.id),n]));
  const added=new Set(comparison.added.map(e=>edgeKey(...e))),removed=new Set(comparison.removed.map(e=>edgeKey(...e)));
  let content='';
  function panel(edges,offset,changed){
    const x=n=>offset+180+n.x*142,y=n=>188+n.y*124;
    content+=`<rect x="${offset+8}" y="35" width="344" height="300" fill="#f8fafc" rx="8"/><text x="${offset+180}" y="23" text-anchor="middle" font-size="18" fill="#29445f">${changed?'Transformed':'Original'} · last snapshot</text>`;
    edges.filter(e=>e.every(n=>selected.has(String(n)))).slice(0,1600).forEach(e=>{const a=index.get(String(e[0])),b=index.get(String(e[1])),highlight=changed?added.has(edgeKey(...e)):removed.has(edgeKey(...e));content+=`<line x1="${x(a)}" y1="${y(a)}" x2="${x(b)}" y2="${y(b)}" stroke="${highlight?(changed?'#237e81':'#b56c38'):'#bbcbdc'}" stroke-width="${highlight?2:.7}" opacity="${highlight?1:.55}"/>`;});
    nodes.forEach(n=>{content+=`<circle cx="${x(n)}" cy="${y(n)}" r="${3+Math.min(n.degree/12,3)}" fill="${colors[n.community%colors.length]}" stroke="white" stroke-width="1.2"><title>${esc(n.id)} · community ${n.community+1}</title></circle>`;});
  }
  panel(graph.edges,0,false);panel(comparison.edges,360,true);
  content+='<text x="180" y="360" text-anchor="middle" font-size="15" fill="#b56c38">Orange edges are removed by the change</text><text x="540" y="360" text-anchor="middle" font-size="15" fill="#237e81">Teal edges are added by the change</text>';
  return svgFrame('Original and transformed network comparison',content,720,380);
}
function renderVisualNetwork(index=0){
  const c=visualComparisons()[index];$('result-body').innerHTML=comparisonTools('network-change',index)+(c.valid_for_analysis?'':`<p class="result-note">This change is excluded (${esc(c.status)}). Its structure is shown for diagnosis, not as a valid explanation.</p>`)+figureCard('network-comparison',`${c.concept} · ${c.direction}`,'The same nodes and positions are used in both panels.',networkFigure(c),`${Math.min(80,state.result.graph.nodes.length)} of ${state.result.graph.nodes.length} nodes shown; up to 1,600 edges per panel. Predictions use the full sequence. ${c.added.length} added and ${c.removed.length} removed edges in the full last snapshot.`,!c.valid_for_analysis?'These pictures show the graph edits, but this test failed its checks. We cannot use it as a valid explanation.':c.added.length+c.removed.length===0?'The last network stayed the same. This change may affect earlier time steps; open History to check.':`The change added ${c.added.length} connections and removed ${c.removed.length} connections in the last network. The same dots stay in the same places, so you can compare the connections. The model's response to these edits is explained above.`)+`<div class="graph-legend">${Array.from({length:state.result.summary.communities},(_,i)=>`<span><i class="legend-dot" style="background:${colors[i%colors.length]}"></i>Community ${i+1}</span>`).join('')}</div><p class="result-note">History-only transformations may leave the last snapshot unchanged. Select History to see their effects. Edge highlights are structural edits, not individual edge importance scores.</p>`;
  $('network-change').onchange=e=>renderVisualNetwork(Number(e.target.value));wireFigureDownloads();
}
function historyFigure(original,changed,metric){
  const all=original.concat(changed||[]).map(r=>r[metric]),low=Math.min(0,...all),high=Math.max(...all,low+.001),x=i=>78+i*580/Math.max(1,original.length-1),y=v=>260-(v-low)/(high-low)*210;
  let content='';for(let i=0;i<5;i++){const value=low+(high-low)*i/4;content+=`<line x1="78" x2="658" y1="${y(value)}" y2="${y(value)}" stroke="#e5edf4"/><text x="67" y="${y(value)+4}" text-anchor="end" fill="#61748c" font-size="15">${number(value)}</text>`;}
  function series(rows,color,dashed){content+=`<polyline points="${rows.map((r,i)=>`${x(i)},${y(r[metric])}`).join(' ')}" fill="none" stroke="${color}" stroke-width="2.8" ${dashed?'stroke-dasharray="7 4"':''}/>`;rows.forEach((r,i)=>{content+=`<circle cx="${x(i)}" cy="${y(r[metric])}" r="${dashed?4:3}" fill="${dashed?'white':color}" stroke="${color}" stroke-width="1.8"><title>${esc(r.label)} · ${number(r[metric])}</title></circle>`;});}
  series(original,'#345f92',false);if(changed)series(changed,'#237e81',true);
  original.forEach((r,i)=>{if(i===0||i===original.length-1||original.length<10)content+=`<text x="${x(i)}" y="283" text-anchor="middle" fill="#61748c" font-size="15">${i+1}</text>`;});
  content+='<text x="360" y="315" text-anchor="middle" fill="#61748c" font-size="16">Snapshot, oldest to newest</text><text x="78" y="22" font-size="16" fill="#345f92">━━ Original</text>'+(changed?'<text x="220" y="22" font-size="16" fill="#237e81">┄┄ Transformed</text>':'');
  return svgFrame('Original and transformed '+metric+' history',content,720,335);
}
function renderVisualHistory(index=0,metric='bridge'){
  const c=visualComparisons()[index],names={bridge:'Bridge width',density:'Density',centralization:'Centralization',edges:'Edge count'};
  $('result-body').innerHTML=comparisonTools('history-change',index)+`<div class="chart-tools"><label for="trajectory-metric">Measure</label><select id="trajectory-metric">${Object.entries(names).map(([id,name])=>`<option value="${id}" ${id===metric?'selected':''}>${name}</option>`).join('')}</select></div>`+(c.valid_for_analysis?'':`<p class="result-note">Excluded change (${esc(c.status)}): use this plot to inspect the validity failure.</p>`)+figureCard('history-comparison',`${names[metric]} through time`,`${c.concept} · ${c.direction}`,historyFigure(state.result.trajectory,c.trajectory,metric),c.trajectory?'Solid blue is the original; dashed teal is the transformed sequence. Overlapping lines mean the selected measure stayed the same.':'This older saved experiment contains only original history. Run it again to save transformed histories.',easyHistory(c,metric))+'<p class="result-note">A present-only model reads the final snapshot; a forecast or slope model reads history. Indices show ordering, not equal spacing in real time. This is a structural measure, not the model’s prediction.</p>';
  $('history-change').onchange=e=>renderVisualHistory(Number(e.target.value),metric);$('trajectory-metric').onchange=e=>renderVisualHistory(index,e.target.value);wireFigureDownloads();
}
