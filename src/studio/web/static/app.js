'use strict';
const $ = id => document.getElementById(id);
const S = { csrf:'', tab:'A', data:{assets:[],jobs:[],analyses:[],recipes:[],candidates:[],evaluations:[]}, copy:{}, selected:null, resultStamp:null, submitKey:null, pendingPayload:null, approval:null };
const UI = {emptyJobs:'暂无任务。先选择素材并创建任务。', saved:'已保存到本地。', failed:'操作失败', upload:'素材已保存；请在商品或参考下拉框中选择。', demo:'测试素材已载入。商品为本地绘制的透明 PNG，参考为固定测试场景。', queued:'任务已入队，由独立 Worker 执行。', noProduct:'请选择商品图片。', noCompare:'请选择 C1 和 C2 候选。', mismatch:'这两个候选的商品或参考不同，不能作为同素材对照。', fixture:'测试夹具 / 非模型生成', none:'未评价', cost:'费用 unknown · Fixture 无收费调用'};
function node(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;}
function message(text,error=false){$('message').textContent=text;$('message').className=error?'error':'';}
function bind(id,event,fn){$(id).addEventListener(event,async e=>{try{await fn(e);}catch(err){message(err.message,true);}});}
async function api(path,options={}){const headers={...(options.headers||{})};if(options.method&&options.method!=='GET'){headers['X-CSRF-Token']=S.csrf;if(!(options.body instanceof FormData)){headers['Content-Type']='application/json';}}const response=await fetch(path,{...options,headers});if(!response.ok){let error;try{error=await response.json();}catch{error={detail:response.statusText};}throw new Error(typeof error.detail==='string'?error.detail:JSON.stringify(error.detail));}return response.json();}
function selection(id){const values=Array.from($(id).selectedOptions).map(o=>o.value).filter(Boolean);if(id!=='products')return values;S.productOrder=[...(S.productOrder||[]).filter(v=>values.includes(v)),...values.filter(v=>!(S.productOrder||[]).includes(v))];return S.productOrder;}
function options(id,items,empty,label){const target=$(id), previous=selection(id);target.replaceChildren();if(empty!==null){target.append(new Option(empty,''));}items.forEach(item=>{const option=new Option(label(item),item.id);option.selected=previous.includes(item.id);target.append(option);});}
function isGeneratedAsset(asset){return S.data.candidates.some(c=>c.asset_id===asset.id||c.data?.raw_asset_id===asset.id)||asset.source.startsWith('真实模型')||asset.source.startsWith('本地抠图');}
function assetLabel(asset){return `${asset.fixture?'[测试] ':''}${asset.source.slice(0,22)} · ${asset.id.slice(0,6)}`;}
function preview(container,id,caption){const figure=node('figure');const img=node('img');img.src=`/api/assets/${id}`;img.alt=caption;figure.append(img,node('figcaption',caption));container.append(figure);}
function previews(){renderScenePreview();const target=$('input-previews');target.replaceChildren();selection('products').forEach(id=>preview(target,id,'商品 / '+id.slice(0,6)));const extra=S.tab==='C'?$('reference').value:S.tab==='A'?$('back').value:$('mask').value;if(extra)preview(target,extra,S.tab==='C'?'参考图':S.tab==='A'?'背面图':'蒙版');}
function renderJobs(){const target=$('jobs');target.replaceChildren();if(!S.data.jobs.length)target.append(node('p',UI.emptyJobs,'hint'));S.data.jobs.forEach(job=>{const button=node('button',undefined,'job'+(S.selected===job.id?' selected':''));button.type='button';button.append(node('b',(job.payload.fixture&&job.payload.request.mode!=='CUTOUT'?'[演示] ':'')+S.copy.modes[job.payload.request.mode]+((job.payload.request.batch_product_ids||[]).length>1?(job.payload.request.batch_index?' · 批量 '+(job.payload.request.batch_index+1)+'/'+job.payload.request.batch_product_ids.length:' · 首张 / '+job.payload.request.batch_product_ids.length+' 张'):'')),node('span',S.copy.states[job.state]||job.state,'badge'),node('small',`\n${job.id.slice(0,8)} · ${new Date(job.created_at*1000).toLocaleTimeString('zh-CN')}`));button.addEventListener('click',()=>showJob(job.id).catch(err=>message(err.message,true)));target.append(button);});}
function labeledInput(label,value,type='text'){const wrap=node('div');const input=node('input');input.id='field-'+crypto.randomUUID();input.type=type;input.value=value??'';const lab=node('label',label);lab.htmlFor=input.id;wrap.append(lab,input);return{wrap,input};}
function table(headers){const wrap=node('div',undefined,'table-wrap');const t=node('table');const row=node('tr');headers.forEach(h=>row.append(node('th',h)));const head=node('thead');head.append(row);const body=node('tbody');t.append(head,body);wrap.append(t);return{wrap,body};}
function cellInput(row,value,label){const td=node('td');const input=node('input');input.value=value??'';input.setAttribute('aria-label',label);td.append(input);row.append(td);return input;}
function editableRows(container,title,rows,columns){container.append(node('h3',title));const t=table(columns);const controls=[];function add(data={}){const tr=node('tr'),fields={};columns.forEach(key=>fields[key]=cellInput(tr,data[key],title+' '+key));const remove=node('button','删除','secondary');remove.type='button';remove.addEventListener('click',()=>{tr.remove();controls.splice(controls.indexOf(fields),1);});const td=node('td');td.append(remove);tr.append(td);t.body.append(tr);controls.push(fields);}rows.forEach(add);const button=node('button','添加一行','secondary');button.type='button';button.addEventListener('click',()=>add());container.append(t.wrap,button);return()=>controls.map(fields=>Object.fromEntries(columns.map(key=>[key,fields[key].value||null])));}
function copyControl(label, read){const button=node('button',label,'secondary');button.type='button';button.addEventListener('click',async()=>{try{const value=read();if(!value.trim())throw new Error('没有可复制的内容');await navigator.clipboard.writeText(value);message('已复制到剪贴板。');}catch(err){message('复制失败，请选中文字手动复制。',true);}});return button;}
function renderAnalysis(record,container){
  if(record.data.notes)container.append(node('h4','图片识别摘要'),node('p',record.data.notes,'description'));
  const tabs=node('div',undefined,'result-actions'), full=node('div'), params=node('div');
  const fullButton=node('button','完整提示词','primary'), partsButton=node('button','动态参数','secondary');
  for(const b of [fullButton,partsButton])b.type='button';
  function select(parts){full.hidden=parts;params.hidden=!parts;fullButton.setAttribute('aria-pressed',String(!parts));partsButton.setAttribute('aria-pressed',String(parts));}
  fullButton.addEventListener('click',()=>select(false));partsButton.addEventListener('click',()=>select(true));tabs.append(fullButton,partsButton);container.append(tabs,full,params);select(false);
  const prompt=node('textarea');prompt.rows=10;prompt.maxLength=8000;prompt.setAttribute('aria-label','完整逆推提示词');prompt.value=record.data.generation_prompt||'';
  if(!prompt.value)full.append(node('p',record.fixture?'Fixture 不生成真实逆推提示词。':'这是旧版分析，未生成完整提示词；可切换动态参数查看原记录，重新分析即可获得新版结果。','warning'));
  full.append(prompt);
  const use=node('button','带入 AI 换背景','primary');use.type='button';use.addEventListener('click',()=>{if(!prompt.value.trim()){message('请先生成或填写完整提示词。',true);return;}setTab('B');$('products').value=record.input_ids[0];S.productOrder=[record.input_ids[0]];renderLibrary();$('instructions').value=prompt.value;if($('subject-image').value)$('change-subject').checked=true;fieldVisibility();S.approval=null;$('external-preview').hidden=true;previews();$('instructions').focus();message('已带入原商品和提示词；请将背景、道具改成你的目标效果，再预览提交。');});
  full.append(copyControl('复制完整 Prompt',()=>prompt.value),use,node('p','完整提示词与参数均可独立编辑；修改参数不会自动改写全文，保存会保留两个版本的内容。','hint'));
  params.append(node('p','参数名称来自图片分析。可单独复制颜色、结构、光影等内容；未知项不作为已确认事实。','description'));
  const t=table(['动态参数','内容','证据状态','依据与说明','复制']);const fields={};
  Object.entries(record.data.fields).forEach(([name,evidence])=>{const tr=node('tr');tr.append(node('td',name));const value=cellInput(tr,evidence.value,name);const status=node('select');status.setAttribute('aria-label',name+'证据状态');Object.entries(S.copy.evidence).forEach(([key,text])=>status.append(new Option(text,key)));status.value=evidence.status;const td=node('td');td.append(status);tr.append(td,node('td',evidence.note||'—'));const action=node('td');action.append(copyControl('复制 '+name,()=>value.value));tr.append(action);fields[name]={value,status};t.body.append(tr);});params.append(t.wrap);
  const extra=node('details');extra.append(node('summary','人工补充尺寸与工艺'));params.append(extra);
  const dimensions=editableRows(extra,'尺寸表（不从照片测量）',record.data.dimensions,['部位','数值','单位','来源']);const workmanship=editableRows(extra,'工艺表',record.data.workmanship,['工艺','说明','来源']);
  const save=node('button','保存提示词与参数新版本','primary');save.type='button';save.addEventListener('click',async()=>{try{const data=structuredClone(record.data);data.generation_prompt=prompt.value;for(const[name,c]of Object.entries(fields)){data.fields[name].value=c.value.value||null;data.fields[name].status=c.status.value;}data.dimensions=dimensions();data.workmanship=workmanship();const saved=await api('/api/analysis/'+record.id,{method:'PUT',body:JSON.stringify({data,version:record.version})});await refresh();$('analysis').value=saved.id;S.resultStamp=null;await showJob(S.selected);message(UI.saved);}catch(err){message(err.message,true);}});container.append(save);
}
function renderRecipe(record,container){
 container.append(node('p','视觉配方已准备。可以直接添加自己的商品生成；想调整场景时再展开修改。','description'));
 const editor=node('details');editor.append(node('summary','调整视觉配方（选填）'));const grid=node('div',undefined,'two');const fields={};
 for(const[key,el]of Object.entries(record.data.elements)){const label=S.recipeFields[key]||key;const field=labeledInput(label,el.action==='modify'?el.override:el.value);const use=node('input');use.type='checkbox';use.checked=el.action!=='ignore';const check=node('label','使用此元素','check');check.prepend(use);field.wrap.append(check);grid.append(field.wrap);fields[key]={input:field.input,use,original:el};}
 editor.append(grid);const preserve=labeledInput('必须保留的商品特征',record.data.preserve),exclude=labeledInput('不带入的参考元素',record.data.exclude);editor.append(preserve.wrap,exclude.wrap);container.append(editor);
 async function saveRecipe(){const data={elements:{},preserve:preserve.input.value,exclude:exclude.input.value};for(const[key,c]of Object.entries(fields)){const value=c.input.value||null;data.elements[key]={value:c.original.value,action:!c.use.checked?'ignore':value!==c.original.value?'modify':'inherit',override:value!==c.original.value?value:null};}return api('/api/recipe/'+record.id,{method:'PUT',body:JSON.stringify({data,version:record.version})});}
 const next=node('button','保存配方 → 添加自己的商品生成','primary');next.type='button';next.addEventListener('click',async()=>{next.disabled=true;try{const saved=await saveRecipe();await refresh();setTab('C');$('reference').value=record.reference_id;$('recipe').value=saved.id;$('mode').value='C2';$('upload-target').value='subject-image';$('recipe-status').textContent='已保存配方。添加自己的商品，再生成。';updateMode();$('subject-image').focus();S.resultStamp=null;message('配方已保存，下一步添加自己的商品图。');}catch(e){message(e.message,true);}finally{next.disabled=false;}});container.append(next);
}
function renderEvaluation(candidate,container){const section=node('details');section.append(node('summary','人工评价与商品关键特征检查'));const form=node('form');const latest=S.data.evaluations.find(e=>e.candidate_id===candidate.id)?.data||{};const scores={};[['fidelity','商品保真（1–5）'],['reference_fit','参考符合度（1–5）'],['usability','视觉可用性（1–5）'],['rework_minutes','人工返工分钟数']].forEach(([key,label])=>{const field=labeledInput(label,latest[key],'number');field.input.min=key==='rework_minutes'?'0':'1';field.input.max=key==='rework_minutes'?'10000':'5';form.append(field.wrap);scores[key]=field.input;});const checks={};S.copy.checks.forEach(name=>{const label=node('label',name),select=node('select');select.id='check-'+crypto.randomUUID();label.htmlFor=select.id;[['unknown','无法判断 / 未检查'],['pass','通过'],['fail','失败']].forEach(([v,l])=>select.append(new Option(l,v)));select.value=latest.checks?.[name]||'unknown';checks[name]=select;form.append(label,select);});const notes=labeledInput('失真、失败原因或返工说明',latest.notes);form.append(notes.wrap);const button=node('button','保存人工评价','primary');button.type='submit';form.append(button);form.addEventListener('submit',async e=>{e.preventDefault();try{const data={notes:notes.input.value,checks:{}};for(const[k,input]of Object.entries(scores))data[k]=input.value===''?null:Number(input.value);for(const[k,input]of Object.entries(checks))data.checks[k]=input.value;await api(`/api/candidates/${candidate.id}/evaluations`,{method:'POST',body:JSON.stringify(data)});await refresh();message(UI.saved);}catch(err){message(err.message,true);}});section.append(form);container.append(section);}
async function showJob(id,scroll=false){const epoch=S.draftEpoch;if(document.body.dataset.tool==='home')document.body.dataset.tool='history';S.selected=id;renderJobs();const detail=await api('/api/jobs/'+id);if(epoch!==S.draftEpoch)return;if(['home','history'].includes(document.body.dataset.tool)&&isCanvasResult(detail)){fillRequest({...detail.job.payload.request,mode:detail.job.payload.request.mode==='CUTOUT'?'A_white':detail.job.payload.request.mode,execution:detail.job.payload.request.mode==='CUTOUT'?'real':detail.job.payload.request.execution});S.resultStamp=null;}const stamp=[id,detail.job.state,detail.analysis?.id,detail.recipe?.id].join(':');if(S.resultStamp===stamp){if(!isCanvasResult(detail))$('result-details').showModal();return;}S.resultStamp=stamp;S.visualResult=detail;renderVisualFlow();syncGlassNav();$('empty-result').hidden=true;const target=$('result');target.replaceChildren();target.append(node('span',S.copy.states[detail.job.state],'badge'),node('h3',S.copy.modes[detail.job.payload.request.mode]+' · '+(detail.job.payload.request.mode==='CUTOUT'?'本地抠图输出':detail.job.payload.fixture?UI.fixture:(detail.job.state==='succeeded'?'真实模型输出 · 尚需人工评价':'真实模型任务 · 尚未取得有效结果'))));if(detail.job.error){const receipt=detail.job.payload.receipt||{};const legacy429=receipt.http_status===429&&!receipt.provider_error_code;target.append(node('p',legacy429?'供应商 HTTP 429：限流、额度限制或服务繁忙。旧记录未保存具体错误码，无法确定子原因；此前「涉及参数 model」的提示不准确。未自动重试。':detail.job.error,'warning'));if(receipt.http_status===429){target.append(node('p','请在火山方舟控制台核对 Seedream 的模型额度、推理限额（安心体验模式）和调用频率。确认原因后再提交，重复点击不能解除额度限制。','hint'));if(receipt.provider_request_id)target.append(copyControl('复制供应商请求 ID',()=>receipt.provider_request_id));}}if(['failed','outcome_unknown'].includes(detail.job.state)&&detail.job.payload.request.mode==='B2'){const restore=node('button','重新载入本次设置','secondary');restore.type='button';restore.addEventListener('click',()=>{fillRequest(detail.job.payload.request);message('设置已恢复，请重新预览后提交；不会自动重试旧任务。');});target.append(restore);}if(['queued','running'].includes(detail.job.state))target.append(node('p','任务等待或执行中。若长时间排队，请确认独立 Worker 已启动。','description'));if(detail.analysis){if(detail.job.payload.request.mode==='CHECK')renderQualityCheck(detail,target);else{renderAnalysis(detail.analysis,target);$('analysis').value=detail.analysis.id;}}if(detail.recipe){renderRecipe(detail.recipe,target);$('recipe').value=detail.recipe.id;}
if(detail.candidate){S.visualResult=detail;renderVisualFlow();const c=detail.candidate;if(c.data.mode==='A_views')target.append(node('p','用途：说明书外观插图初稿 / 部件说明底图 / 设计沟通草图。请对照实物核对接口、按键、开孔与各视图的一致性，再添加准确的部件名称及说明；图中推测结构不作为操作或装配依据。','description'));target.append(node('p',c.data.warning,'warning'));if(c.data.mode==='A_back')target.append(node('p',c.data.label,'description'));const images=node('div',undefined,'result-images');detail.job.payload.request.product_ids.forEach(a=>preview(images,a,'输入商品 · '+a.slice(0,8)));if(detail.job.payload.request.reference_id)preview(images,detail.job.payload.request.reference_id,'原始参考图');(detail.job.payload.request.product_view_ids||[]).forEach(a=>preview(images,a,'同一商品 · 补充角度'));if(detail.job.payload.request.background_id)preview(images,detail.job.payload.request.background_id,'目标背景 / 场景参考');if(detail.job.payload.request.subject_id)preview(images,detail.job.payload.request.subject_id,'指定替换商品');if(detail.job.payload.request.back_id)preview(images,detail.job.payload.request.back_id,'输入背面图');preview(images,c.asset_id,'结果 · '+(c.data.mode==='CUTOUT'?'本地抠图':c.fixture?UI.fixture:'真实模型输出'));const comparison=node('details');comparison.append(node('summary','查看输入图片与生成结果对照'),images);target.append(comparison);const actions=node('div',undefined,'result-actions');const download=node('a','下载 PNG');download.href=`/api/assets/${c.asset_id}?download=true`;const favorite=node('button',c.favorite?'取消收藏':'收藏到本地','secondary');favorite.type='button';favorite.addEventListener('click',async()=>{try{const result=await api(`/api/candidates/${c.id}/favorite`,{method:'PUT',body:JSON.stringify({favorite:!c.favorite})});c.favorite=result.favorite;favorite.textContent=c.favorite?'取消收藏':'收藏到本地';await refresh();}catch(err){message(err.message,true);}});actions.append(download,favorite,node('span',c.data.mode==='CUTOUT'?'本地抠图 · 无外发费用':c.fixture?UI.cost:'费用 unknown · 以供应商账单为准','hint'));target.append(actions);if(c.data.transformations.length){const list=node('ul');c.data.transformations.forEach(item=>list.append(node('li',item)));const block=node('details');block.append(node('summary','处理记录'),list);target.append(block);}renderEvaluation(c,target);resultNextSteps(detail,target);}
if(detail.job.state==='succeeded'){const link=node('a',`导出 ${detail.job.payload.request.mode==='CUTOUT'?'本地抠图':detail.job.payload.fixture?'Fixture':'真实模型'} 结果与追溯记录（ZIP）`);link.href=`/api/jobs/${id}/export`;const actions=node('div',undefined,'result-actions');actions.append(link);target.append(actions);}const trace=node('details');trace.append(node('summary','查看输入快照、模型与请求记录'),node('pre',JSON.stringify(detail,null,2)));target.append(trace);if(!isCanvasResult(detail))$('result-details').showModal();else if(scroll)$('visual-flow-cards').scrollIntoView({behavior:'smooth',block:'start'});}
function selectedAssets(){return selection('products');}
function renderLibrary(){
 const target=$('asset-library');target.replaceChildren();const selected=selectedAssets();$('selection-count').textContent=`${selected.length} / ${$('mode').value==='A_white'?1:$('mode').value==='A_views'?6:10}`;
 const all=S.data.assets.filter(a=>selected.includes(a.id)||(a.id!==$('background-image').value||selected.includes(a.id))&&($('show-tests').checked||!(a.source.startsWith('本地')&&a.source.includes('测试')))&&!a.source.startsWith('测试夹具 / 非模型生成')&&!a.source.startsWith('真实模型')&&!a.source.startsWith('本地抠图'));
 for(const a of all){const card=node('div',undefined,'asset-card'+(selected.includes(a.id)?' is-selected':''));const label=node('label');const check=node('input');check.type='checkbox';check.checked=selected.includes(a.id);check.setAttribute('aria-label','选择 '+a.source);check.addEventListener('change',()=>{try{if(check.checked)applySlot(defaultInputRole(),[a.id]);else{Array.from($('products').options).find(o=>o.value===a.id).selected=false;if(a.id===S.drawingMain)S.drawingMain=null;invalidate();renderLibrary();}}catch(e){check.checked=false;message(e.message,true);}});const img=node('img');img.src='/api/assets/'+a.id;img.alt=a.source;label.append(check,img,node('span',(selected.includes(a.id)?(selected.indexOf(a.id)+1)+'. ':'')+a.source));const del=node('button','删除','text-button');del.type='button';del.addEventListener('click',async()=>{try{await api('/api/assets/'+a.id,{method:'DELETE'});invalidate();await refresh();message('已从素材库删除；历史任务的原图保留。');}catch(e){message(e.message,true);}});const isMain=($('mode').value==='A_views'?S.drawingMain:selected[0])===a.id;const main=node('button',isMain?'主要参考':'设为主图','asset-main');main.type='button';main.disabled=isMain;main.addEventListener('click',()=>{try{if($('mode').value==='A_views')applySlot('main',[a.id]);else{applySlot(defaultInputRole(),[a.id]);S.productOrder=[a.id,...selectedAssets().filter(id=>id!==a.id)];invalidate();renderLibrary();}}catch(e){message(e.message,true);}});card.append(label,main,del);target.append(card);}
 if(!all.length)target.append(node('p','还没有图片，拖入或粘贴即可添加。','hint'));renderWorkingAssets();
}
function invalidate(){S.visualResult=null;S.approval=null;renderVisualFlow();S.submitKey=null;$('external-preview').hidden=true;}
async function refresh(){S.data=await api('/api/state');const inputs=S.data.assets.filter(a=>($('show-tests').checked||!a.fixture)&&!a.source.startsWith('测试夹具 / 非模型生成')&&($('show-tests').checked||!(a.source.startsWith('本地')&&a.source.includes('测试'))));options('products',inputs,null,assetLabel);for(const id of ['back','reference','mask','subject-image','background-image'])options(id,id==='background-image'?inputs.filter(a=>!isGeneratedAsset(a)||a.id===$('background-image').value):inputs,'未选择',assetLabel);options('analysis',S.data.analyses.filter(a=>a.data.fields),'不关联分析',a=>`商品资料 v${a.version}`);options('recipe',S.data.recipes,'自动使用本参考最新配方',r=>`配方 v${r.version}`);for(const[id,mode]of[['compare-one','C1'],['compare-two','C2']])options(id,S.data.candidates.filter(c=>c.data.mode===mode),`选择 ${mode}`,c=>c.id.slice(0,8));renderJobs();renderLibrary();previews();renderGallery();}
function setTab(tab){S.tab=tab;if(tab==='B')S.tool='promo';document.body.dataset.tab=tab;for(const b of document.querySelectorAll('.tabs button[data-tab]')){b.classList.toggle('active',b.dataset.tab===tab);b.setAttribute('aria-pressed',String(b.dataset.tab===tab));}for(const key of ['A','B','C'])document.querySelectorAll('.for-'+key).forEach(e=>e.hidden=key!==tab);$('flow-title').textContent={A:'2. 选择操作路线',B:'配置场景重构与创意要求',C:'2. 参考图 → 配方 → 自有商品'}[tab];$('mode').replaceChildren();const modes={A:['A','A_white','A_views'],B:['B2'],C:['C_analyze','C2']}[tab];modes.forEach(m=>$('mode').append(new Option(S.copy.modes[m],m)));$('upload-target').value=tab==='C'?'reference':'products';updateMode();}
function fieldVisibility(){const m=$('mode').value;$('subject-control').hidden=!(m==='C2'||(m==='B2'&&$('change-subject').checked));$('background-control').hidden=['C_analyze','A_white','A_views'].includes(m)||(m==='B2'&&!$('change-background').checked);$('background-help').hidden=!m.startsWith('A');}
function updateMode(){fieldVisibility();const m=$('mode').value;const real=$('execution').value==='real';$('submit-job').textContent=real?(m==='B2'?'预览首张生成':'预览并开始'):'运行本地演示';$('recipient').textContent=real?(['A','C_analyze'].includes(m)?'本次由 Kimi 分析图片，输出文字；上传不会自动调用模型。':'本次由 Seedream 根据图片与要求生成，结果需人工核对。'):'本地演示只验证流程，不代表真实模型效果。';$('operation-step').textContent=m.startsWith('A')?'STEP 2 · 商品处理方式':'STEP 2 · 场景与操作设置';$('generation-intent').textContent={A:'逆推完整提示词与动态参数',A_white:'生成白底实物配图',A_views:'生成说明书插图初稿',B2:'先看一张，再决定下一步',C_analyze:'先解析参考图，得到视觉配方',C2:'用已有配方重新呈现自己的商品'}[m]||'预览本次任务';$('mode-note').textContent=m==='A'?'上传的图片将一起逆推完整 Prompt；也可逐项复制动态参数。':m==='A_white'?'上传一张商品实拍，保持原图视角与结构，生成干净的白底实物图，用于商品展示、说明书实物配图；出图后可抠为透明 PNG。':m==='A_views'?'把同一商品的实拍转成白底三视图线稿（正视、侧视、俯视），可作说明书外观插图、部件说明底图或设计沟通草图。建议补充多角度照片；核对结构后再加部件名称与说明。没有精确尺寸，不用于生产加工。':m==='B2'?'以自有商品为主体，按参考场景生成新图；要求保留外观与 Logo，出图后需核对细节。':m==='C_analyze'?'只需一张参考图。解析后可调整配方，添加自己的商品直接生成。':'选择自己的商品图，使用当前参考图已保存的最新视觉配方生成；出图后核对商品外观与 Logo。';invalidate();renderChoiceCards();syncToolUI();}
function requestPayload(){let ids=selectedAssets();const mode=$('mode').value;const reference=$('reference').value||null;if(mode==='B2'&&S.tool==='promo'&&!$('background-image').value)throw new Error('请上传或选择想复刻的参考场景。');if(mode==='C_analyze')ids=reference?[reference]:[];if(mode==='C2'&&$('subject-image').value)ids=[$('subject-image').value];if(mode==='A_white'&&ids.length!==1)throw new Error('白底图只使用 1 张实拍，请点击商品卡重新选择一张。');if(mode==='A_views'){if(S.drawingMain===null||(S.drawingMain&&!ids.includes(S.drawingMain)))throw new Error('请选择 1 张主视图。');if(ids.length>6)throw new Error('工业草图仅支持 1 张主视图和最多 5 张补充角度。');}if(!ids.length)throw new Error(mode==='C_analyze'?'请添加参考图。':'请添加并选择待处理图片。');if(ids.length>10)throw new Error('最多 10 张图片');if(mode==='B2'&&$('product-set').value==='views'&&ids.length>9)throw new Error('同一商品最多 9 个角度，为场景图保留一个位置');let recipe=null;if(mode==='C2'){recipe=S.data.recipes.find(r=>r.reference_id===reference)?.id;if(!recipe)throw new Error('请先解析这张参考图，得到配方后再生成。');if(ids.length!==1)throw new Error('参考重构每次选择一张自己的商品图。');}
 return {execution:$('execution').value,mode,product_ids:mode==='B2'?[ids[0]]:ids,product_view_ids:mode==='B2'&&$('product-set').value==='views'?ids.slice(1):[],batch_product_ids:mode==='B2'&&$('product-set').value==='batch'?ids:[],batch_index:0,reference_id:mode.startsWith('C')?reference:null,back_id:mode.startsWith('A')&&mode!=='A_white'?($('back').value||null):null,background_id:(mode==='C2'||(mode==='B2'&&$('change-background').checked))?($('background-image').value||null):null,subject_id:mode==='B2'&&$('change-subject').checked?($('subject-image').value||null):null,change_background:$('change-background').checked,change_subject:mode==='B2'&&$('change-subject').checked,recipe_id:recipe,instructions:$('instructions').value,preserve:$('preserve').value,strategy:$('strategy').value,ratio:$('ratio').value,background:$('background').value};}
