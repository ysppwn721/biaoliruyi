'use strict';
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let workspace = null, currentView = 'overview', filter = 'all', health = null, graphFact = null;
const statusNames = {consistent:'仍成立', inconsistent:'已失效', unverifiable:'无法判断'};
const kindNames = {quote:'数值引用', growth:'增长率', ranking:'排名', threshold:'阈值判断', chart:'图表数据'};
const classNames = {consistent:'green', inconsistent:'red', unverifiable:'amber'};
let toastTimer, pendingUploads = [];
const factDrafts = new Map();
function drafts() {
  if (!factDrafts.has(workspace.id)) factDrafts.set(workspace.id, new Map());
  return factDrafts.get(workspace.id);
}
function trackDraft(input) {
  const fact = workspace.facts.find(f => f.id === input.dataset.fact);
  const value = input.value;
  if (value.trim() !== '' && Number(value) === fact.value) drafts().delete(fact.id);
  else drafts().set(fact.id, value);
  renderDraftStatus();
}
function renderDraftStatus() {
  const count = drafts().size;
  const status = $('factDraftStatus');
  if (status) status.textContent = count ? `${count} 项数值尚未应用，切换视图时会保留` : '当前显示已保存的数据';
  const discard = $('discardDrafts');
  if (discard) discard.classList.toggle('hidden', !count);
  $('saveFacts').disabled = !count;
  document.querySelectorAll('[data-fact]').forEach(input => input.closest('.fact-row').classList.toggle('edited', drafts().has(input.dataset.fact)));
}
function renderUploadFiles() {
  const list = $('uploadFileList');
  if (!list) return;
  const total = pendingUploads.reduce((sum, file) => sum + file.size, 0);
  list.innerHTML = pendingUploads.map((file, index) => {
    const ext = file.name.split('.').pop().toLowerCase();
    const type = ext === 'xlsx' ? 'Excel' : ext === 'docx' ? 'Word' : 'PPT';
    return `<div class="upload-file-row"><span class="file-icon ${ext === 'docx' ? 'docx' : ext === 'pptx' ? 'pptx' : ''}">${ext === 'xlsx' ? 'X' : ext === 'docx' ? 'W' : 'P'}</span><div><strong>${esc(file.name)}</strong><small>${type} · ${(file.size / 1024 / 1024).toFixed(2)} MB</small></div><button type="button" class="icon-button upload-remove" data-upload-remove="${index}" aria-label="移除 ${esc(file.name)}">×</button></div>`;
  }).join('');
  const status = $('uploadFileStatus');
  if (status) status.textContent = pendingUploads.length ? `已加入 ${pendingUploads.length} 份文件 · ${(total / 1024 / 1024).toFixed(2)} / 30 MB` : '尚未加入文件';
  const submit = $('uploadSubmit');
  if (submit) submit.disabled = pendingUploads.length < 2 || pendingUploads.length > 10 || total > 30 * 1024 * 1024;
  list.querySelectorAll('[data-upload-remove]').forEach(button => button.onclick = () => {
    pendingUploads.splice(Number(button.dataset.uploadRemove), 1);
    renderUploadFiles();
  });
}
function statusBadge(c, r=resultOf(c)) {
  return `<span class="badge ${c.confirmed ? classNames[r.status] : 'amber'}">${c.confirmed ? esc(statusNames[r.status]) : '待确认 · ' + esc(statusNames[r.status])}</span>`;
}

