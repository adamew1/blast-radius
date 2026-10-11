export default function(component) {
  const {data:d,parentElement,setTriggerValue}=component;
  const root=parentElement.querySelector('#terminal');
  if(!root||!d) return;
  if(root.dataset.pending===String(d.ack)) delete root.dataset.pending;
  root.classList.toggle('busy',!!root.dataset.pending);
  root.dataset.revision=d.revision;
  const s=d.state, st=d.stress, plan=s.plan, audit=plan?.audit;
  const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money=v=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(v||0);
  const short=v=>v>=1e6?'$'+(v/1e6).toFixed(2)+'M':v>=1e3?'$'+(v/1e3).toFixed(1)+'K':money(v);
  const pct=v=>(v*100).toFixed(1)+'%';
  const label=v=>String(v).replace(/Pendle /,'').replace(/Morpho /,'').replace(/ · .*/, '').replace(/Sky \(formerly MakerDAO\)/,'Sky');
  const send=(type,rest={})=>{
    const nonce=Date.now()+Math.random();
    root.dataset.pending=String(nonce);
    root.classList.add('busy');
    setTriggerValue('action',{type,...rest,revision:d.revision,nonce});
  };
  const stage=s.evidence?4:plan?3:s.attacked?2:s.revealed?1:0;
  const selected=d.selected;
  const after=!!audit&&s.before_after==='after';
  const shownLoss=s.attacked?(after?audit.residual_loss_usd:st.loss_usd):0;
  const top=(d.shared.length?d.shared:d.ranking).slice(0,3);
  const count=d.positions.length;
  const soldIds=new Set((plan?.actions||[]).filter(a=>a.fraction>0).map(a=>a.id));
  let frames=[], timers=[];
  const metric=(name,value,note,cls='')=>`<div class="metric"><div class="label">${name}</div><div class="value ${cls}">${value}</div><div class="note">${note}</div></div>`;
  root.innerHTML=`<main class="terminal">
    <header class="top"><div class="brand"><svg viewBox="0 0 40 40" aria-hidden="true"><circle cx="20" cy="20" r="17" fill="none" stroke="#4adbc0" stroke-width="1"/><circle cx="20" cy="20" r="10" fill="none" stroke="#4adbc0" stroke-width="1"/><path d="M20 1v10M20 29v10M1 20h10M29 20h10" stroke="#4adbc0"/><circle cx="20" cy="20" r="3" fill="#4adbc0"/></svg><div>BLAST RADIUS<small>DEPENDENCY INTELLIGENCE</small></div></div>
    <nav class="steps" aria-label="Demonstration stages">${['DISCOVER','ATTACK','COLLAPSE','RESCUE','PROVE'].map((x,i)=>`<span class="step ${i<=stage?'active':''}"><b>${i+1}</b>${x}</span>`).join('')}</nav>
    <div class="meta"><span class="badge"><i></i>FROZEN EVIDENCE</span><button class="ghost" id="reset">Reset</button></div></header>
    <section class="hero"><div><div class="eyebrow">THE ILLUSION OF DIVERSIFICATION</div><h1>${!s.revealed?`${count===10?'Ten':count} positions. <span>One hidden bet?</span>`:plan?'A smaller blast radius. <span>A defensible cost.</span>':`${st.exposed_positions} ${st.exposed_positions===1?'position':'positions'}. <span>One ${st.exposed_positions>1?'shared ':''}dependency.</span>`}</h1><p>${!s.revealed?`You think you own ${count} independent investments. Let the dependencies tell you what you really own.`:`${esc(selected.label)} connects ${st.exposed_positions} investments across the book. ${s.attacked?'This is the damage conditional on your chosen shock.':'Discovered from recursive position look-through.'}`}</p></div><div class="headline-note"><strong>REAL DATA. EXPLICIT ASSUMPTIONS.</strong>Illustrative ${short(st.aum_usd)} allocation.<br>Hypothetical pre-failure protection.<br>Scenario loss ≠ expected loss.</div></section>
    ${challengePanel()}
    <section class="metrics" aria-label="Portfolio financial metrics">${metric('Portfolio value',money(st.aum_usd),`${count} positions · supported instruments`)}${metric('Shared exposure',s.revealed?`${st.exposed_positions} / ${count}`:'—',s.revealed?`${money(st.affected_capital_usd)} gross affected capital`:'Hidden beneath the position labels',s.revealed?'amber':'')}${metric(after?'Residual scenario loss':'Conditional scenario loss',s.attacked?`<span id="loss-counter" data-target="${shownLoss}">${money(shownLoss)}</span>`:'—',s.attacked?`${Math.round(s.severity*100)}% intrinsic shock · ${pct(shownLoss/st.aum_usd)} of book`:'Choose a dependency, then trigger failure',after?'teal':'red')}${metric(audit?'Protection cost':(d.shared.length?'Largest shared dependency':'Largest dependency'),audit?money(audit.protection_cost_usd):s.revealed?esc(label(top[0].label)):'Unknown',audit?'Execution + conversion reserve + 30d carry':s.revealed?`${top[0].positions} positions · ${short(top[0].loss_usd)} modelled loss`:'Automatically ranked, never hardcoded',audit?'teal':'')}</section>
    <div class="workspace"><section class="graph-panel"><div class="panel-head"><strong>Portfolio dependency network</strong><div class="legend"><span><i></i>Observed / mapped</span><span><i class="hot"></i>Transmitted shock</span><span><i class="saved"></i>Reduced exposure</span></div>${audit?`<div class="view-toggle"><button id="before" class="${!after?'on':''}">Before</button><button id="after" class="${after?'on':''}">After rescue</button></div>`:''}</div><div class="network"><svg id="network" viewBox="0 0 1080 600" role="group" aria-label="Interactive portfolio dependency graph"></svg>${!s.revealed?`<div class="initial-card"><div class="number">${count} → ?</div><h3>Diversification is a claim.<br>Let the graph test it.</h3><p>Your positions have different names.<br>Their yield sources, collateral and issuers may tell a different story.</p><div class="micro">RECURSIVE LOOK-THROUGH · REAL SNAPSHOT</div></div>`:''}<div class="network-hint">${s.revealed?'Click a dependency to attack it. Click a path to inspect its financial meaning.':''}</div></div><div class="inspection" id="inspection"><div class="inspect-header"><strong>${s.attacked?'Shock flows from dependency to position.':'A position label is only the surface.'}</strong><span>${s.revealed?'WIDTH = ATTRIBUTED LOSS':`${count} SNAPSHOT POSITIONS`}</span></div>${s.revealed?'Solid paths show actual underlying relationships. Faint dotted links summarize inspectable discovered paths.':'Find the common dependency hidden beneath your portfolio.'}</div></section>
    <aside class="rail"><div class="kicker">${!s.revealed?'01 / DISCOVER':!s.attacked?'02 / ATTACK':'04 / RESCUE'}</div><h2>${!s.revealed?'What did you really buy?':!s.attacked?'Choose your failure.':'Can we protect it<br>before it fails?'}</h2><p>${!s.revealed?'Automatically rank shared dependencies by their modelled impact on the entire book.':!s.attacked?'Select any dependency. The same deterministic engine recomputes every position.':'Find the least-cost reductions within quote and shared liquidity bounds.'}</p>
    ${!s.revealed?'<button class="primary" id="discover">FIND MY WEAKEST POINT ↗</button>':`<select class="select" id="dependency" aria-label="Select dependency">${d.ranking.map(r=>`<option value="${esc(r.id)}" ${r.id===s.dependency?'selected':''}>${esc(r.label)} · ${r.positions} positions</option>`).join('')}</select><div class="control-row"><label for="severity">Failure severity</label><output id="severity-value">${Math.round(s.severity*100)}%</output></div><input class="slider" id="severity" type="range" min="0" max="100" value="${Math.round(s.severity*100)}" aria-label="Failure severity"><button class="primary attack-btn" id="attack">${s.attacked?'REPLAY FAILURE ↗':'SIMULATE FAILURE ↗'}</button>`}
    ${s.revealed&&!s.attacked?`<div class="section"><div class="section-title">${d.shared.length?'Weakest shared points':'Dependency damage'} · 100% shock</div>${top.map((r,i)=>`<button class="risk-row ${r.id===s.dependency?'selected':''}" data-dependency="${esc(r.id)}"><span class="row"><span>0${i+1} ${esc(label(r.label))}</span><strong>${short(r.loss_usd)}</strong></span><small>${r.positions} positions · ${pct(r.exposure_concentration)} gross affected</small><div class="risk-bar"><b style="width:${100*r.loss_usd/top[0].loss_usd}%"></b></div></button>`).join('')}</div>`:''}
    ${s.attacked?`<div class="section"><label class="section-title" for="limit">Maximum accounted scenario loss</label><div class="limit-wrap"><span>$&nbsp;</span><input id="limit" class="limit" type="number" min="0" step="50000" value="${s.loss_limit}" aria-label="Maximum acceptable loss"></div><div class="section-title">Keep a position? Lock it.</div><div class="locks">${d.positions.map(p=>`<label class="lock"><input type="checkbox" value="${esc(p.id)}" ${s.locks.includes(p.id)?'checked':''}>${esc(label(p.label))}</label>`).join('')}</div><button class="primary" id="rescue">BUILD RESCUE PLAN ↗</button><div class="disclaimer">Loss limit includes execution + conversion reserve. Least economic cost on captured PT trade amounts and 5% vault reductions. Protection happens before the hypothetical failure.</div>${plan?`<div class="section status ${plan.target_met?'':'warn'}">${plan.status==='infeasible'?'TARGET INFEASIBLE':plan.status==='optimal'?'OPTIMAL ON AVAILABLE GRID':esc(plan.status.toUpperCase())}<br>${audit?`${money(audit.accounted_loss_usd)} accounted loss · ${plan.target_met?'within your limit':'above your limit'}`:esc(plan.message)}</div>`:''}</div>`:`<div class="section"><div class="section-title">Evidence, not prediction</div><p>Cached protocol APIs. Sourced issuer mappings. Explicit transmission assumptions. No invented live figures.</p><div class="disclaimer">Model coverage is incomplete: ${d.opaque_positions.length}/${count} positions contain unresolved collateral. Gross affected capital is not loss.</div></div>`}
    </aside></div>
    ${audit?rescuePanel():''}
    <footer class="footer"><div>COMPOSITE EVIDENCE · ${esc((d.snapshot_window||[d.snapshot]).map(x=>x.slice(0,19).replace('T',' ')).join(' to '))} UTC<br>Modelled single-event loss · animation shows causal order, not elapsed incident time · <span class="hash">BUNDLE ${d.bundle_hash.slice(0,12)}</span></div><button class="proof-button" id="proof">${s.evidence?'Hide evidence':'Show Me the Evidence'} ↗</button></footer>
    ${s.evidence?proofPanel():''}
  </main>`;

  function challengePanel(){
    const c=d.challenge;
    return `<details class="challenge" ${s.portfolio_error?'open':''}><summary>CHALLENGE THIS PORTFOLIO <span>${s.portfolio_sizes?'Judge allocation active':'Construct a book from the frozen catalog'}</span></summary><form id="portfolio-form"><p>Choose from ${c.supported.length} admitted Ethereum instruments. Add or remove positions; select at most ten. Allocate $0–$2M each in $50k steps. Applying restarts Discover → Attack → Collapse → Rescue → Prove.</p><div class="catalog-picker"><select id="catalog-instrument" class="select" aria-label="Instrument catalog"></select><button type="button" id="catalog-add" class="ghost">Add instrument</button></div><div class="challenge-inputs">${d.positions.map(p=>allocationRow(p,p.size_usd)).join('')}</div><div class="challenge-bottom"><strong id="challenge-preview"></strong><button class="primary" type="submit">APPLY PORTFOLIO & REDISCOVER ↗</button></div><div class="disclaimer">Frozen catalog, not a wallet import or universal protocol support. Pendle: exact captured $50k–$1M trade amounts only, retaining original outputs and costs. Holdings above $1M cannot fully exit using these quotes. Morpho: funded claims and shared liquidity remain binding. Captures have separate retrieval times. No quote interpolation, splitting or extrapolation; future fills are not guaranteed. Gas and external-cash conversion are assumed reserves.</div><p id="challenge-error" role="alert">${esc(s.portfolio_error||'')}</p></form></details>`;
  }
  function allocationRow(p,value){
    return `<div class="allocation-row" data-instrument="${esc(p.id)}"><label for="size-${esc(p.id)}">${esc(label(p.label))}</label><input id="size-${esc(p.id)}" data-size="${esc(p.id)}" aria-label="Allocation ${esc(p.id)}" type="number" min="0" max="${d.challenge.max_usd}" step="${d.challenge.step_usd}" value="${value}" required><button type="button" class="catalog-remove" data-remove="${esc(p.id)}" aria-label="Remove ${esc(p.id)}">Remove</button></div>`;
  }
  function rescuePanel(){
    const full=s.baseline?.audit;
    const baselineOk=full&&s.baseline.status!=='infeasible';
    const threshold=audit.break_even_probability;
    const actions=(plan.actions||[]).filter(a=>a.fraction>0);
    return `<section class="rescue-panel" aria-label="Rescue comparison"><div class="rescue-top"><div><div class="eyebrow">${plan.target_met?'PROTECTION, PRICED.':'THE CONSTRAINTS ARE REAL.'}</div><h2>${plan.target_met?'The same portfolio. A smaller common bet.':(plan.status==='infeasible'?'This loss limit cannot be met under the current constraints.':'The target has not been proved feasible or infeasible.')}</h2><p>${plan.target_met?`${count-actions.length} positions untouched. Every reduction audited against captured candidates and liquidity.`:'Showing the best attainable accounted loss when proved. Release a lock or increase the limit.'}</p></div></div><div class="rescue-grid"><div class="comparison"><div class="name">01 / DO NOTHING</div><div class="big red">${money(st.loss_usd)}</div><div class="sub">Conditional scenario loss<br>No protection cost</div></div><div class="comparison"><div class="name">02 / EXIT AFFECTED POSITIONS</div><div class="big ${baselineOk?'':'amber'}">${baselineOk?money(full.accounted_loss_usd):'Unavailable'}</div><div class="sub">${baselineOk?`${money(full.protection_cost_usd)} economic cost<br>${money(full.capital_sold_usd)} sold`:'Locks, quote coverage or snapshot liquidity<br>prevent a full exit.'}</div></div><div class="comparison best"><div class="name">03 / ${plan.target_met?'OPTIMIZED PROTECTION':plan.status==='infeasible'?'MINIMUM ATTAINABLE':'BEST VERIFIED CANDIDATE'}</div><div class="big ${plan.target_met?'teal':'amber'}">${money(audit.accounted_loss_usd)}</div><div class="sub">Residual scenario loss + execution + conversion<br>${plan.optimal?'Proved on available discrete candidates':'Verified incumbent; optimality not proved'}</div></div></div><div class="economics">${[['Capital released',audit.capital_released_usd],['Execution + conversion',audit.execution_usd+audit.conversion_usd],['Foregone yield · 30d',audit.carry_usd],['Scenario loss avoided',audit.avoided_loss_usd]].map(([k,v])=>`<div class="economic"><div class="label">${k}</div><strong>${money(v)}</strong></div>`).join('')}</div><div class="actions">${actions.map(a=>`<span class="action-chip">REDUCE ${esc(label(a.label))} ${Math.round(a.fraction*100)}%</span>`).join('')||'<span class="action-chip">HOLD · no reduction needed</span>'}</div><div class="economic-note">${threshold!==null?`Compared with holding, this plan has positive modelled expected net benefit above a <strong>${(threshold*100).toFixed(2)}%</strong> assumed probability of this exact scenario over 30 days. ${threshold>1?'Threshold exceeds 100%: the protection cannot pay for itself under this scenario.':''}`:'No conditional loss avoided; no break-even probability.'} Least cost for your stress mandate. This is a whole-plan break-even comparison, not a marginal threshold or a globally optimal trading policy.<div class="control-row"><label for="probability">Your assumed 30-day scenario probability</label><span><input id="probability" class="probability" type="number" min="0" max="100" step="0.1" placeholder="—" aria-label="Assumed scenario probability"> %</span></div><div id="expected-benefit">Enter an assumption to compare probability-weighted benefit with economic cost.</div></div></section>`;
  }
  function proofPanel(){
    const q=d.quote_bundle.positions['pt-reusd'];
    const quoteCount=Object.values(d.quote_bundle.positions).reduce((sum,p)=>sum+p.options.filter(o=>o.available).length,0);
    return `<div class="proof-inline"><strong>Evidence classification</strong><br>Illustrative allocation to real instruments. Protocol API observations: vault allocations, market balances and available liquidity. Sourced manual relationships: wrapper backing and issuers. Manual token-level oracle names are unverified integration hypotheses. Captures are not synchronized; the manifest distinguishes retrieval time from provider mark time. RPC observations: token decimals at block ${esc(d.quote_bundle.rpc_block)}${d.quote_bundle.catalog_rpc?` and catalog block ${esc(d.quote_bundle.catalog_rpc.rpc_block)}`:''}.<br><strong>A consequential detail:</strong> PT-reUSD has ${q?.input_asset.decimals??'?'} decimals, verified by eth_call. Candidate sizing uses this observed value.<br><strong>Model:</strong> alternate paths use strongest transmission; distinct vault allocations add; lending losses use incremental aggregate collateral shortfall. PT claims transmit underlying loss one-for-one at a fixed discount factor; other coefficients are assumptions, not facts.<br><strong>Execution:</strong> ${quoteCount} captured Pendle quotes. Morpho shared-market resource constraints. Two-basis-point gas and ten-basis-point cash-conversion reserves are assumptions. PT quotes return underlying tokens, including wstETH; protection requires the assumed conversion to external cash. Snapshot bounds do not certify withdrawal queues or future execution.<br><strong>Coverage:</strong> ${d.opaque_positions.length}/${count} positions contain unresolved collateral; loan-asset issuer risk and full reserve look-through are incomplete.<br>The detailed source manifest, full responses, coefficients and downloadable decision receipt are immediately below.</div>`;
  }

  const $=q=>root.querySelector(q);
  $('#reset').onclick=()=>send('reset');
  const sizeInputs=()=>[...root.querySelectorAll('[data-size]')];
  const preview=()=>{
    const values=sizeInputs().map(input=>Number(input.value));
    $('#challenge-preview').textContent=`${money(values.reduce((a,b)=>a+b,0))} · ${values.filter(v=>v>0).length} positions`;
    const selectedIds=new Set(sizeInputs().map(input=>input.dataset.size));
    const available=d.challenge.supported.filter(p=>!selectedIds.has(p.id));
    $('#catalog-instrument').innerHTML=available.map(p=>`<option value="${esc(p.id)}">${esc(p.label)}</option>`).join('');
    $('#catalog-add').disabled=!available.length;
  };
  $('.challenge-inputs').oninput=preview;
  $('.challenge-inputs').onclick=e=>{
    const button=e.target.closest('[data-remove]');
    if(button){button.closest('.allocation-row').remove();preview();}
  };
  $('#catalog-add').onclick=()=>{
    if(sizeInputs().length>=10){$('#challenge-error').textContent='Remove a row before adding another instrument (maximum ten).';return;}
    const p=d.challenge.supported.find(p=>p.id===$('#catalog-instrument').value);
    if(p){$('.challenge-inputs').insertAdjacentHTML('beforeend',allocationRow(p,500000));$('#challenge-error').textContent='';preview();}
  };
  preview();
  $('#portfolio-form').onsubmit=e=>{
    e.preventDefault();
    const sizes=Object.fromEntries(d.challenge.supported.map(p=>[p.id,0]));
    sizeInputs().forEach(input=>sizes[input.dataset.size]=Number(input.value));
    if(!Object.values(sizes).some(v=>v>0)){
      $('#challenge-error').textContent='Keep at least one position.';
      return;
    }
    send('portfolio',{sizes});
  };
  if($('#discover')) $('#discover').onclick=()=>send('discover');
  if($('#dependency')) $('#dependency').onchange=e=>send('select',{id:e.target.value});
  root.querySelectorAll('[data-dependency]').forEach(b=>b.onclick=()=>send('select',{id:b.dataset.dependency}));
  if($('#severity')){
    $('#severity').oninput=e=>{$('#severity-value').textContent=e.target.value+'%';};
    $('#severity').onchange=e=>send('severity',{value:Number(e.target.value)/100});
    $('#attack').onclick=()=>send('attack');
  }
  if($('#rescue')) $('#rescue').onclick=()=>{
    const limit=Number($('#limit').value);
    if(!Number.isFinite(limit)||limit<0)return;
    send('rescue',{limit,locks:[...root.querySelectorAll('.lock input:checked')].map(x=>x.value)});
  };
  if($('#before')){$('#before').onclick=()=>send('view',{value:'before'});$('#after').onclick=()=>send('view',{value:'after'});}
  $('#proof').onclick=()=>send('evidence');
  if($('#probability')) $('#probability').oninput=e=>{
    const p=Number(e.target.value)/100;
    $('#expected-benefit').textContent=e.target.value===''?'Enter an assumption to compare probability-weighted benefit with economic cost.':
      p<0||p>1?'Probability must lie between 0% and 100%.':`${money(p*audit.avoided_loss_usd-audit.protection_cost_usd)} expected net benefit at your assumed ${pct(p)} scenario probability. This probability is not estimated by the system.`;
  };

  // Stable view coordinates. SVG strokes follow the actual graph, reversed
  // visually because failures propagate from dependency to parent claim.
  const svg=$('#network'), NS='http://www.w3.org/2000/svg';
  const make=(tag,attrs,text)=>{const el=document.createElementNS(NS,tag);for(const[k,v]of Object.entries(attrs||{}))el.setAttribute(k,String(v));if(text!==undefined)el.textContent=text;return el;};
  const nodes=d.network.nodes, edges=d.network.edges;
  const coord={};
  for(let col=0;col<4;col++){
    const group=nodes.filter(n=>n.column===col);
    group.forEach((n,i)=>{coord[n.id]={x:[125,405,620,908][col],y:col===0||col===3?60+(n.row||0)*55:90+i*490/Math.max(1,group.length-1),w:col===3?270:col===0?205:col===2?175:145,h:col===3?44:36};});
  }
  const textCols=s.revealed?[[30,'SHARED DEPENDENCIES'],[340,'BACKING / COLLATERAL'],[556,'LENDING MARKETS'],[775,'YOUR INVESTMENTS']]:[[775,'YOUR INVESTMENTS']];
  textCols.forEach(([x,t])=>svg.append(make('text',{x,y:23,class:'column-label'},t)));
  const dist={[d.network.selected]:0};
  for(let k=0;k<20;k++){let changed=false;for(const e of edges.filter(e=>e.active)){if(dist[e.child]!==undefined&&(dist[e.parent]===undefined||dist[e.parent]>dist[e.child]+1)){dist[e.parent]=dist[e.child]+1;changed=true;}}if(!changed)break;}
  const defs=make('defs');
  defs.innerHTML='<filter id="glow"><feGaussianBlur stdDeviation="6"/></filter>';
  svg.append(defs);
  let sequence=0;
  edges.forEach(e=>{
    const a=coord[e.child],b=coord[e.parent];if(!a||!b)return;
    const direction=b.x>=a.x?1:-1;
    const x1=a.x+direction*a.w/2,x2=b.x-direction*b.w/2;
    const gap=Math.max(55,Math.abs(x2-x1)*.5);
    const path=`M${x1},${a.y} C${x1+direction*gap},${a.y} ${x2-direction*gap},${b.y} ${x2},${b.y}`;
    const impact=after?e.remaining_impact_usd:e.impact_usd;
    const maxImpact=Math.max(1,...edges.map(e=>e.impact_usd));
    const width=e.active?1.3+4*Math.sqrt(Math.max(0,impact)/maxImpact):.8;
    const protectedEdge=after&&e.active&&e.remaining_impact_usd<e.impact_usd;
    const p=make('path',{d:path,class:`flow ${e.collapsed?'collapsed':''} ${e.active?'active':''} ${protectedEdge?'protected':''}`,'stroke-width':width});
    const pathId='flow-'+sequence++;p.id=pathId;svg.append(p);
    const click=()=>{
      const child=nodes.find(n=>n.id===e.child),parent=nodes.find(n=>n.id===e.parent);
      const item=e.evidence[0];
      $('#inspection').innerHTML=`<strong>${esc(child?.label)} → ${esc(parent?.label)}</strong><br>${e.collapsed?`${item.paths.length} actual discovered path(s), summarized visually. ${item.paths.map(path=>path.map(id=>nodes.find(n=>n.id===id)?.label||id).join(' → ')).map(esc).join('<br>')}`:`${esc(item.type)} · ${item.exposure_pct}% parent exposure · ${esc(item.source)} · ${esc(item.rule)}<br>${money(impact)} attributed root loss through this edge${item.coefficient!==null&&item.coefficient!==undefined?' · coefficient '+item.coefficient:''}`}<br><code>${esc(e.child)} → ${esc(e.parent)}</code>`;
    };
    const hit=make('path',{d:path,class:'flow-hit',role:'button',tabindex:0,'aria-label':`Inspect ${e.child} to ${e.parent}`});hit.onclick=click;hit.onkeydown=ev=>{if(ev.key==='Enter')click();};svg.append(hit);
    if(e.active&&!reduced){
      const delay=(dist[e.child]||0)*.28;
      p.style.opacity='0';p.style.transition='opacity .5s';
      timers.push(setTimeout(()=>p.style.opacity='1',delay*1000));
      const pulse=make('circle',{r:2.7,class:'pulse'});
      const motion=make('animateMotion',{dur:'1.15s',begin:`${delay}s`,repeatCount:'1',fill:'remove',path});
      pulse.append(motion);pulse.style.opacity='0';svg.append(pulse);
      timers.push(setTimeout(()=>pulse.style.opacity='1',delay*1000));
      timers.push(setTimeout(()=>pulse.remove(),(delay+1.15)*1000));
    }
  });
  nodes.forEach(n=>{
    if(!s.revealed&&n.kind!=='position')return;
    const c=coord[n.id];
    const isPosition=n.kind==='position';
    const affected=s.attacked&&(isPosition?n.loss_usd>0:dist[n.id]!==undefined);
    const protectedNode=after&&isPosition&&n.sold_fraction>0;
    const g=make('g',{class:`node ${n.selected?'selected':''} ${affected?'failed':''} ${protectedNode?'rescued':''}`,role:'button',tabindex:0,'aria-label':isPosition?`Inspect ${n.label}`:`Attack ${n.label}`,'data-node':n.id});
    g.append(make('rect',{x:c.x-c.w/2,y:c.y-c.h/2,width:c.w,height:c.h,rx:isPosition?5:8,class:'node-box'}));
    if(isPosition){
      const title=label(n.label);g.append(make('text',{x:c.x-c.w/2+13,y:c.y-5,class:'position-label'},title.length>29?title.slice(0,28)+'…':title));
      g.append(make('text',{x:c.x-c.w/2+13,y:c.y+12,class:'position-value'},after&&n.sold_fraction>0?`${money(n.size_usd*(1-n.sold_fraction))} retained · ${Math.round(n.sold_fraction*100)}% exit`:money(n.size_usd)));
      if(s.attacked)g.append(make('text',{x:c.x+c.w/2-11,y:c.y+12,'text-anchor':'end',class:'loss-label',style:protectedNode?'fill:#4adbc0':''},'-'+short(after?n.remaining_loss_usd:n.loss_usd)));
      if(s.locks.includes(n.position_id))g.append(make('text',{x:c.x+c.w/2-12,y:c.y-6,'text-anchor':'end',fill:'#eac27a','font-size':9},'LOCKED'));
    }else{
      const title=label(n.label);const max=n.column===0?25:23;
      g.append(make('text',{x:c.x-c.w/2+10,y:c.y+3,class:'node-label'},title.length>max?title.slice(0,max-1)+'…':title));
      if(n.count)g.append(make('text',{x:c.x+c.w/2-9,y:c.y+3,'text-anchor':'end',class:'node-sub'},`${n.count}×`));
    }
    const inspect=()=>{
      if(!isPosition){send('select',{id:n.id});return;}
      const row=st.positions.find(p=>p.id===n.position_id);
      $('#inspection').innerHTML=`<strong>${esc(n.label)}</strong> · ${money(n.size_usd)} snapshot position<br>${money(row.loss_usd)} conditional loss · ${pct(row.fraction)} loss fraction${audit?` · ${Math.round((plan.actions.find(a=>a.id===n.position_id)?.fraction||0)*100)}% proposed reduction`:''}<br><code>${esc(n.id)}</code>`;
    };
    g.onclick=inspect;g.onkeydown=ev=>{if(ev.key==='Enter')inspect();};
    if(affected&&!reduced){g.style.opacity='.4';g.style.transition='opacity .45s';timers.push(setTimeout(()=>g.style.opacity='1',(dist[n.id]||0)*280));}
    svg.append(g);
  });
  // Animate only toward authoritative Python values, never inventing intermediate
  // incident observations. Browser-local interpolation is decorative.
  const counter=$('#loss-counter');
  if(counter&&!reduced){const target=Number(counter.dataset.target),start=performance.now();const tick=t=>{const progress=Math.min(1,(t-start)/1100);counter.textContent=money(target*(1-Math.pow(1-progress,3)));if(progress<1)frames.push(requestAnimationFrame(tick));};frames.push(requestAnimationFrame(tick));}
  return ()=>{timers.forEach(clearTimeout);frames.forEach(cancelAnimationFrame);};
}