async function uploadFilesCore(files,roleOverride){if(S.uploading)throw new Error('请等待当前图片上传完成');files=Array.from(files);if(!files.length)return;if(files.length>10)throw new Error('一次最多添加 10 张图片，请分次添加。');if(files.some(f=>f.size>15*1024*1024))throw new Error('单张图片不能超过 15 MB');if(files.some(f=>!['image/png','image/jpeg','image/webp'].includes(f.type)))throw new Error('请选择 PNG、JPEG 或 WebP 图片。');const role=roleOverride||$('upload-target').value;if(role!=='products'&&files.length!==1)throw new Error('背景、参考或替换主体每次添加一张。');const previous=selectedAssets();if(role==='products'&&previous.length+files.length>10)throw new Error('本次选择合计超过 10 张，请先取消部分图片的勾选。');const added=[];S.uploading=true;$('file').disabled=true;
 try{for(const file of files){const data=new FormData();data.append('file',file);data.append('source',$('source').value.trim()||file.name||'粘贴图片');const a=await api('/api/assets',{method:'POST',body:data});added.push(a.id);}await refresh();if(role==='products'){S.productOrder=previous.concat(added);for(const o of $('products').options)o.selected=previous.concat(added).includes(o.value);}else $(role).value=added[0];invalidate();renderLibrary();previews();message(`已添加 ${added.length} 张图片。`);}finally{S.uploading=false;$('file').disabled=false;$('file').value='';}}