function toast(message, error=false) {
  $('toast').textContent = message; $('toast').className = 'show' + (error ? ' error' : '');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').className='', 5000);
}
async function api(path, options={}) {
  const response = await fetch(path, options);
  let data;
  try { data = await response.json(); } catch { throw new Error('服务器没有返回有效结果，请检查连接'); }
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '请求参数不正确，请刷新后重试');
  return data;
}
async function busy(label, action) {
  $('busyText').textContent=label; $('busy').classList.remove('hidden');
  try { return await action(); } catch(e) { toast(e.message, true); return null; }
  finally { $('busy').classList.add('hidden'); }
}
async function post(action, payload, label) {
  const result = await busy(label, () => api(`/api/projects/${workspace.id}/${action}`, {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({revision:workspace.revision,...payload})
  }));
  if (result) { workspace=result; render(); await refreshProjects(); }
  return result;
}
function modal(title, html) { $('modalTitle').textContent=title; $('modalContent').innerHTML=html; if (!$('modal').open) $('modal').showModal(); }
function closeModal() { $('modal').close(); }
function localTime(s) { return new Date(s).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}); }
function fileOf(c) { return workspace.documents.find(d=>d.id===c.file_id); }
function resultOf(c) { return workspace.checks.find(r=>r.claim_id===c.id); }
function factName(f) { return `${f.subject==='总计'?'':f.subject+' · '}${f.period}${f.metric}`; }
function downloadLinks() {
  return workspace.documents.filter(d=>d.kind!=='xlsx').map(d=>`<a class="button secondary small" href="${esc(d.download_url)}" download>↓ ${d.kind==='docx'?'Word':'PPT'} · ${esc(d.name)}</a>`).join('');
}
function deliveryModal() {
  const s=workspace.summary;
  modal('下载 Word 与 PPT',`<p class="modal-intro">项目：${esc(workspace.name)} · 版本 ${workspace.revision}</p>${s.inconsistent?`<p class="hint">还有 ${s.inconsistent} 项内容与当前数据不一致。下方下载的是当前版本，请先完成修复。</p>`:'<p class="modal-intro">已识别论断中没有计算不一致项。点击下方按钮下载当前文件。</p>'}${s.pending?`<p class="hint">仍有 ${s.pending} 项来源待确认，候选计算结果不能代替人工确认。</p>`:''}${s.unverifiable?`<p class="hint">另有 ${s.unverifiable} 项无法判断，需要人工复核。</p>`:''}<div class="delivery-links">${downloadLinks()}</div><div class="modal-actions">${s.repairable?'<button class="button primary" id="deliveryRepair">预览并修复剩余内容</button>':''}<a class="button secondary" href="/api/projects/${workspace.id}/export" download>下载完整成果包</a></div>`);
  if($('deliveryRepair'))$('deliveryRepair').onclick=repairModal;
}
function afterDataUpdate() {
  if(workspace.summary.repairable) repairModal();
  else if(workspace.summary.inconsistent) {
    modal('数据已更新，成果尚未修复',`<p class="modal-intro">发现 ${workspace.summary.inconsistent} 项不一致内容，需要先确认对应来源，才能生成修改后的 Word / PPT。</p><div class="modal-actions"><button class="button primary" id="nextConfirm">审阅候选来源</button></div>`);
    $('nextConfirm').onclick=confirmAllModal;
  } else deliveryModal();
}

