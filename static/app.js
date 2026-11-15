'use strict';
const $ = id => document.getElementById(id);
let data;
let request = 0;
const labels = {pending:'Pending',in_progress:'In progress',blocked:'Blocked',awaiting_verification:'Awaiting verification',verified_done:'Verified done',done:'Done'};
function el(tag, text, cls) { const n=document.createElement(tag); if(text!==undefined)n.textContent=text; if(cls)n.className=cls; return n; }
function moneyless(n) { return n===null || n===undefined ? 'Unavailable' : Number(n).toLocaleString(undefined,{maximumFractionDigits:2}); }
function range(r) { return r ? `${moneyless(r.low)} / ${moneyless(r.likely)} / ${moneyless(r.high)} h` : 'Unavailable'; }
function status(s) { return el('span',labels[s]||s,'status '+(Object.hasOwn(labels,s)?s:'')); }
function empty(target,title,detail) { const box=el('div',undefined,'empty');box.append(el('strong',title),el('span',detail));target.append(box); }
function issueEstimate(i) { return i.estimate || Object.fromEntries(['low','likely','high'].map(k=>[k,data.estimate_method[k]*data.estimate_method.review_multiplier])); }
function sumMetrics(items,complete) {
 const verified=items.filter(i=>i.verified).length;
 const estimate={low:0,likely:0,high:0},remaining={...estimate};let measured=0,actual=0;
 items.forEach(i=>{ const e=issueEstimate(i);Object.keys(e).forEach(k=>{estimate[k]+=e[k];if(!i.verified)remaining[k]+=e[k];});if(i.actual_machine_hours!==null){measured++;actual+=i.actual_machine_hours;} });
 return {known_issues:items.length,verified_issues:verified,percent:complete&&items.length?Math.round(verified/items.length*1000)/10:null,estimate:items.length?estimate:null,remaining_estimate:items.length?remaining:null,actual_machine_hours:measured?actual:null,measured_issues:measured,scope_complete:complete};
}
function matchesTeam(record,team) { const teams=record.teams||[];return !team||(team==='unassigned'?teams.length===0:teams.includes(team)); }
function selection() {
 const p=$('project').value,e=$('epic').value,team=$('team').value;
 const issues=data.issues.filter(i=>(!p||i.projects.includes(p))&&(!e||i.epic_keys.includes(e))&&matchesTeam(i,team));
 const tasks=data.tasks.filter(t=>(!p||t.project===p)&&(!e||t.epic_key===e)&&matchesTeam(t,team));
 // Only explicitly team-scoped aggregates can describe a team subset.
 const reported=data.reported_statistics.filter(r=>(!p||!r.project||r.project===p)&&(!e||!r.epic||r.epic===e)&&(!team||((r.teams||[]).length>0&&matchesTeam(r,team))));
 const epics=data.epics.filter(x=>(!e||x.key===e)&&(!(p||team)||issues.some(i=>i.epic_keys.includes(x.key))||tasks.some(t=>t.epic_key===x.key)||reported.some(r=>r.epic===x.key&&(!p||r.project===p))));
 const projects=data.projects.filter(x=>(!p||x.id===p)&&(!team||matchesTeam(x,team)||issues.some(i=>i.projects.includes(x.id))||tasks.some(t=>t.project===x.id)||reported.some(r=>r.project===x.id))&&(!e||issues.some(i=>i.projects.includes(x.id))||tasks.some(t=>t.project===x.id)||reported.some(r=>r.project===x.id&&r.epic===e)));
 const complete=(e?data.epics.some(x=>x.key===e)&&data.epics.filter(x=>x.key===e).every(x=>x.scope_complete):data.totals.scope_complete);
 return {p,e,team,issues,tasks,epics,projects,reported,totals:sumMetrics(issues,complete)};
}
function renderMetrics(s) {
 const m=s.totals,area=$('metrics');area.replaceChildren();
 $('scope-estimate').textContent=`Known-scope estimate: ${range(m.estimate)} (low / likely / high). ${m.scope_complete?'Enumerated imported scope.':'Partial or unavailable scope; full total unknown.'}`;
 const entries=[['Verified progress',m.percent===null?'—':m.percent+'%',`${m.verified_issues} verified / ${m.known_issues} known issues${m.percent===null?' · scope unavailable or incomplete':''}`],['Known issues',String(m.known_issues),`${s.tasks.length} local tasks · ${s.epics.length} epics`],['Likely remaining',m.remaining_estimate?moneyless(m.remaining_estimate.likely)+' h':'—',m.remaining_estimate?`Low ${moneyless(m.remaining_estimate.low)} · High ${moneyless(m.remaining_estimate.high)} · ${m.scope_complete?'enumerated scope':'known subset'}`:'No enumerated work to estimate'],['Measured Codex time',m.actual_machine_hours===null?'—':moneyless(m.actual_machine_hours)+' h',`${m.measured_issues} / ${m.known_issues} issues measured · ${m.measured_issues===0?'no measured actuals':m.measured_issues<m.known_issues?'known subset only':'recorded actuals'}`]];
 $('estimate-summary').replaceChildren();
 [['Known-scope estimate',range(m.estimate),'Low / likely / high · '+(m.scope_complete?'enumerated scope':'known subset only')],['Remaining estimate',range(m.remaining_estimate),'Excludes verified issues'],['Measured actual',m.actual_machine_hours===null?'Unavailable':moneyless(m.actual_machine_hours)+' h',`${m.measured_issues} / ${m.known_issues} issues measured`]].forEach(([title,value,detail])=>{const card=el('article',undefined,'metric');card.append(el('span',title,'label'),el('strong',value),el('small',detail));$('estimate-summary').append(card);});
 entries.forEach(([label,value,detail])=>{const card=el('article',undefined,'metric');card.append(el('span',label,'label'),el('strong',value),el('small',detail));area.append(card);});
}
function renderProjects(s) {
 const area=$('projects');area.replaceChildren();
 const projects=s.projects;
 $('project-count').textContent=`${projects.length} projects · dynamic inventory`;
 projects.forEach(p=>{const card=el('button',undefined,'project-card'+(s.p===p.id?' selected':''));card.type='button';card.setAttribute('aria-label',`Filter ${p.name}`);
 const top=el('div',undefined,'project-top');top.append(el('h3',p.name),el('span',p.kind==='coordination'?'Coordination':p.registered?'Registered':'Unregistered','tag'));card.append(top);
 const selected=s.issues.filter(i=>i.projects.includes(p.id));
 const m=sumMetrics(selected,s.totals.scope_complete),track=el('div',undefined,'progress-track'),fill=el('div',undefined,'progress-fill');fill.style.width=(m.percent||0)+'%';track.append(fill);card.append(track);
 card.append(el('strong',m.percent===null?'No verified percentage':m.percent+'% verified'));
 card.append(el('p',`${selected.length} known issues · ${s.tasks.filter(t=>t.project===p.id).length} local tasks`));
 let allocated={low:0,likely:0,high:0};selected.forEach(i=>{const estimate=issueEstimate(i);Object.keys(allocated).forEach(k=>allocated[k]+=estimate[k]/i.projects.length);});
 card.append(el('p',`Allocated model: ${range(selected.length?allocated:null)}`));
 card.append(el('p',selected.length?(m.scope_complete?'Enumerated scope · low / likely / high':'Known subset only · full estimate unknown'):'No imported issue scope'));
 if(!s.team&&p.reported_estimate)card.append(el('p','Reported project estimate: '+range(p.reported_estimate)));
 if(!s.team&&p.reported_actual_machine_hours!==null)card.append(el('p','Reported project actual: '+moneyless(p.reported_actual_machine_hours)+' h'));
 card.addEventListener('click',()=>{$('project').value=s.p===p.id?'':p.id;render();});area.append(card);});
 if(!projects.length)empty(area,'No matching projects','Choose another filter or add project statistics to the mailbox.');
}
function svgEl(tag,attrs={},text) {const n=document.createElementNS('http://www.w3.org/2000/svg',tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));if(text!==undefined)n.textContent=text;return n;}
function cycleEdges(edges) {
 const adjacency=new Map();edges.forEach(e=>{if(!adjacency.has(e.from))adjacency.set(e.from,[]);adjacency.get(e.from).push(e.to);});
 const reaches=(start,target)=>{const queue=[start],seen=new Set();while(queue.length){const n=queue.pop();if(n===target)return true;if(seen.has(n))continue;seen.add(n);queue.push(...(adjacency.get(n)||[]));}return false;};
 return new Set(edges.filter(e=>reaches(e.to,e.from)).map(e=>e.from+'>'+e.to));
}
function renderMap(s) {
 const area=$('map'),list=$('dependency-list');area.replaceChildren();list.replaceChildren();
 const selected=new Set(s.issues.map(i=>i.key)),taskSelected=new Set(s.tasks.map(t=>t.id));
 const relevant=data.dependencies.filter(e=>selected.has(e.from)||selected.has(e.to));
 const taskEdges=data.task_dependencies.filter(e=>taskSelected.has(e.from)||taskSelected.has(e.to));
 const external=data.external_dependencies.filter(d=>s.epics.some(e=>e.key===d.epic));
 const nodes=new Map();s.issues.forEach(i=>nodes.set(i.key,{label:i.key,detail:i.title,status:i.local_status,kind:'issue'}));
 relevant.forEach(e=>[e.from,e.to].forEach(k=>{if(!nodes.has(k))nodes.set(k,{label:k,detail:data.issues.some(i=>i.key===k)?'Outside selection':'Unresolved prerequisite',boundary:true,kind:'issue'});}));
 s.tasks.forEach(t=>nodes.set('task:'+t.id,{label:'Task · '+t.id,detail:t.title,status:t.status,kind:'task'}));
 taskEdges.forEach(e=>[e.from,e.to].forEach(k=>{if(!nodes.has('task:'+k))nodes.set('task:'+k,{label:'Task · '+k,detail:'Outside selection / unresolved',boundary:true,kind:'task'});}));
 external.forEach(d=>{if(!nodes.has(d.key))nodes.set(d.key,{label:d.key,detail:'External Epic dependency',boundary:true,kind:'issue'});});
 if(!nodes.size&&!s.epics.length){empty(area,'The map is ready for your scope.','Import Epic issues or local tasks to see their dependencies. Projects remain visible above.');return;}
 const displayedProjects=s.projects;
 const h=Math.max(nodes.size,displayedProjects.length,s.epics.length)*74+78;
 const svg=svgEl('svg',{width:960,height:h,viewBox:`0 0 960 ${h}`,role:'img','aria-label':'Project, epic, issue and task dependency map'});
 const defs=svgEl('defs');for(const [id,color] of [['arrow','#4a7bc3'],['cycle-arrow','#d7745e']]){const m=svgEl('marker',{id,viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:6,markerHeight:6,orient:'auto-start-reverse'});m.append(svgEl('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:color}));defs.append(m);}svg.append(defs);
 [['PROJECT',20],['EPIC',265],['ISSUE / LOCAL TASK',520]].forEach(([text,x])=>svg.append(svgEl('text',{x,y:26,class:'lane'},text)));
 const pos=new Map(),projectPos=new Map(),epicPos=new Map();
 displayedProjects.forEach((p,i)=>projectPos.set(p.id,{x:20,y:48+i*74,label:p.name,detail:p.kind==='coordination'?'Coordination group':p.registered?'Project':'Unregistered project'}));
 s.epics.forEach((e,i)=>epicPos.set(e.key,{x:265,y:48+i*74,label:e.key,detail:e.scope_complete?'Complete scope':'Incomplete scope'}));
 [...nodes.entries()].forEach(([key,n],i)=>pos.set(key,{x:520,y:48+i*74,...n}));
 const line=(a,b)=>{if(a&&b)svg.append(svgEl('path',{d:`M${a.x+205} ${a.y+24} C${a.x+235} ${a.y+24} ${b.x-25} ${b.y+24} ${b.x} ${b.y+24}`,stroke:'#d6e0eb','stroke-width':1.2,fill:'none'}));};
 s.issues.forEach(i=>{i.projects.forEach(p=>i.epic_keys.forEach(e=>line(projectPos.get(p),epicPos.get(e))));i.epic_keys.forEach(e=>line(epicPos.get(e),pos.get(i.key)));});
 s.tasks.forEach(t=>line(projectPos.get(t.project),pos.get('task:'+t.id)));
 s.reported.forEach(r=>line(projectPos.get(r.project),epicPos.get(r.epic)));
 external.forEach(d=>line(epicPos.get(d.epic),pos.get(d.key)));
 const edges=[...relevant,...taskEdges.map(e=>({...e,from:'task:'+e.from,to:'task:'+e.to}))];const cycles=cycleEdges(edges);
 edges.forEach((e,index)=>{const a=pos.get(e.from),b=pos.get(e.to);if(!a||!b)return;const cycle=cycles.has(e.from+'>'+e.to);const far=795+(index%7)*17;svg.append(svgEl('path',{d:`M${a.x+205} ${a.y+24} C${far} ${a.y+24} ${far} ${b.y+24} ${b.x+205} ${b.y+24}`,stroke:cycle?'#d7745e':'#4a7bc3','stroke-width':1.6,'stroke-dasharray':e.unresolved?'5 4':'none',fill:'none','marker-end':`url(#${cycle?'cycle-arrow':'arrow'})`}));list.append(el('span',`${e.from} → ${e.to}${cycle?' · cycle':''}${e.unresolved?' · unresolved':''}`,cycle?'cycle':''));});
 const draw=n=>{const g=svgEl('g');g.append(svgEl('title',{},n.label+' — '+n.detail));g.append(svgEl('rect',{x:n.x,y:n.y,width:205,height:52,rx:6,fill:n.boundary?'#f3f6fa':'#fff',stroke:n.status==='verified_done'?'#8ecab5':'#d5e0ec','stroke-dasharray':n.boundary?'4 3':'none'}));g.append(svgEl('text',{x:n.x+12,y:n.y+21,'font-weight':600},String(n.label).slice(0,29)));g.append(svgEl('text',{x:n.x+12,y:n.y+38,'font-size':9,fill:'#7b8e9e'},String(n.detail).slice(0,34)));svg.append(g);};
 projectPos.forEach(draw);epicPos.forEach(draw);pos.forEach(draw);area.append(svg);
}
function renderIssues(s) {
 const tbody=$('issues');tbody.replaceChildren();$('issue-count').textContent=`${s.issues.length} unique issues`;
 s.issues.forEach(i=>{const row=el('tr'),key=el('td');key.append(el('strong',i.key),el('span',i.title));if(i.conflict)key.append(el('small','Conflicting snapshots — reconcile source'));const members=el('td',i.projects.join(', ')||'Unmapped');members.append(el('small','Team: '+((i.teams||[]).join(', ')||'Unassigned')));members.append(el('small',i.epic_keys.join(', ')));const source=el('td',i.source_status);const local=el('td');local.append(status(i.local_status));const estimate=el('td',range(issueEstimate(i)));estimate.append(el('small',i.estimate?'Explicit estimate':'Model · low / likely / high'));row.append(key,members,source,local,estimate);tbody.append(row);});
 if(!s.issues.length){const r=el('tr'),c=el('td');c.colSpan=5;empty(c,'No issues in this view','No imported scope is not zero progress. Add an Epic snapshot or explore the isolated demo.');r.append(c);tbody.append(r);}
}
function renderTasks(s) {const area=$('tasks');area.replaceChildren();$('task-count').textContent=`${s.tasks.length} local tasks`;s.tasks.forEach(t=>{const c=el('article',undefined,'task');c.append(el('strong',t.title),status(t.status),el('p',`${t.project} · ${(t.teams||[]).join(', ')||'Unassigned'} · ${t.issue_key||'No Jira mapping'}`),el('p',`${t.evidenced?'Completion evidence recorded':'Not verified'} · ${t.id}`));area.append(c);});if(!s.tasks.length)empty(area,'No local tasks yet','Tasks appear here even before they are mapped to Jira.');}
function renderReported(s) {const area=$('reported');area.replaceChildren();const items=s.reported;items.forEach(r=>{const d=el('details');d.append(el('summary',`${r.project||'All projects'} / ${r.epic||'Project snapshot'} · ${r.source}`),el('p',r.updated_at?'Updated '+r.updated_at:'Timestamp unavailable','muted'),el('pre',JSON.stringify(r.values,null,2)));area.append(d);});if(!items.length)empty(area,'No aggregate statistics recorded',s.team?'No explicitly team-scoped aggregates match. Whole-project totals are hidden for team filters.':'This panel preserves reported figures separately from verified issue progress.');}
function render(){if(!data)return;const s=selection();renderMetrics(s);renderProjects(s);renderMap(s);renderIssues(s);renderTasks(s);renderReported(s);$('warnings').replaceChildren(...data.warnings.map(w=>el('li',w)));$('warning-count').textContent=`(${data.warnings.length})`;$('warnings-panel').open=!!data.warnings.length;$('demo-banner').hidden=data.mode!=='demo';$('freshness').textContent=`${data.mode==='demo'?'Demo':'Mailbox'} read ${new Date(data.generated_at).toLocaleTimeString()}`;scenario();}
function populate(id,items,key,label,all){const select=$(id),previous=select.value;select.replaceChildren();const option=el('option',all);option.value='';select.append(option);items.forEach(item=>{const o=el('option',item[label]);o.value=item[key];select.append(o);});if(items.some(i=>i[key]===previous))select.value=previous;}
async function load(){const ticket=++request;$('error').hidden=true;$('refresh').disabled=true;const params=new URLSearchParams({mode:$('demo').checked?'demo':'live'});['low','likely','high','review_multiplier'].forEach(k=>params.set(k,$(k).value));try{const response=await fetch('/api/dashboard?'+params);const payload=await response.json();if(!response.ok)throw new Error(payload.error?.message||'Unable to read mailbox');if(ticket!==request)return;data=payload;populate('project',data.projects,'id','name','All projects');populate('epic',data.epics,'key','key','All epics');render();}catch(e){if(ticket!==request)return;$('error').textContent=`Could not refresh: ${e.message}. ${data?'Last successful snapshot is still displayed.':'Check the mailbox mount and try again.'}`;$('error').hidden=false;}finally{if(ticket===request)$('refresh').disabled=false;}}
function scenario(){const count=Number($('scenario-count').value);const model=data?.estimate_method;if(!model)return;$('scenario-result').textContent=Number.isFinite(count)&&count>=0&&count<=10000?range(Object.fromEntries(['low','likely','high'].map(k=>[k,count*model[k]*model.review_multiplier]))):'Enter a count from 0 to 10,000';}
$('refresh').addEventListener('click',load);$('demo').addEventListener('change',()=>{$('project').value='';$('epic').value='';load();});$('team').addEventListener('change',render);$('project').addEventListener('change',render);$('epic').addEventListener('change',render);$('model-form').addEventListener('submit',e=>{e.preventDefault();load();});$('scenario-count').addEventListener('input',scenario);load();

function syncThemeButton(){const dark=document.documentElement.dataset.theme!=='light';$('theme-toggle').textContent=dark?'☀ Light theme':'☾ Dark theme';$('theme-toggle').setAttribute('aria-label',dark?'Switch to light theme':'Switch to dark theme');}
$('theme-toggle').addEventListener('click',()=>{const next=document.documentElement.dataset.theme==='light'?'dark':'light';document.documentElement.dataset.theme=next;try{localStorage.setItem('mailbox-theme',next);}catch(_){}syncThemeButton();});syncThemeButton();

const viewTitles={overview:['A clear view of the work.','Dependencies, verified progress and Codex effort in one place.'],dependencies:['See what depends on what.','Follow project, Epic, issue and local task relationships.'],tasks:['From scope to verified work.','Jira snapshots and local execution, with evidence kept distinct.'],estimates:['Plan the effort explicitly.','Explore Codex machine-hours with transparent assumptions.'],sources:['Know where the numbers come from.','Reported snapshots, provenance and data-quality warnings.']};
function selectView(){const requested=location.hash.slice(1);const key=Object.hasOwn(viewTitles,requested)?requested:'overview';document.querySelectorAll('.view-tabs [role=tab]').forEach(tab=>{const active=tab.id==='tab-'+key;tab.setAttribute('aria-selected',String(active));tab.tabIndex=active?0:-1;});document.querySelectorAll('.page-view').forEach(view=>view.hidden=view.id!=='view-'+key);document.querySelector('.page-heading h1').textContent=viewTitles[key][0];document.querySelector('.page-heading .subtitle').textContent=viewTitles[key][1];document.querySelector('.page-heading .eyebrow').textContent='PROJECT OPERATIONS / '+key.toUpperCase();document.title='Mailbox · '+key[0].toUpperCase()+key.slice(1);}
document.querySelector('.view-tabs').addEventListener('keydown',event=>{const tabs=[...document.querySelectorAll('.view-tabs [role=tab]')],index=tabs.indexOf(document.activeElement);if(index<0)return;let next;if(event.key==='ArrowRight')next=(index+1)%tabs.length;else if(event.key==='ArrowLeft')next=(index+tabs.length-1)%tabs.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=tabs.length-1;else return;event.preventDefault();tabs[next].focus();location.hash=tabs[next].getAttribute('href');});
window.addEventListener('hashchange',()=>{selectView();window.scrollTo({top:0});});selectView();