async function start(){const session=await api('/api/session');S.csrf=session.csrf;S.copy=session.copy;S.recipeFields=session.recipe_fields;await refresh();setupMixStudio();setupChoiceCards();setupTools();goToolHome();document.querySelectorAll('.tabs button[data-tab]').forEach(b=>b.addEventListener('click',()=>setTab(b.dataset.tab)));bind('show-tests','change',refresh);bind('mode','change',updateMode);bind('execution','change',updateMode);bind('job-form','input',onGenerationInput);for(const id of ['reference','subject-image','background-image'])bind(id,'change',invalidate);bind('preset','change',()=>{if($('preset').value)$('instructions').value+=($('instructions').value?'\n':'')+$('preset').value;$('preset').value='';invalidate();});bind('cancel-external','click',()=>{if(S.approval?.batch){S.approval=null;$('external-preview').hidden=true;renderVisualFlow();}else invalidate();});bind('confirm-external','click',confirmExternal);bind('job-form','submit',submitForm);bind('upload-form','submit',e=>e.preventDefault());bind('file','change',async()=>{try{await uploadToSlot($('file').files,defaultInputRole());}finally{$('file').value='';}});const drop=$('drop-zone');drop.addEventListener('dragover',e=>{e.preventDefault();drop.classList.add('dragging');});drop.addEventListener('dragleave',()=>drop.classList.remove('dragging'));drop.addEventListener('drop',e=>{e.preventDefault();drop.classList.remove('dragging');if(!S.uploading)uploadToSlot(e.dataTransfer.files,defaultInputRole()).catch(err=>message(err.message,true));});document.addEventListener('paste',e=>{const files=Array.from(e.clipboardData?.files||[]);if(files.length){e.preventDefault();if(!S.uploading)uploadToSlot(files,$('image-picker').open?S.pickerRole:(S.activeInputRole||defaultInputRole())).catch(err=>{message(err.message,true);$('picker-status').textContent=err.message;});}});bind('demo','click',async()=>{const r=await api('/api/demo',{method:'POST'});$('show-tests').checked=true;await refresh();$('products').value=r.product_id;$('reference').value=r.reference_id;$('execution').value='fixture';renderLibrary();updateMode();message('已载入开发测试素材。');});bind('compare','click',()=>{const one=S.data.candidates.find(c=>c.id===$('compare-one').value),two=S.data.candidates.find(c=>c.id===$('compare-two').value);if(!one||!two)throw new Error('请选择两张候选');if(JSON.stringify(one.data.request.product_ids)!==JSON.stringify(two.data.request.product_ids))throw new Error('请选择同商品候选');$('comparison').replaceChildren();preview($('comparison'),one.asset_id,'C1');preview($('comparison'),two.asset_id,'C2');});setInterval(async()=>{try{if(S.data.jobs.some(j=>['queued','running'].includes(j.state))){await refresh();if(S.selected)await showJob(S.selected);}}catch(e){message(e.message,true);}},1600);}