async function refreshProjects() {
  const projects=await api('/api/projects');
  $('projects').innerHTML=projects.map(p=>`<button class="project-link ${workspace?.id===p.id?'active':''}" data-project="${p.id}">${esc(p.name)}</button>`).join('');
  return projects;
}
async function loadProject(id) {
  const w=await busy('正在读取项目',()=>api('/api/projects/'+id));
  if(w){workspace=w;graphFact=null;localStorage.setItem('zhilian-project',w.id);render();await refreshProjects();}
}
function switchView(view) {
  currentView=view;
  document.querySelectorAll('.nav-item').forEach(b=>b.classList.toggle('active',b.dataset.view===view));
  const labels={overview:'一致性工作台',sources:'来源与文件',graph:'证据依赖图',history:'变更记录'};
  $('breadcrumb').textContent=labels[view];
  if(workspace)render();
}
function render() {
  $('welcome').classList.toggle('hidden',!!workspace);$('workspace').classList.toggle('hidden',!workspace);
  if(!workspace)return;
  const w=workspace,s=w.summary;
  for (const f of w.facts) if (drafts().has(f.id) && drafts().get(f.id).trim() !== '' && Number(drafts().get(f.id)) === f.value) drafts().delete(f.id);
  $('projectName').textContent=w.name;
  $('workspaceEyebrow').textContent=w.demo?'DEMO PROJECT · 模拟数据':'PROJECT WORKSPACE';
  $('projectSubtitle').textContent=`${s.documents} 份文件 · ${s.facts} 条来源事实 · 版本 ${w.revision} · 数据与成果均保留历史版本`;
  ['overview','sources','graph','history'].forEach(v=>$(v+'View').classList.toggle('hidden',currentView!==v));
  $('undoButton').disabled=!w.history.length;
  const verified=w.claims.filter(c=>c.confirmed&&resultOf(c).status==='consistent').length;
  const stats=[['已识别论断',s.claims,'','逐项核验已识别的受支持表达','◇'],['已确认且成立',verified,'success','来源已确认，计算结果一致','✓'],['计算不一致',s.inconsistent,'danger','确认来源后可预览局部修复','↗'],['来源待确认',s.pending,'','候选结果须经人工核对','◷']];
  $('stats').innerHTML=stats.map(([label,value,cls,note,icon])=>`<div class="stat"><div class="stat-top">${label}<span class="stat-icon">${icon}</span></div><div class="stat-value ${cls}">${value}<span style="font-size:11px;color:#9bab9d;font-weight:400;margin-left:7px">项</span></div><div class="stat-bottom">${note}</div></div>`).join('');
  $('successBanner').innerHTML=s.inconsistent?`<div class="banner">${s.inconsistent} 项内容尚未更新到 Word / PPT。${s.repairable?'请预览并确认修复。':'请先确认来源关联。'} <button class="button primary small" id="continueRepair">${s.repairable?'预览修复并生成文件':'审阅候选来源'}</button></div>`:w.last_repair?`<div class="banner">✓ 已修复 ${w.last_repair.count} 项并重新验证。${s.pending?`另有 ${s.pending} 项来源待确认。`:''}<div class="delivery-links">${downloadLinks()}</div></div>`:'';
  if($('continueRepair'))$('continueRepair').onclick=s.repairable?repairModal:confirmAllModal;
  $('workflow').innerHTML=`<span class="step done"><i>✓</i> 导入文件</span><span class="rule"></span><span class="step ${s.pending===0?'done':''}"><i>${s.pending===0?'✓':'2'}</i> 确认来源</span><span class="rule"></span><span class="step ${s.pending===0?'done':''}"><i>3</i> 验证结论</span><span class="rule"></span><span class="step ${w.last_repair?'done':''}"><i>4</i> 修复与导出</span>`;
  $('suggestButton').disabled=!health?.model.enabled;
  $('suggestButton').title=health?.model.enabled?'将待确认论断及事实元数据发送给配置的模型':'模型未配置。使用规则候选和人工确认也可完成流程';
  $('filters').querySelectorAll('button').forEach(b=>b.classList.toggle('selected',b.dataset.filter===filter));
  const claims=w.claims.filter(c=>filter==='all'||(filter==='pending'?!c.confirmed:resultOf(c).status===filter));
  $('claimCount').textContent=`显示 ${claims.length} 项 · 仅覆盖已识别的论断`;
  $('claims').innerHTML=claims.length?claims.map(c=>{
    const r=resultOf(c),f=fileOf(c),names=c.refs.map(id=>w.facts.find(f=>f.id===id)).filter(Boolean).map(f=>`${factName(f)} ${f.value??'缺失'}${f.unit}`);
    return `<article class="claim-card ${r.status==='inconsistent'?'problem':''}"><div class="claim-top"><span class="file-tag">${f.kind==='docx'?'W':f.kind==='pptx'?'P':'X'} · ${esc(kindNames[c.kind])}</span><span class="place" title="${esc(f.name+' · '+c.label)}">${esc(c.label)}</span><span class="badge ${classNames[r.status]}">${esc(statusNames[r.status])}${c.confirmed?'':' · 待确认'}</span></div><div class="claim-text">${esc(c.original)}</div>${r.status==='inconsistent'?`<div class="suggested"><span>建议更新为</span>${esc(r.expected)}</div>`:''}${r.status==='unverifiable'?`<div class="hint">${esc(r.reason)}</div>`:''}<div class="claim-bottom"><span class="evidence-label" title="${esc(names.join('；'))}">${c.confirmed?'✓ 来源已确认':'◷ 候选来源'} · ${esc(names.join(' / ')||'请手动指定')}</span><button class="link-button" data-claim="${c.id}">查看依据 →</button></div></article>`;
  }).join(''):'<div class="empty-list">当前筛选下没有论断。</div>';
  $('confirmAll').disabled=!w.claims.some(c=>!c.confirmed&&c.refs.length&&resultOf(c).status!=='unverifiable');
  $('reviewRepairs').disabled=!s.repairable;
  $('repairHint').textContent=s.repairable?`${s.repairable} 项已确认来源的结论可修复`:'确认来源后，仅修复已失效的结论';
  $('factInputs').innerHTML=w.facts.map(f=>`<div class="fact-row"><label for="fact-${esc(f.id)}">${esc(factName(f))}<small>${esc(f.sheet+'!'+f.cell)}</small></label><div class="fact-field"><input id="fact-${esc(f.id)}" data-fact="${esc(f.id)}" type="number" step="any" value="${f.value??''}" aria-label="${esc(factName(f))}"><span>${esc(f.unit)}</span></div></div>`).join('');
  if (!$('factDraftStatus')) $('factInputs').insertAdjacentHTML('afterend','<div class="draft-status" id="factDraftStatus"></div><button class="button text full hidden" id="discardDrafts">撤销未应用输入</button>');
  $('demoChange').classList.toggle('hidden',!w.demo);
  document.querySelectorAll('[data-fact]').forEach(input => {if(drafts().has(input.dataset.fact))input.value=drafts().get(input.dataset.fact);});
  renderDraftStatus();
  renderSources();renderGraph();renderHistory();
  document.querySelectorAll('[data-fact]').forEach(input => input.oninput=()=>trackDraft(input));
  $('discardDrafts').onclick=()=>{drafts().clear();render();toast('已撤销尚未应用的输入');};
}
function renderSources(){
  const w=workspace, segments=w.unmatched_segments||[];
  $('sourcesView').innerHTML=`<div class="file-grid">${w.documents.map(d=>`<article class="file-card"><span class="file-icon ${d.kind}">${d.kind==='xlsx'?'X':d.kind==='docx'?'W':'P'}</span><h3>${esc(d.name)}</h3><p>${d.kind==='xlsx'?'主要数据源':'关联成果'} · SHA256 ${esc(d.sha256.slice(0,12))}…</p><a class="button secondary small" href="${d.download_url}">↓ 下载当前版本</a></article>`).join('')}</div><section class="panel"><h2>结构化事实表</h2><p class="hint">主体、期间、单位与统计口径共同决定一条事实的含义。</p><div class="table-scroll"><table class="data-table"><thead><tr><th>ID</th><th>主体</th><th>指标</th><th>期间</th><th>数值</th><th>单位</th><th>口径</th><th>位置</th></tr></thead><tbody>${w.facts.map(f=>`<tr>${[f.id,f.subject,f.metric,f.period,f.value??'缺失',f.unit,f.scope,f.sheet+'!'+f.cell].map(x=>`<td>${esc(x)}</td>`).join('')}</tr>`).join('')}</tbody></table></div></section><section class="panel" style="margin-top:20px"><h2>检查范围与未识别内容</h2><p class="hint">${segments.length} 个片段没有覆盖受支持论断，可能是标题、普通说明或不支持的表达，不能据此认定正确。</p><ul class="warning-list">${w.documents.flatMap(d=>(d.warnings||[]).map(x=>`<li>${esc(d.name)}：${esc(x)}</li>`)).join('')}<li>不验证业务因果关系或主观评价；不保证任意排版和嵌入对象保真。</li></ul><details><summary class="link-button">查看未识别文本</summary>${segments.map(b=>`<div class="evidence-block"><small>${esc(b.label)}</small><p>${esc(b.text)}</p></div>`).join('')||'<p class="hint">所有可读正文片段都已有受支持论断覆盖。</p>'}</details></section>`;
}
function renderGraph(){
  const w=workspace,cs=graphFact?w.claims.filter(c=>c.refs.includes(graphFact)):w.claims;
  $('graphView').innerHTML=`<p class="graph-note">选择左侧事实，查看依赖它的论断。虚线含义的候选关系须经人工确认，才可用于自动修复。</p><div class="graph-columns"><div class="graph-column"><h3>来源事实 · ${w.facts.length}</h3><button class="link-button" id="clearGraph" style="margin-bottom:15px">显示全部关联</button>${w.facts.map(f=>`<button class="graph-node ${graphFact===f.id?'selected':''}" style="width:100%;text-align:left" data-graph-fact="${esc(f.id)}">${esc(factName(f))}<small>${esc(f.value)} ${esc(f.unit)} · ${esc(f.scope)}</small></button>`).join('')}</div><div class="graph-arrow">→</div><div class="graph-column"><h3>依赖论断 · ${cs.length}</h3>${cs.map(c=>`<div class="graph-node"><div style="display:flex;justify-content:space-between;gap:10px"><span>${esc(c.original)}</span><span class="badge ${classNames[resultOf(c).status]}">${statusNames[resultOf(c).status]}</span></div><small>${esc(fileOf(c).name)} · ${esc(c.label)}</small><div class="graph-ref">${c.confirmed?'已确认':'候选'} · ${esc(c.refs.join(' + '))}</div><button class="link-button" data-claim="${c.id}" style="margin-top:8px">查看计算与依据 →</button></div>`).join('')||'<div class="empty-list">没有关联论断</div>'}</div></div>`;
}
function renderHistory(){
  $('historyView').innerHTML=`<section class="panel"><h2>变更与核验记录</h2><p class="hint">文件变更创建新版本；确认来源和模型建议也会留下记录。</p>${workspace.audit.slice().reverse().map(a=>`<div class="history-row"><time>${esc(localTime(a.time))}</time><div><h3>${esc(a.event)}</h3><p>${esc(a.detail)}</p></div></div>`).join('')}</section>`;
}
function uploadModal(){
  pendingUploads = [];
  modal('导入文件，建立项目',`<p class="modal-intro">一份 Excel 事实表，加一份或多份 Word / PPT。可以分多次选择，后续选择会加入列表，不会替换之前的文件。</p><form id="uploadForm"><label class="field-label" for="uploadName">项目名称</label><input id="uploadName" class="text-input" name="name" value="我的数据分析项目" maxlength="100" required><label class="dropzone"><h3>选择并加入文件</h3><p>可重复打开文件选择器；最多10份，合计不超过30MB</p><input id="uploadFiles" type="file" accept=".xlsx,.docx,.pptx" multiple></label><div id="uploadFileList" class="upload-file-list"></div><div id="uploadFileStatus" class="upload-file-status">尚未加入文件</div><a class="link-button" href="/api/template">↓ 下载 Excel 事实表模板</a><p class="hint">需要一份 .xlsx 和至少一份 .docx / .pptx。Excel 首行包含：事实ID、主体、指标、期间、数值、单位、统计口径。</p><div class="modal-actions"><button type="button" class="button secondary" id="modalDemo">先体验演示</button><button class="button primary" id="uploadSubmit" type="submit" disabled>导入并识别</button></div></form>`);
  $('modalDemo').onclick=demo;
  $('uploadFiles').onchange = event => {
    const incoming = [...event.target.files];
    for (const file of incoming) {
      const ext = file.name.split('.').pop().toLowerCase();
      const duplicate = pendingUploads.some(old => old.name === file.name && old.size === file.size && old.lastModified === file.lastModified);
      if (!['xlsx', 'docx', 'pptx'].includes(ext) || duplicate) continue;
      if (pendingUploads.length < 10) pendingUploads.push(file);
    }
    event.target.value = '';
    renderUploadFiles();
  };
  $('uploadForm').onsubmit=async e=>{
    e.preventDefault();
    const total = pendingUploads.reduce((sum, file) => sum + file.size, 0);
    const extensions = pendingUploads.map(file => file.name.split('.').pop().toLowerCase());
    if (pendingUploads.length < 2 || !extensions.includes('xlsx') || !extensions.some(ext => ext === 'docx' || ext === 'pptx')) { toast('请加入一份 Excel 和至少一份 Word / PPT', true); return; }
    if (total > 30 * 1024 * 1024) { toast('每批上传总大小不超过30MB', true); return; }
    const form = new FormData();
    form.set('name', $('uploadName').value);
    pendingUploads.forEach(file => form.append('files', file, file.name));
    const result=await busy('解析文件并识别论断',()=>api('/api/projects',{method:'POST',body:form}));
    if(result){closeModal();workspace=result;switchView('overview');localStorage.setItem('zhilian-project',result.id);await refreshProjects();toast('导入完成，请审阅并确认来源关联');}
  };
  renderUploadFiles();
}
function importSourceModal(){
  const projectId=workspace.id, revision=workspace.revision;
  modal('导入更新后的 Excel',`<p class="modal-intro">在 Excel / WPS 中保存后选择文件。先查看数值差异和受影响结论，确认后建立新版本。</p><form id="sourceForm"><label class="dropzone"><h3>选择更新后的源表</h3><p>一份 .xlsx，最大 30MB</p><input type="file" name="file" accept=".xlsx" required></label><p class="hint">事实ID、主体、指标、期间、单位和统计口径需保持一致；支持调整行顺序。若增删事实或改变含义，请建立新项目。</p><div class="modal-actions"><button class="button primary" type="submit">查看变更与影响 →</button></div></form>`);
  $('sourceForm').onsubmit=async e=>{
    e.preventDefault();
    const form=new FormData(e.target);form.set('revision',revision);
    const file=form.get('file');
    if(file.size>30*1024*1024){toast('更新表不超过30MB',true);return;}
    const preview=await busy('分析 Excel 变更及结论影响',()=>api(`/api/projects/${projectId}/source/preview`,{method:'POST',body:form}));
    if(!preview)return;
    sourcePreviewModal(preview, file, projectId, revision);
  };
}
function sourcePreviewModal(preview, file, projectId, revision){
  const facts=new Map(workspace.facts.map(f=>[f.id,f]));
  modal('确认源表变更',`<p class="modal-intro">${esc(file.name)} · ${preview.changes.length} 项数值变化。以下为应用后的预计结果，当前文件尚未修改。</p><div class="preview-metrics"><div><strong>${preview.affected.length}</strong><span>受影响论断</span></div><div><strong>${preview.summary.consistent}</strong><span>仍然成立</span></div><div><strong>${preview.summary.inconsistent}</strong><span>计算不一致</span></div><div><strong>${preview.summary.unverifiable}</strong><span>无法判断</span></div></div><h3>数值变更</h3><div class="table-scroll"><table class="data-table"><thead><tr><th>来源事实</th><th>当前值</th><th>新值</th></tr></thead><tbody>${preview.changes.map(c=>{const f=facts.get(c.id);return `<tr><td>${esc(factName(f))}<small class="cell-meta">${esc(c.id)}</small></td><td>${esc(c.before??'缺失')} ${esc(f.unit)}</td><td class="changed-value">${esc(c.after??'缺失')} ${esc(f.unit)}</td></tr>`;}).join('')}</tbody></table></div><h3 class="section-heading">受影响的结论</h3><p class="hint">数值变化后，仍成立的结论会保留原文。候选来源需人工确认后才能修复。</p>${preview.affected.map(item=>{const c=workspace.claims.find(c=>c.id===item.claim_id);return `<div class="impact-row"><div><span class="file-tag">${esc(fileOf(c).name)} · ${esc(c.label)}</span>${statusBadge(c,item.after)}</div><p>${esc(c.original)}</p><small>${esc(statusNames[item.before.status])} → ${esc(statusNames[item.after.status])} · ${esc(item.after.reason)}</small>${item.after.status==='inconsistent'?`<div class="diff-new">预计修复为：${esc(item.after.expected)}</div>`:''}</div>`;}).join('')||'<p class="hint">这些来源事实目前没有关联到已识别的论断。</p>'}<p class="hint">确认后更新源表并重新验证，Word / PPT 将在你预览并确认修复后更新。${drafts().size?'右侧尚未应用的输入将被此次源表更新替换。':''}</p><div class="modal-actions"><button class="button secondary" id="chooseSourceAgain">重新选文件</button><button class="button primary" id="applySource">确认导入并验证</button></div>`);
  $('chooseSourceAgain').onclick=importSourceModal;
  $('applySource').onclick=async()=>{
    const form=new FormData();form.set('file',file);form.set('revision',revision);
    const result=await busy('保存源表新版本并重新验证',()=>api(`/api/projects/${projectId}/source`,{method:'POST',body:form}));
    if(result){factDrafts.delete(projectId);workspace=result;filter='all';closeModal();switchView('overview');await refreshProjects();afterDataUpdate();}
  };
}
async function demo(){
  const result=await busy('正在创建真实 Office 演示文件',()=>api('/api/projects/demo',{method:'POST'}));
  if(result){closeModal();workspace=result;filter='all';switchView('overview');localStorage.setItem('zhilian-project',result.id);await refreshProjects();toast('演示已就绪：确认来源 → 载入演示变更 → 更新数据');}
}
function claimModal(id){
  const c=workspace.claims.find(c=>c.id===id),r=resultOf(c),suggestion=workspace.suggestions?.find(s=>s.claim_id===id);
  modal('来源与计算依据',`<span class="badge ${classNames[r.status]}">${statusNames[r.status]}</span> <span class="badge neutral">${esc(kindNames[c.kind])}</span><div class="evidence-block">${esc(c.original)}</div><p class="hint">${esc(fileOf(c).name)} · ${esc(c.label)} · ${esc(c.extraction)}</p><h3 style="margin-top:18px">验证过程</h3><p class="hint">${esc(r.reason)}</p>${r.expected&&r.status==='inconsistent'?`<div class="diff-new">${esc(r.expected)}</div>`:''}<h3 style="margin-top:20px">关联来源</h3><p class="hint">增长率依次选择上期、本期；排名需确认比较集合完整。单纯存在引用并不证明统计口径一致。</p>${suggestion?`<div class="evidence-block"><small>模型建议，尚未生效</small><p>${esc(suggestion.reason)}</p><button class="link-button" id="useSuggestion">选择建议的来源</button></div>`:''}<div class="check-list">${workspace.facts.map(f=>`<label><input type="checkbox" name="ref" value="${esc(f.id)}" ${c.refs.includes(f.id)?'checked':''}><div>${esc(factName(f))} · ${esc(f.value??'缺失')}${esc(f.unit)}<small>${esc(f.id)} · ${esc(f.scope)} · ${esc(f.sheet+'!'+f.cell)}</small></div></label>`).join('')}</div><p class="hint">${c.confirmed?'此关联已经确认，可以重新选择。':'当前是候选关联，请核对后确认。'}</p><div class="modal-actions"><button class="button primary" id="confirmLink">确认所选来源</button></div>`);
  if(suggestion)$('useSuggestion').onclick=()=>document.querySelectorAll('input[name=ref]').forEach(x=>x.checked=suggestion.refs.includes(x.value));
  $('confirmLink').onclick=async()=>{const selected=[...document.querySelectorAll('input[name=ref]:checked')].map(x=>x.value);let refs=selected;if(c.kind==='growth')refs.sort((a,b)=>{const period=id=>workspace.facts.find(f=>f.id===id)?.period;return (period(a)==='上期'?0:1)-(period(b)==='上期'?0:1);});if(c.kind==='threshold'&&!('limit' in c.spec))refs.sort((a,b)=>(workspace.facts.find(f=>f.id===a)?.metric==='支出'?0:1)-(workspace.facts.find(f=>f.id===b)?.metric==='支出'?0:1));const result=await post('links',{links:[{claim_id:id,refs}]},'检查关联口径');if(result){closeModal();toast('来源关联已确认');}};
}
function confirmAllModal(){
  const cs=workspace.claims.filter(c=>!c.confirmed&&c.refs.length&&resultOf(c).status!=='unverifiable');
  modal('审阅候选来源',`<p class="modal-intro">以下 ${cs.length} 项已找到可计算的候选来源。请核对主体、期间、单位和统计口径；确认后才允许修复。</p><div class="check-list">${cs.map(c=>`<label><input type="checkbox" name="confirmClaim" value="${c.id}" checked><div>${esc(c.original)}<small>${esc(c.refs.map(id=>{const f=workspace.facts.find(f=>f.id===id);return `${factName(f)} ${f.value}${f.unit} [${f.scope}]`;}).join(' / '))}</small></div></label>`).join('')}</div><div class="modal-actions"><button class="button primary" id="applyConfirmAll">确认选中的关联</button></div>`);
  $('applyConfirmAll').onclick=async()=>{const ids=[...document.querySelectorAll('input[name=confirmClaim]:checked')].map(x=>x.value);const links=cs.filter(c=>ids.includes(c.id)).map(c=>({claim_id:c.id,refs:c.refs}));const result=await post('links',{links},'保存确认结果');if(result){closeModal();if(result.summary.repairable)repairModal();else toast('关联已确认，可以更新数据');}};
}
function repairModal(){
  const cs=workspace.claims.filter(c=>c.confirmed&&resultOf(c).status==='inconsistent');
  modal('预览并确认修复',`<p class="modal-intro">仅修改选中的受支持位置。写入新版本后，系统重新读取成果并检查这些论断，原版本保留。</p>${cs.map(c=>`<div class="diff-row"><label><input type="checkbox" name="repairClaim" value="${c.id}" checked> ${esc(fileOf(c).name)} · ${esc(c.label)}</label><div class="diff-old">− ${esc(c.original)}</div><div class="diff-new">＋ ${esc(resultOf(c).expected)}</div></div>`).join('')}<div class="modal-actions"><button class="button primary" id="applyRepairs">确认修复并复核</button></div>`);
  $('applyRepairs').onclick=async()=>{const ids=[...document.querySelectorAll('input[name=repairClaim]:checked')].map(x=>x.value);const result=await post('repair',{claim_ids:ids},'正在修复文件并重新验证');if(result){closeModal();filter='all';render();deliveryModal();}};
}
function helpModal(){
  modal('使用知链',`<div class="help-section"><h3>1 导入或体验演示</h3><p>准备一份符合模板的 Excel，以及结构清晰的 Word 或 PPT。演示项目会创建包含真实文本、不同文字格式和原生图表的文件。</p></div><div class="help-section"><h3>2 审阅来源关联</h3><p>规则识别会给出候选来源。查看依据，确认主体、指标、期间、单位和口径；支持手动纠正关联。</p></div><div class="help-section"><h3>3 修改并重新验证</h3><p>在右侧修改数值。系统检查原有论断是仍成立、已失效，还是无法判断。依赖变化不会直接触发改写。</p></div><div class="help-section"><h3>4 修复与导出</h3><p>预览修改前后内容，确认后写入新版本。导出包含Excel、Word/PPT、核验记录JSON和报告。可撤销上一次文件变更。</p></div><div class="help-section"><h3>识别范围</h3><p>支持明确表达的数值引用、较上期/环比增长率、最高排名和阈值。语义歧义、因果解释、主观结论、未识别文本不会被当作验证通过。完整范围见项目 README。</p></div>`);
}
function settingsModal(){
  modal('模型与运行方式',`<p class="modal-intro">当前模式：${health?.model.enabled?esc(health.model.provider)+' · '+esc(health.model.model):'规则识别与人工确认，无模型调用'}</p><div class="help-section"><h3>API 是可选项</h3><p>在服务器项目根目录的 <code>.env</code> 中配置模型地址、模型ID与密钥，重启服务生效。不要在聊天或源码里填写密钥。参照 <code>.env.example</code> 接入百炼兼容API或本地Ollama。</p></div><div class="help-section"><h3>模型做什么</h3><p>当前模型接口只为已识别的待确认论断提出来源关联建议，不会自动确认、改文件或执行代码。计算、口径校验与文件复核始终由程序完成。任意自然语言论断抽取尚未实现。</p></div><div class="help-section"><h3>本地与公网</h3><p>本机使用不需要服务器。公网部署需要设置访问密码与HTTPS，并配置模型额度。当前系统是共享工作空间，尚未实现团队成员分级权限。</p></div><div class="help-section"><h3>发送给模型的内容</h3><p>只有点击“模型关联建议”后才发送待确认论断及事实元数据。原文件不会直接上传到模型服务。返回建议必须由你核对。</p></div>`);
}