start().catch(err=>message(err.message,true));

async function submitForm(e){
  e.preventDefault();
  const epoch=S.draftEpoch;const payload=requestPayload(), serialized=JSON.stringify(payload);
  if(S.uploading)throw new Error('请等待图片上传完成');if(!S.submitKey||S.pendingPayload!==serialized)S.submitKey=crypto.randomUUID();
  S.pendingPayload=serialized;
  $('submit-job').disabled=true;S.visualResult=null;S.previewing=true;renderVisualFlow();
  try {
    if(payload.execution==='real'){
      const preview=await api('/api/jobs/preview',{method:'POST',body:serialized});if(epoch!==S.draftEpoch)return;
      S.approval={preview,serialized,key:S.submitKey};
      $('external-ack').checked=false;
      const plan=preview.plan;
      $('external-summary').textContent=`接收方：${plan.recipient}；模型：${plan.model}。发送 ${preview.sent_assets.length} 张图片及下列文字/快照。最多 1 次调用，最多 ${plan.max_output_images} 张结果图。费用 unknown，无自动重试；重复新建真实任务可能重复收费。`;
      $('external-text').textContent=JSON.stringify({requirements:preview.compiled_prompt||plan.prompt,analysis:plan.analysis,recipe:plan.recipe,mode:plan.request.mode},null,2);
      $('external-images').replaceChildren();
      preview.sent_assets.forEach(asset=>previewImage(asset));
      $('external-preview').hidden=false;$('external-preview').scrollIntoView({behavior:'smooth',block:'center'});
      message('外发预览已准备；尚未创建付费任务。');
      return;
    }
    await sendJob(payload,S.submitKey);
  } finally {if(epoch===S.draftEpoch){$('submit-job').disabled=false;S.previewing=false;renderVisualFlow();}}
}
function previewImage(asset){preview($('external-images'),asset.id,`${asset.fixture?'测试素材 · ':''}${asset.source} · ${asset.id.slice(0,8)}`);}
async function sendJob(payload,key,token=''){
  const epoch=S.draftEpoch;const job=await api('/api/jobs',{method:'POST',headers:{'Idempotency-Key':key,'X-External-Confirmation':token},body:JSON.stringify(payload)});
  await refresh();if(epoch!==S.draftEpoch)return;await showJob(job.id,true);message(UI.queued);
}
async function confirmExternal(){const epoch=S.draftEpoch;
  if(S.approval?.batch){if(!$('external-ack').checked)throw new Error('请确认本批次图片和调用次数');$('confirm-external').disabled=true;try{const p=S.approval.preview;const results=await api('/api/batch/'+p.candidate_id+'/submit',{method:'POST',headers:{'X-External-Confirmation':p.confirmation_token}});if(epoch!==S.draftEpoch){await refresh();return;}invalidate();await refresh();if(results.length)await showJob(results[0].id,true);message('剩余任务已提交；刷新或重复确认不会重复生成同一批次。');}finally{$('confirm-external').disabled=false;}return;}

  if(!S.approval||(!S.approval.check&&JSON.stringify(requestPayload())!==S.approval.serialized))throw new Error('输入已改变，请重新预览。');
  if(!$('external-ack').checked)throw new Error('请先阅读并勾选本次外发与调用授权。');
  $('confirm-external').disabled=true;
  try{await sendJob(JSON.parse(S.approval.serialized),S.approval.key,S.approval.preview.confirmation_token);if(epoch===S.draftEpoch)$('external-preview').hidden=true;}
  finally{$('confirm-external').disabled=false;}
}
function fillRequest(r){$('result-details').close();if(['A_white','A_views','B2'].includes(r.mode))S.tool=r.mode==='A_views'?'drawing':'promo';setTab(r.mode.startsWith('C')?'C':r.mode==='B2'?'B':'A');if(Array.from($('mode').options).some(o=>o.value===r.mode))$('mode').value=r.mode;$('product-set').value=r.batch_product_ids?.length?'batch':'views';const ids=r.batch_product_ids?.length?r.batch_product_ids:[...r.product_ids,...(r.product_view_ids||[])];S.productOrder=ids;S.drawingMain=ids[0]||null;for(const o of $('products').options)o.selected=ids.includes(o.value);for(const[id,key]of [['instructions','instructions'],['preserve','preserve'],['background-image','background_id'],['subject-image','subject_id'],['reference','reference_id'],['ratio','ratio'],['execution','execution'],['back','back_id'],['strategy','strategy'],['background','background'],['recipe','recipe_id']])$(id).value=r[key]||'';$('change-background').checked=r.change_background!==false;$('change-subject').checked=!!r.change_subject;updateMode();renderLibrary();$('instructions').focus();}
function resultNextSteps(detail,target,compact=false){const c=detail.candidate;if(!c)return;const r=detail.job.payload.request;const actions=node('div',undefined,'result-actions');
 if(!c.fixture){const add=node('button','加入待处理图片列表','secondary');add.type='button';add.addEventListener('click',async()=>{add.disabled=true;try{await refresh();applySlot(defaultInputRole(),[c.asset_id]);message('已加入待处理图片列表并选中，当前操作路线保持不变。');}catch(e){message(e.message,true);}finally{add.disabled=false;}});actions.append(add);}

 if(!c.fixture&&r.mode==='A_white'){const next=node('button','继续制作场景宣传图 →','primary');next.type='button';next.addEventListener('click',()=>continueWithCandidate(detail));actions.append(next);}

 if(r.mode==='A_white'){const cut=node('button','抠图 · 下载无背景 PNG','secondary');cut.type='button';cut.addEventListener('click',async()=>{cut.disabled=true;try{const job=await api('/api/candidates/'+c.id+'/cutout',{method:'POST'});await refresh();await showJob(job.id,true);}catch(e){message(e.message,true);}finally{cut.disabled=false;}});actions.append(cut);}
 if(r.mode==='B2'&&!r.batch_index){if((r.batch_product_ids||[]).length>1){if(!compact){const review=node('section',undefined,'batch-review');renderBatchReview(detail,review);target.append(review);}}else{const retry=node('button','不满意 · 添加修改意见再生成','secondary');retry.type='button';retry.addEventListener('click',()=>reviseBatchSample(detail));actions.append(retry);}}
 if(r.anchor_candidate_id&&!compact){const anchor=S.data.candidates.find(a=>a.id===r.anchor_candidate_id);if(anchor)preview(target,anchor.asset_id,'此批次已通过的风格样张');}
 target.append(actions);
}

function renderScenePreview(){const box=$('scene-preview');if(!box)return;box.replaceChildren();if($('background-image').value)preview(box,$('background-image').value,'将沿用此场景、光线与构图');renderVisualFlow();}
function setupMixStudio(){
 document.documentElement.style.setProperty('--action-dock-height','0px');

 bind('open-history','click',()=>{document.body.dataset.tool='history';syncGlassNav();const history=$('history-panel');history.querySelector('details').open=true;history.scrollIntoView({behavior:'smooth',block:'start'});});
 bind('close-result-details','click',()=>$('result-details').close());
 $('result-details').addEventListener('click',e=>{if(e.target===$('result-details'))$('result-details').close();});
 const scene=$('scene-drop');
 scene.addEventListener('focusin',()=>{$('upload-target').value='background-image';});
 scene.addEventListener('click',()=>{$('upload-target').value='background-image';});
 $('drop-zone').addEventListener('focusin',()=>{$('upload-target').value='products';});
 $('drop-zone').addEventListener('click',()=>{$('upload-target').value='products';});
 bind('scene-file','change',async()=>{await uploadFiles($('scene-file').files,'background-image');$('scene-file').value='';});
 scene.addEventListener('dragover',e=>{e.preventDefault();scene.classList.add('dragging');});
 scene.addEventListener('dragleave',()=>scene.classList.remove('dragging'));
 scene.addEventListener('drop',e=>{e.preventDefault();scene.classList.remove('dragging');if(!S.uploading)uploadFiles(e.dataTransfer.files,'background-image').catch(err=>message(err.message,true));});
 bind('background-image','change',()=>{renderScenePreview();renderLibrary();});
 bind('product-set','change',()=>{invalidate();$('product-set-help').textContent=$('product-set').value==='views'?'首图决定主体，其余补充细节；只生成一件商品。':'每张图代表一个商品。先试第一件，通过后统一生成剩余商品。';});
}

// Disclosure/consent interactions do not alter the signed generation request.
function onGenerationInput(e){
 const target=e.target;
 if(target.closest('#external-preview'))return;
 if(!target.matches('input, select, textarea'))return;
 const parameters=new Set(['mode','change-background','change-subject','subject-image','background-image','preset','instructions','preserve','ratio','execution','back','strategy','background','mask','scale','pos-x','pos-y','feather','shadow']);
 if(!parameters.has(target.id))return;
 invalidate();fieldVisibility();
}

// Cards adapt the existing canonical selects; change handlers and signed previews stay shared.
const choiceDescriptions={A:'解析光线、材质与构图；复制完整提示词或单个参数。',A_white:'实拍变干净白底图；完成后可直接进入场景混图。',A_views:'说明书外观插图与设计沟通初稿，不作为生产工程图。',C_analyze:'从参考图提取可调整的视觉配方。',C2:'使用已保存配方，为自己的商品生成新图。',views:'多张照片是一件商品的不同角度。',batch:'每张是一件商品，先确认首张，再继续批量。',real:'预览图片与请求后确认调用。',fixture:'本地验证流程，不调用真实模型。'};
function setupChoiceCards(){
 for(const id of ['mode','product-set','ratio','execution','preset']){const select=$(id);select.hidden=true;const group=node('div',undefined,'choice-cards '+(id==='ratio'||id==='preset'?'compact-choices':''));group.id=id+'-cards';group.setAttribute('role','group');group.setAttribute('aria-label',{mode:'商品处理方式', 'product-set':'商品照片分组',ratio:'画布比例',execution:'执行方式',preset:'场景快捷补充'}[id]);select.after(group);select.addEventListener('change',renderChoiceCards);}
 renderChoiceCards();
}
function renderChoiceCards(){
 for(const id of ['mode','product-set','ratio','execution','preset']){const group=$(id+'-cards');if(!group)continue;group.hidden=id==='mode'&&S.tab==='B';group.replaceChildren();for(const option of $(id).options){if(!option.value)continue;const button=node('button',undefined,'choice-card');button.type='button';button.setAttribute('aria-pressed',String(id!=='preset'&&option.selected));button.append(node('b',option.text));if(choiceDescriptions[option.value])button.append(node('small',choiceDescriptions[option.value]));button.addEventListener('click',()=>{$(id).value=option.value;$(id).dispatchEvent(new Event('change',{bubbles:true}));invalidate();renderChoiceCards();});group.append(button);}}
}
async function continueWithCandidate(detail){
 $('result-details').close();
 try{await refresh();const c=detail.candidate,r=detail.job.payload.request;S.tool='promo';setTab('B');$('products').value=c.asset_id;S.productOrder=[c.asset_id];$('product-set').value='views';$('product-set').dispatchEvent(new Event('change'));$('change-subject').checked=false;$('change-background').checked=true;$('subject-image').value='';$('background-image').value='';$('instructions').value='';$('preserve').value=r.preserve||'';$('ratio').value=r.ratio||'1:1';$('execution').value='real';updateMode();renderLibrary();previews();$('canvas-title').scrollIntoView({behavior:'smooth',block:'start'});message('已把这张结果设为新商品主图。添加目标场景即可继续；未自动调用模型。');}catch(e){message(e.message,true);}
}
async function previewQualityCheck(candidateId){
 invalidate();const p=await api('/api/candidates/'+candidateId+'/check-preview',{method:'POST'});
 S.approval={check:true,preview:p,serialized:JSON.stringify(p.plan.request),key:crypto.randomUUID()};
 $('external-ack').checked=false;$('external-summary').textContent=`AI 对照检查：${p.plan.recipient} / ${p.plan.model}。发送 ${p.sent_assets.length} 张图片及原生成要求，最多调用 1 次，只输出检查报告，不重绘。费用以供应商账单为准。`;
 $('external-text').textContent=p.plan.prompt;$('external-images').replaceChildren();p.sent_assets.forEach(previewImage);$('external-preview').hidden=false;$('external-preview').scrollIntoView({behavior:'smooth',block:'start'});
}
function renderQualityCheck(detail,target){
 const report=detail.analysis.data;target.append(node('p',report.summary,'description'),node('p',report.limitations,'warning'));
 const names={issue:'发现问题',no_obvious_issue:'未见明显问题',unknown:'无法判断'};
 for(const item of report.checks){const block=node('section',undefined,'step-card');block.append(node('h3',item.topic+' · '+names[item.status]),node('p',item.observation),node('p','位置：'+item.location,'hint'));if(item.suggestion&&item.status==='issue')block.append(node('p','修改建议：'+item.suggestion));target.append(block);}
 const issues=report.checks.filter(i=>i.status==='issue');if(!issues.length){target.append(node('p','没有明确问题可带入；仍需人工核对商品细节。','hint'));return;}
 const use=node('button','把问题带入修改意见','secondary');use.type='button';use.addEventListener('click',async()=>{try{const c=S.data.candidates.find(x=>x.id===detail.job.payload.request.check_candidate_id);if(!c)throw new Error('原结果不在当前记录中，请从历史重新打开。');const source=await api('/api/jobs/'+c.job_id);fillRequest(source.job.payload.request);const advice=issues.map(i=>`${i.topic}（${i.location}）：${i.observation}；${i.suggestion}`).join('\n');$('instructions').value=($('instructions').value+'\n待人工确认的 AI 修改建议：\n'+advice).slice(0,8000);invalidate();$('instructions').focus();message('已恢复原生成设置并加入建议，请核对后预览；未自动重绘。');}catch(e){message(e.message,true);}});target.append(use);
}