document.addEventListener('click',e=>{
  const nav=e.target.closest('[data-view]');if(nav)switchView(nav.dataset.view);
  const project=e.target.closest('[data-project]');if(project)loadProject(project.dataset.project);
  const claim=e.target.closest('[data-claim]');if(claim)claimModal(claim.dataset.claim);
  const graph=e.target.closest('[data-graph-fact]');if(graph){graphFact=graph.dataset.graphFact;renderGraph();}
  if(e.target.closest('#clearGraph')){graphFact=null;renderGraph();}
});
$('filters').onclick=e=>{const b=e.target.closest('[data-filter]');if(b){filter=b.dataset.filter;render();}};
$('closeModal').onclick=closeModal;
$('modal').addEventListener('click',e=>{if(e.target===$('modal'))closeModal();});
$('newProject').onclick=uploadModal;$('welcomeUpload').onclick=uploadModal;$('loadDemo').onclick=demo;
$('helpButton').onclick=helpModal;$('scopeButton').onclick=helpModal;$('settingsButton').onclick=settingsModal;
$('confirmAll').onclick=confirmAllModal;$('reviewRepairs').onclick=repairModal;
$('demoChange').insertAdjacentHTML('afterend','<button class="button secondary full" id="importSource">导入更新后的 Excel</button>');
$('importSource').onclick=importSourceModal;
  $('saveFacts').onclick=async()=>{
  const values={};for(const input of document.querySelectorAll('[data-fact]')){const old=workspace.facts.find(f=>f.id===input.dataset.fact);if(input.value.trim()===''){toast('数值不能为空',true);return;}const value=Number(input.value);if(!Number.isFinite(value)){toast('请输入有效数字',true);return;}if(value!==old.value)values[old.id]=value;}
  if(!Object.keys(values).length){toast('数值没有变化');return;}
  const result=await post('facts',{values},'写入数据新版本并重新验证');
  if(result){factDrafts.delete(result.id);render();afterDataUpdate();}
};
$('demoChange').onclick=()=>{const values={sales_current:90,product_a:60,spending:110};document.querySelectorAll('[data-fact]').forEach(x=>{if(x.dataset.fact in values){x.value=values[x.dataset.fact];trackDraft(x);}});toast('已填写示例变更，点击“更新数据并验证”应用');};
$('exportButton').onclick=deliveryModal;
$('undoButton').onclick=()=>{modal('撤销上一次文件变更',`<p class="modal-intro">恢复上一次数据更新或修复之前的文件。操作记录会保留。</p><div class="modal-actions"><button class="button primary" id="applyUndo">确认恢复</button></div>`);$('applyUndo').onclick=async()=>{if(await post('undo',{},'恢复文件版本')){closeModal();toast('已恢复上一次文件变更之前的版本');}};};
$('suggestButton').onclick=()=>{modal('请求模型关联建议',`<p class="modal-intro">将最多40条未确认论断及事实元数据发送至你配置的 ${esc(health.model.provider)} 服务。这可能产生API费用。模型只提出建议，结果仍需人工确认。</p><div class="modal-actions"><button class="button primary" id="callModel">发送并获取建议</button></div>`);$('callModel').onclick=async()=>{if(await post('suggest',{},'等待模型建议，最长约60秒')){closeModal();toast('建议已保存，在“查看依据”中审阅');}};};
async function init(){
  try{
    health=await api('/api/health');$('connection').innerHTML='工作空间已连接<small>本地持久化存储</small>';
    $('modelBadge').textContent=health.model.enabled?'模型已配置':'规则模式 · 无需 API';
    const projects=await refreshProjects();const previous=localStorage.getItem('zhilian-project');
    if(projects.length)await loadProject(projects.find(p=>p.id===previous)?.id||projects[0].id);else render();
  }catch(e){$('welcome').classList.remove('hidden');$('connection').textContent='连接失败';toast(e.message,true);}
}
init();