async function uploadFiles(files,roleOverride){
 const role=roleOverride||$('upload-target').value;
 const status=role==='background-image'?$('scene-status'):null;
 if(S.uploading)throw new Error('请等待当前图片上传完成');
 if(!files.length)return;
 if(status){status.textContent='正在上传参考场景…';status.className='hint';}
 try{
  await uploadFilesCore(files,role);
  if(status){status.textContent='参考场景已上传并选中，可查看上方预览。';status.className='hint';}
 }catch(e){
  if(status){status.textContent='未上传：'+e.message+'。请选择符合要求的图片后重试；原有商品和场景选择保留。';status.className='warning';}
  throw e;
 }finally{
  if(role==='background-image')$('scene-file').value='';
  else $('file').value='';
 }
}

const TOOL_CATALOG={
 promo:{title:'生成宣传图物料',description:'先得到纯净的商品展示图，再让商品进入喜欢的场景。'},
 drawing:{title:'生成说明书工业草图',description:'提供正面、侧面、俯视或其他角度，生成说明书外观插图初稿。'}
};
function setAssetDrawer(open){
 $('asset-drawer').hidden=!open;$('asset-backdrop').hidden=!open;
 $('toggle-assets').setAttribute('aria-expanded',String(open));
 document.body.classList.toggle('assets-open',open);
 if(open){$('upload-target').value='products';S.activeInputRole=defaultInputRole();}
}
function goToolHome(){S.draftEpoch=(S.draftEpoch||0)+1;S.selected=null;invalidate();S.activeInputRole=null;S.tool=null;document.body.dataset.tool='home';setAssetDrawer(false);$('message').textContent='';syncGlassNav();window.scrollTo({top:0,behavior:'smooth'});}
function resetTaskDraft(){
 S.draftEpoch=(S.draftEpoch||0)+1;
 S.selected=null;S.resultStamp=null;S.visualResult=null;S.productOrder=[];S.drawingMain=null;
 S.activeInputRole=null;S.pickerRole=null;S.submitKey=null;S.pendingPayload=null;S.approval=null;S.previewing=false;
 for(const option of $('products').options)option.selected=false;
 for(const id of ['instructions','preserve','back','subject-image','background-image','reference','analysis','recipe','mask','preset','source'])$(id).value='';
 for(const [id,value] of Object.entries({'product-set':'views',execution:'real',background:'#ffffff',ratio:'1:1',strategy:'reference_recipe',scale:'0.7','pos-x':'0.5','pos-y':'0.5',feather:'0'}))$(id).value=value;
 $('change-subject').checked=false;$('change-background').checked=true;$('shadow').checked=true;$('external-ack').checked=false;
 $('external-preview').hidden=true;$('external-summary').textContent='';$('external-text').textContent='';$('external-images').replaceChildren();
 $('result').replaceChildren();$('empty-result').hidden=true;
 for(const id of ['picker-status','scene-status','workspace-upload-status','recipe-status'])$(id).textContent='';
 for(const id of ['picker-file','file','scene-file','workspace-file'])$(id).value='';
 $('result-details').close();$('image-picker').close();
 document.querySelector('.requirements-card').open=false;
 $('submit-job').disabled=false;$('confirm-external').disabled=false;
 message('');
}
function selectTool(tool,mode=tool==='drawing'?'A_views':'A_white'){
 resetTaskDraft();S.tool=tool;setAssetDrawer(false);
 setTab(mode==='B2'?'B':'A');$('mode').value=mode;
 updateMode();renderLibrary();previews();renderJobs();
 window.scrollTo({top:0,behavior:'smooth'});
}
function syncToolUI(){
 if(!S.tool)return;
 const mode=$('mode').value;
 if(!['A_white','A_views','B2'].includes(mode))return;
 S.tool=mode==='A_views'?'drawing':'promo';document.body.dataset.tool=S.tool;
 const scene=mode==='B2';document.body.dataset.stage=scene?'scene':'white';
 $('tool-eyebrow').textContent=TOOL_CATALOG[S.tool].title;
 $('flow-title').textContent=mode==='A_views'?'生成说明书工业草图':scene?'制作场景宣传图':'制作纯净白底图';
 $('tool-description').textContent=mode==='A_views'?TOOL_CATALOG.drawing.description:scene?'用自己的商品，复刻参考图的背景、氛围与光线。':'上传同一商品的随手拍，获得干净的商品展示图；可直接下载或继续混图。';
 $('pipeline-steps').hidden=S.tool!=='promo';
 $('stage-white').setAttribute('aria-current',scene?'false':'step');$('stage-scene').setAttribute('aria-current',scene?'step':'false');
 $('operation-step').textContent=mode==='A_views'?'1 · 添加商品三视图 / 多角度实拍':scene?'1 · 商品与参考场景':'1 · 添加商品实拍';
 $('quick-presets').hidden=!scene;
 $('instructions').placeholder=mode==='A_views'?'例如：突出接口与按键轮廓，保持各视图比例一致。':scene?'例如：保留参考图的地面与侧光，移除广告文字。':'例如：保留屏幕文字与按钮位置，去除桌面杂物。';
 $('submit-job').textContent=mode==='A_views'?'预览并生成工业草图':scene?'预览并生成场景图':'预览并生成白底图';
 syncGlassNav();renderVisualFlow();
 $('generation-intent').textContent=scene?'确认首张效果，再决定后续':mode==='A_views'?'说明书插图初稿 · 需核对结构':'白底图完成后，可下载或继续混图';
}
function setupTools(){
 setupGlassStudio();
 bind('choose-promo','click',()=>selectTool('promo'));bind('choose-drawing','click',()=>selectTool('drawing'));
 bind('new-task','click',()=>selectTool(S.tool,$('mode').value));
 bind('tool-home','click',goToolHome);bind('toggle-assets','click',()=>setAssetDrawer($('asset-drawer').hidden));
 for(const id of ['workspace-assets','select-working-assets'])bind(id,'click',()=>setAssetDrawer(true));
 for(const id of ['close-assets','asset-backdrop'])bind(id,'click',()=>setAssetDrawer(false));
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('asset-drawer').hidden){setAssetDrawer(false);$('toggle-assets').focus();}});
 bind('stage-white','click',()=>{S.activeInputRole='white';S.tool='promo';setTab('A');$('mode').value='A_white';$('instructions').value='';updateMode();});
 bind('stage-scene','click',()=>{S.activeInputRole='products';message('');setTab('B');$('instructions').value='';updateMode();});
}
function renderWorkingAssets(){
 const box=$('working-assets');if(!box)return;box.replaceChildren();const ids=selectedAssets();
 if(!ids.length){renderVisualFlow();return;}
 for(const id of ids){const item=node('div',undefined,'working-asset');preview(item,id,ids.length===1?'本次商品':'参考角度 / 商品 '+(ids.indexOf(id)+1));const remove=node('button','移出本次','text-button');remove.type='button';remove.addEventListener('click',()=>{Array.from($('products').options).find(o=>o.value===id).selected=false;invalidate();renderLibrary();});item.append(remove);box.append(item);}
 renderVisualFlow();
}

function setupGlassStudio(){
 bind('gallery-all','click',()=>$('open-history').click());
 $('batch-settings').append($('product-set').parentElement);
 bind('picker-close','click',()=>$('image-picker').close());
 bind('picker-local','click',()=>$('picker-file').click());
 bind('picker-library','click',()=>{$('picker-library-grid').hidden=false;renderPicker();});
 bind('picker-file','change',async()=>{try{await uploadToSlot($('picker-file').files,S.pickerRole);}catch(e){$('picker-status').textContent=e.message;}finally{$('picker-file').value='';}});
 $('image-picker').addEventListener('click',e=>{if(e.target===$('image-picker'))$('image-picker').close();});
}
function syncGlassNav(){
 const current=document.body.dataset.tool;
 $('page-title').textContent={home:'首页',promo:'宣传图物料',drawing:'说明书工业草图',history:'历史作品'}[current]||'首页';
 $('tool-home').hidden=current==='home';$('new-task').hidden=!['promo','drawing'].includes(current);
 document.title=($('page-title').textContent)+' · Storm Studio.';
}
function slotSelection(role,ids=selectedAssets()){
 if(role==='scene')return $('background-image').value?[$('background-image').value]:[];
 if(role==='main')return S.drawingMain&&ids.includes(S.drawingMain)?[S.drawingMain]:[];
 if(role==='angles')return ids.filter(id=>id!==S.drawingMain);
 return ids;
}
function planSlotSelection(role,existing,incoming,main){
 incoming=[...new Set(incoming)];
 if(role==='white'){if(incoming.length!==1)throw new Error('白底图请选择 1 张商品实拍，不添加辅助角度。');return {ids:incoming,main};}
 if(role==='main'){
  if(incoming.length!==1)throw new Error('主视图最多选择 1 张。');
  const angles=existing.filter(id=>id!==main&&id!==incoming[0]);
  if(angles.length>5)throw new Error('补充角度最多 5 张，请先移除多余图片。');
  return {ids:[incoming[0],...angles],main:incoming[0]};
 }
 if(role==='scene'){
  if(incoming.length!==1)throw new Error('参考场景请选择 1 张。');
  return {ids:incoming,main};
 }
 const ids=[...new Set([...existing,...incoming])];
 if(role==='angles'&&ids.filter(id=>id!==main).length>5)throw new Error('补充角度最多 5 张。');
 if(role==='products'&&ids.length>10)throw new Error('商品图片最多 10 张。');
 return {ids,main};
}
function applySlot(role,incoming){
 const result=planSlotSelection(role,selectedAssets(),incoming,S.drawingMain);
 if(role==='scene'){
  const id=result.ids[0];if(!Array.from($('background-image').options).some(o=>o.value===id))$('background-image').append(new Option('已选作品',id));
  $('background-image').value=id;
 }else{
  S.drawingMain=result.main;S.productOrder=result.ids;
  for(const o of $('products').options)o.selected=result.ids.includes(o.value);
 }
 invalidate();renderLibrary();previews();
}
function defaultInputRole(){if($('mode').value==='A_white')return 'white';return $('mode').value==='A_views'?(S.drawingMain?'angles':'main'):'products';}
function openImagePicker(role){
 S.pickerRole=role;S.activeInputRole=role;
 $('picker-title').textContent={white:'自己的商品 · 单张实拍',products:'自己的商品',main:'商品正面 / 主视图',angles:'补充角度',scene:'参考场景'}[role];
 $('picker-limit').textContent={white:'只选 1 张商品实拍，以该图的视角与结构生成白底图；选择新图会替换当前输入。暂不添加辅助角度。',products:'建议优先使用清晰白底商品图，有助于保留商品细节、提升混图效果；也支持实拍图。最多 10 张。',main:'选择 1 张主视图，可替换。',angles:'最多 5 张侧面、背面、俯视等补充角度。',scene:'选择 1 张背景或商品场景参考。'}[role]+' PNG / JPEG / WebP，每张不超过 15 MB。';
 $('picker-file').multiple=!['white','main','scene'].includes(role);
 $('picker-status').textContent='';$('picker-library-grid').hidden=true;renderPicker();$('image-picker').showModal();
}
function renderPicker(){
 const role=S.pickerRole;if(!role)return;
 const selected=slotSelection(role);const box=$('picker-selected');box.replaceChildren();
 for(const id of selected){const item=node('div',undefined,'picker-item');preview(item,id,id===S.drawingMain?'主视图':'已选图片');const remove=node('button','移除','secondary');remove.type='button';remove.addEventListener('click',()=>{if(role==='scene')$('background-image').value='';else{for(const o of $('products').options)if(o.value===id)o.selected=false;if(id===S.drawingMain)S.drawingMain=null;}invalidate();renderLibrary();renderPicker();});item.append(remove);box.append(item);}
 const library=$('picker-library-grid');library.replaceChildren();
 const candidates=new Set(S.data.candidates.filter(c=>!c.fixture).map(c=>c.asset_id));
 const assets=S.data.assets.filter(a=>!a.fixture&&(!isGeneratedAsset(a)||candidates.has(a.id)));
 if(!assets.length)library.append(node('p','还没有素材，请先从本地上传。','hint'));
 for(const a of assets){const button=node('button',undefined,'picker-item library-choice');button.type='button';button.setAttribute('aria-label','选用图片 '+a.id.slice(0,8));button.setAttribute('aria-pressed',String(selected.includes(a.id)));preview(button,a.id,a.source.slice(0,35));button.addEventListener('click',()=>{try{applySlot(role,[a.id]);$('picker-status').textContent='已选中，可继续选择或关闭。';renderPicker();}catch(e){$('picker-status').textContent=e.message;}});library.append(button);}
}
async function uploadToSlot(files,role){
 files=Array.from(files);if(!files.length)return;if(S.uploading)throw new Error('请等待当前图片上传完成');
 const epoch=S.draftEpoch;const existing=selectedAssets();planSlotSelection(role,existing,files.map((_,i)=>'upload-'+i),S.drawingMain);
 if(files.some(f=>f.size>15*1024*1024))throw new Error('单张图片不能超过 15 MB');
 if(files.some(f=>!['image/png','image/jpeg','image/webp'].includes(f.type)))throw new Error('请选择 PNG、JPEG 或 WebP 图片。');
 S.uploading=true;$('picker-local').disabled=true;$('picker-status').textContent='正在上传…';
 const added=[];
 try{
  for(const file of files){const data=new FormData();data.append('file',file);data.append('source',$('source').value.trim()||file.name||'粘贴图片');added.push((await api('/api/assets',{method:'POST',body:data})).id);}
  await refresh();if(epoch!==S.draftEpoch)return;applySlot(role,added);renderPicker();$('picker-status').textContent=`已添加 ${added.length} 张图片。`;message(`已添加 ${added.length} 张图片。`);
 }catch(e){$('picker-status').textContent=e.message;throw e;}
 finally{S.uploading=false;$('picker-local').disabled=false;}
}
function resultPhase(detail,previewing=false){
 if(previewing)return {busy:true,text:'正在准备生成预览…'};
 if(!detail)return {busy:false,text:'生成结果将在这里显示'};
 const state=detail.job.state;
 if(state==='queued')return {busy:true,text:'任务已排队，等待生成…'};
 if(state==='running')return {busy:true,text:'正在生成，请稍候…'};
 if(state==='interrupted')return {busy:false,text:'任务已中断，请查看任务记录'};
 if(state==='failed')return {busy:false,text:'生成失败'};
 if(state==='outcome_unknown')return {busy:false,text:'生成状态未知，请查看任务记录'};
 return {busy:false,text:detail.candidate?'':'暂无可显示的结果'};
}
function renderVisualFlow(){
 const box=$('visual-flow-cards');if(!box||!S.data)return;
 const saved=S.visualResult, request=saved?.job.payload.request;
 const mode=request?.mode||$('mode').value,drawing=mode==='A_views',scene=mode==='B2';
 const ids=request?requestProducts(request):selectedAssets();
 const isBatch=scene&&(request?request.batch_product_ids?.length>1:$('product-set').value==='batch'&&ids.length>1);
 const main=request?ids[0]:(ids.includes(S.drawingMain)?S.drawingMain:null);
 const background=request?request.background_id:$('background-image').value;
 const phase=resultPhase(saved,S.previewing);if(!saved&&!S.previewing&&S.approval)phase.text='请在下方确认，确认后开始生成';
 $('canvas-title').textContent=drawing?'把商品角度，整理成清晰的说明书草图':scene?'让自己的商品，进入喜欢的展示场景':'从一张实拍开始，得到纯净商品展示图';
 $('canvas-subtitle').textContent=drawing?'1 张主视图 + 最多 5 张补充角度 · 核对实物后用于说明书配图':scene?'沿用参考背景与光线 · 保留商品身份，完成后核对细节':'一张实拍，保留原视角与结构 · 只清理背景与杂物';
 const items=[{label:drawing?'主视图':'自己的商品',caption:drawing?'1. 商品正面 / 主视图 · 最多 1 张':scene?(isBatch?`共 ${ids.length} 件商品 · 先确认首张`:'自己的商品 · 支持多张'):'自己的商品 · 单张实拍',ids:drawing?(main?[main]:[]):ids,role:drawing?'main':scene?'products':'white',empty:'点击添加 / 拖入商品图片'}];
 if(drawing||scene)items.push({label:drawing?'补充角度':'参考场景',caption:drawing?'2. 侧面 / 俯视等角度 · 最多 5 张':'喜欢的背景与氛围',ids:drawing?ids.filter(id=>id!==main):(background?[background]:[]),role:drawing?'angles':'scene',empty:drawing?'点击添加 / 拖入补充角度':'点击添加 / 拖入参考场景'});
 items.push({label:mode==='CUTOUT'?'透明 PNG':drawing?'工业草图':scene?'场景成图':'白底展示图',caption:drawing?'3. 说明书插图初稿':isBatch?`当前第 ${(request?.batch_index||0)+1} / ${ids.length} 件商品`:'下载或继续创作',ids:saved?.candidate?[saved.candidate.asset_id]:[],empty:phase.text,final:true});
 renderBatchReview(saved,$('batch-review'));
 const progress=batchProgress(saved,S.data.jobs,S.data.candidates);document.querySelector('.canvas-action').hidden=!!progress;
 box.classList.toggle('two-tiles',items.length===2);box.replaceChildren();
 for(const [index,item]of items.entries()){
  if(index){const arrow=node('div',undefined,'flow-connector');if(items.length===2)arrow.append(node('small','去除杂物与背景'));arrow.append(node('span','→'));box.append(arrow);}
  const figure=node('figure',undefined,'flow-tile'+(item.final?' final':''));
  const picture=node(item.final?'div':'button',undefined,'flow-picture'+(item.ids.length>1?' stacked':'')+(item.final&&phase.busy?' is-loading':''));
  if(!item.final){picture.type='button';picture.setAttribute('aria-label','添加或管理'+item.label);picture.addEventListener('click',()=>openImagePicker(item.role));picture.addEventListener('focus',()=>{S.activeInputRole=item.role;});picture.addEventListener('dragover',e=>{e.preventDefault();picture.classList.add('dragging');});picture.addEventListener('dragleave',()=>picture.classList.remove('dragging'));picture.addEventListener('drop',e=>{e.preventDefault();picture.classList.remove('dragging');uploadToSlot(e.dataTransfer.files,item.role).catch(err=>message(err.message,true));});}
  picture.append(node('span',item.label,'flow-tag'));
  if(item.ids.length){const stack=node('div',undefined,'image-stack');item.ids.slice(0,3).reverse().forEach((id,i,arr)=>{const img=node('img');img.src='/api/assets/'+id;img.alt=item.label+' '+(arr.length-i);img.className='stack-layer layer-'+(arr.length-i-1);stack.append(img);});picture.append(stack);if(item.ids.length>1)picture.append(node('span',item.ids.length+' 张 · 点击管理','stack-count'));}
  else{const placeholder=node('div',undefined,'flow-placeholder');const icon=node('i',item.final?'✦':'+');if(item.final&&phase.busy)icon.className='loading-spinner';placeholder.append(icon,node('span',item.empty));picture.append(placeholder);}
  if(item.final){picture.setAttribute('aria-busy',String(phase.busy));picture.setAttribute('aria-live','polite');}
  figure.append(picture,node('figcaption',item.caption));if(scene&&index===0)figure.append(node('p','建议优先使用清晰白底图，有助于保留商品细节、提升混图效果。','product-input-tip'));if(item.final&&saved)renderCanvasResult(saved,figure);box.append(figure);
 }
}

function renderGallery(){
 const box=$('recent-gallery');if(!box)return;box.replaceChildren();
 const items=S.data.candidates.filter(c=>!c.fixture&&['A_white','A_views','B2'].includes(c.data.mode)&&S.data.assets.some(a=>a.id===c.asset_id)).slice(0,5);
 if(!items.length){box.append(node('p','完成第一张作品后，会在这里看到你的生成记录。','gallery-empty'));return;}
 for(const c of items){const button=node('button',undefined,'gallery-item');button.type='button';const img=node('img');img.src='/api/assets/'+c.asset_id;img.alt=S.copy.modes[c.data.mode];button.append(img,node('span',S.copy.modes[c.data.mode]));button.setAttribute('aria-label','查看作品 '+c.id.slice(0,8));button.addEventListener('click',async()=>{const epoch=S.draftEpoch;try{const detail=await api('/api/jobs/'+c.job_id);if(epoch!==S.draftEpoch)return;fillRequest(detail.job.payload.request);S.resultStamp=null;await showJob(c.job_id,true);}catch(e){message(e.message,true);}});box.append(button);}
}

// The whole batch stays visible even though each provider call receives one product.
function requestProducts(request){return request.batch_product_ids?.length?[...request.batch_product_ids]:[...request.product_ids,...(request.product_view_ids||[])];}
function batchProgress(detail,jobs,candidates){
 const request=detail?.job.payload.request;
 if(request?.mode!=='B2'||(request.batch_product_ids||[]).length<2)return null;
 const anchor=request.anchor_candidate_id?candidates.find(c=>c.id===request.anchor_candidate_id):detail.candidate;
 const first=request.batch_index?jobs.find(j=>j.id===anchor?.job_id):detail.job;
 const rows=request.batch_product_ids.map((asset,index)=>{
  const job=index===0?first:jobs.find(j=>j.payload.request.anchor_candidate_id===anchor?.id&&j.payload.request.batch_index===index);
  return {asset,index,job,state:job?.state||(index?'awaiting_approval':'queued')};
 });
 return {rows,anchor,first,remaining:rows.length-1,submitted:rows.slice(1).filter(r=>r.job).length,ready:first?.state==='succeeded'&&!!anchor};
}
function reviseBatchSample(detail){
 fillRequest(detail.job.payload.request);
 $('instructions').value+=($('instructions').value?'\n':'')+'修改意见：';
 document.querySelector('.requirements-card').open=true;
 $('instructions').scrollIntoView({behavior:'smooth',block:'center'});$('instructions').focus();
 message('已保留全部商品和参考场景。补充修改意见后重新生成首张；满意后再继续余下商品。');
}
async function previewBatchApproval(detail){
 const c=detail.candidate;
 const p=await api('/api/batch/'+c.id+'/preview',{method:'POST'});
 fillRequest(detail.job.payload.request);S.visualResult=detail;renderVisualFlow();
 S.approval={batch:true,preview:p};$('external-ack').checked=false;
 $('external-summary').textContent=`已选此图为风格样张。剩余 ${p.plans.length} 张，每张最多一次调用，合计最多 ${p.max_calls} 次收费调用，不自动重试。所有商品沿用原参考场景与这张通过样张，完成后仍需核对商品和 Logo。`;
 $('external-text').textContent=JSON.stringify(p.plans.map(x=>({model:x.model,recipient:x.recipient,request:x.request,prompt:x.prompt})),null,2);
 $('external-images').replaceChildren();const seen=new Set();for(const plan of p.plans)for(const a of plan.sent_assets||[])if(!seen.has(a.id)){seen.add(a.id);previewImage(a);}
 $('external-preview').hidden=false;$('external-preview').scrollIntoView({behavior:'smooth',block:'center'});
}
function renderBatchReview(detail,box){
 box.replaceChildren();const progress=batchProgress(detail,S.data.jobs,S.data.candidates);box.hidden=!progress;
 if(!progress)return;
 const {rows,anchor,first,remaining,submitted,ready}=progress;
 box.append(node('h3',submitted===remaining?'本批次生成进度':ready?'首张已生成，效果满意吗？':'先生成首张，确认效果后再继续'));
 box.append(node('p',`共 ${rows.length} 件商品 · ${submitted===remaining?'剩余任务已提交，不会重复生成':`先看第 1 件，余下 ${remaining} 件保留在本批次中`}。`,'hint'));
 const queue=node('div',undefined,'batch-queue');
 for(const row of rows){const item=node('button',undefined,'batch-product');item.type='button';item.disabled=!row.job;const img=node('img');img.src='/api/assets/'+row.asset;img.alt='第 '+(row.index+1)+' 件商品';
  const status=row.state==='awaiting_approval'?(submitted?'待提交':'等待首张确认'):row.index===0&&row.state==='succeeded'&&!submitted?'样张待确认':S.copy.states[row.state]||row.state;
  item.append(img,node('span',`第 ${row.index+1} 件 · ${status}`));
  if(row.job)item.addEventListener('click',async()=>{try{fillRequest(row.job.payload.request);S.resultStamp=null;await showJob(row.job.id,false);}catch(e){message(e.message,true);}});queue.append(item);
 }
 box.append(queue);
 if(ready&&submitted<remaining){
  const original={job:first,candidate:anchor};const actions=node('div',undefined,'batch-decisions');
  const approve=node('button',submitted?'继续提交剩余任务':`通过，继续生成余下 ${remaining} 张`,'primary');approve.type='button';
  approve.addEventListener('click',async()=>{approve.disabled=true;try{await previewBatchApproval(original);}catch(e){message(e.message,true);}finally{approve.disabled=false;}});
  actions.append(approve);
  if(!submitted){const retry=node('button','不满意，修改后重新生成','secondary');retry.type='button';retry.addEventListener('click',()=>reviseBatchSample(original));actions.append(retry);}
  box.append(actions,node('p','继续前会预览并确认调用次数；剩余商品使用这张通过样张统一风格。','hint'));
 }
}

function isCanvasResult(detail){return ['A_white','A_views','B2','CUTOUT'].includes(detail.job.payload.request.mode);}
async function openResultDetails(detail){
 if(S.selected!==detail.job.id||!S.resultStamp){S.resultStamp=null;await showJob(detail.job.id,false);}
 $('result-details').showModal();
}
function renderCanvasResult(detail,container){
 const box=node('div',undefined,'canvas-result-tools');const c=detail.candidate;
 if(c){
  const primary=node('div',undefined,'canvas-download');const download=node('a','下载 PNG','primary');download.href=`/api/assets/${c.asset_id}?download=true`;primary.append(download);box.append(primary);
  resultNextSteps(detail,box,true);
  box.append(node('p',c.data.mode==='A_views'?'说明书插图初稿，需核对结构与标注。':c.data.mode==='CUTOUT'?'透明背景已生成，请检查边缘。':'AI 生成，请核对商品结构、文字与 Logo。','hint'));
 }else if(detail.job.error){
  box.append(node('p',detail.job.error,'canvas-result-error'));
  const restore=node('button','调整设置后再生成','secondary');restore.type='button';restore.addEventListener('click',()=>{fillRequest(detail.job.payload.request);message('设置已恢复，修改后重新预览；未自动重试。');});box.append(restore);
 }
 const more=node('button','详情 · 记录与评价','text-link');more.type='button';more.addEventListener('click',()=>openResultDetails(detail).catch(e=>message(e.message,true)));box.append(more);container.append(box);
}
