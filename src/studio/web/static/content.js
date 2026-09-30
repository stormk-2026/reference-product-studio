'use strict';
const CONTENT = {kind:'app',ids:[],deck:null,approval:null,job:null,stamp:null,busy:false,upload:false,series:null,original:null};

function contentStatus(value,busy=false){$('content-status').textContent=value;$('content-status').classList.toggle('busy',busy);}
function contentBusy(value){CONTENT.busy=value;for(const root of [$('content-form'),$('content-editor'),$('content-output-actions')])for(const el of root.querySelectorAll('button,input,textarea,select'))el.disabled=value;}
function contentInvalidate(clearDeck=false){
 CONTENT.approval=null;CONTENT.series=null;$('content-approval').hidden=true;$('content-consent').checked=false;$('content-output').hidden=true;
 if(clearDeck){CONTENT.deck=null;CONTENT.original=null;$('content-editor').hidden=true;$('content-restore-copy').hidden=true;$('content-original').hidden=true;}
 contentStatus(clearDeck?'素材或方案已更新，请重新起草文案。':'内容已更新；需要重新预览模型调用。');
}
function contentKind(kind){
 CONTENT.kind=kind;document.querySelectorAll('[data-content-kind]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.contentKind===kind)));
 $('content-assets-title').textContent=kind==='app'?'2 · 添加 App 截图':'2 · 添加商品图片';
 $('content-upload-hint').textContent=kind==='app'?'拖入或粘贴真实 App 截图':'拖入商品实拍或已生成的展示图';
 $('content-name-label').textContent=kind==='app'?'App 名称':'商品名称';
 $('content-name').placeholder=kind==='app'?'例如：我的记账 App':'例如：桌面电子看板';
 $('content-facts').placeholder=kind==='app'?'例如：支持手动记账、分类汇总、月度图表；不支持自动同步银行卡。':'例如：外壳颜色、可见部件、已确认的功能与使用场景；不要填写未验证的参数。';
}
function startContentTool(){
 resetTaskDraft();setAssetDrawer(false);S.tool=null;document.body.dataset.tool='content';
 Object.assign(CONTENT,{ids:[],deck:null,approval:null,job:null,stamp:null,busy:false,upload:false,series:null,original:null});
 $('content-form').reset();contentKind('app');$('content-editor').hidden=true;$('content-output').hidden=true;$('content-approval').hidden=true;
 $('content-library-list').hidden=true;$('content-restore-copy').hidden=true;$('content-original').hidden=true;renderContentInputs();
 contentStatus('选择 App 或商品方案，添加素材与真实卖点。');syncGlassNav();window.scrollTo({top:0,behavior:'smooth'});
}
function contentBrief(){return {kind:CONTENT.kind,name:$('content-name').value.trim(),audience:$('content-audience').value.trim(),facts:$('content-facts').value.trim(),experience:$('content-experience').value.trim(),page_count:Number($('content-count').value),style:$('content-style').value,accent:$('content-accent').value};}
function contentRequest(mode){
 if(CONTENT.upload)throw new Error('请等待素材上传完成');
 if(!CONTENT.ids.length)throw new Error(CONTENT.kind==='app'?'请添加至少一张 App 截图':'请添加至少一张商品图');
 const brief=contentBrief();if(!brief.name||!brief.facts)throw new Error('请填写名称和真实功能 / 卖点');
 const request={mode,execution:mode==='CONTENT_RENDER'?'fixture':'real',ratio:'3:4',product_ids:[...CONTENT.ids],content_brief:brief};
 if(mode==='CONTENT_POLISH'||mode==='CONTENT_SCENE')request.content_deck=readContentDeck();
 if(mode==='CONTENT_POLISH')request.content_polish_note=$('content-polish-note').value.trim();
 if(mode==='CONTENT_SCENE')request.content_page_index=0;
 return request;
}
function renderContentInputs(){
 const root=$('content-inputs');root.replaceChildren();
 CONTENT.ids.forEach((id,index)=>{const card=node('div',undefined,'content-input-item'),im=node('img');im.src='/api/assets/'+id;im.alt=(CONTENT.kind==='app'?'App 截图':'商品图')+' '+(index+1);
  const remove=node('button','移除 '+(index+1),'secondary');remove.type='button';remove.disabled=CONTENT.busy;
  remove.addEventListener('click',()=>{CONTENT.ids=CONTENT.ids.filter(v=>v!==id);contentInvalidate(true);renderContentInputs();});card.append(im,remove);root.append(card);});
}
async function uploadContent(files){
 files=Array.from(files);$('content-file').value='';if(!files.length)return;
 if(CONTENT.busy||CONTENT.upload)throw new Error('请等待当前任务完成');
 if(CONTENT.ids.length+files.length>6)throw new Error('每次最多 6 张素材');
 if(files.some(f=>f.size>15*1024*1024||!['image/png','image/jpeg','image/webp'].includes(f.type)))throw new Error('请选择不超过 15 MB 的 PNG / JPEG / WebP 图片');
 const epoch=S.draftEpoch;CONTENT.upload=true;contentStatus('正在上传素材…',true);
 try{for(const file of files){const form=new FormData();form.append('file',file);form.append('source',file.name||'宣传图文素材');const asset=await api('/api/assets',{method:'POST',body:form});if(epoch!==S.draftEpoch)return;CONTENT.ids.push(asset.id);renderContentInputs();}
  await refresh();if(epoch===S.draftEpoch){contentInvalidate(true);contentStatus('素材已添加，填写名称和真实卖点即可起草。');}}
 finally{if(epoch===S.draftEpoch){CONTENT.upload=false;$('content-file').value='';}}
}
async function openContentLibrary(){
 await refresh();const root=$('content-library-list');root.replaceChildren();root.hidden=false;
 for(const a of S.data.assets.filter(a=>!a.fixture)){const button=node('button',undefined,'content-input-item');button.type='button';const im=node('img');im.src='/api/assets/'+a.id;im.alt=a.source||'图片资产';button.append(im,node('small','选择此图'));
  button.addEventListener('click',()=>{if(CONTENT.busy||CONTENT.ids.includes(a.id))return;if(CONTENT.ids.length>=6){message('最多选择 6 张',true);return;}CONTENT.ids.push(a.id);renderContentInputs();contentInvalidate(true);});root.append(button);}
 if(!root.children.length)root.append(node('p','还没有图片，请先上传。','hint'));
}
function contentManualDeck(brief,count){
 const labels=brief.kind==='app'?['封面','功能亮点','使用流程','使用场景','适合谁','总结']:['封面','商品卖点','使用场景','外观细节','适合谁','总结'];
 return {pages:Array.from({length:brief.page_count},(_,i)=>({label:labels[i],title:i===0?brief.name.slice(0,36):labels[i],body:'',image_index:i%count})),post_title:brief.name.slice(0,40),post_body:brief.facts,review_notes:'手动文案：请补充逐页内容，并核对所有事实。'};
}
function renderContentEditor(deck){
 CONTENT.deck=structuredClone(deck);const root=$('content-page-editors');root.replaceChildren();
 CONTENT.deck.pages.forEach((p,i)=>{const section=node('details',undefined,'content-page-editor');section.open=i===0;section.append(node('summary',`${String(i+1).padStart(2,'0')} / ${i===0?'封面':'正文'}`));
  for(const [key,label,max] of [['label','栏目标签',16],['title','页面标题',36],['body','页面正文',160]]){const input=node(key==='body'?'textarea':'input');input.value=p[key];input.maxLength=max;input.dataset.pageField=key;input.dataset.pageIndex=String(i);input.id=`content-p${i}-${key}`;if(key==='body')input.rows=3;const lab=node('label',label);lab.htmlFor=input.id;section.append(lab,input);}
  const select=node('select');select.dataset.pageIndex=String(i);select.dataset.pageField='image_index';select.id=`content-p${i}-image`;
  CONTENT.ids.forEach((_,j)=>select.append(new Option((CONTENT.kind==='app'?'截图 ':'商品图 ')+(j+1),j)));select.value=p.image_index;const label=node('label','本页使用的素材');label.htmlFor=select.id;section.append(label,select);root.append(section);});
 $('content-post-title').value=deck.post_title;$('content-post-body').value=deck.post_body;$('content-notes').textContent=deck.review_notes||'发布前请核对产品信息。';$('content-editor').hidden=false;
}
function readContentDeck(){
 if(!CONTENT.deck)throw new Error('请先起草或填写文案');const deck=structuredClone(CONTENT.deck);
 for(const input of $('content-page-editors').querySelectorAll('[data-page-field]'))deck.pages[Number(input.dataset.pageIndex)][input.dataset.pageField]=input.dataset.pageField==='image_index'?Number(input.value):input.value.trim();
 deck.post_title=$('content-post-title').value.trim();deck.post_body=$('content-post-body').value.trim();
 if(deck.pages.some(p=>!p.title||!p.label)||!deck.post_title||!deck.post_body)throw new Error('请填写每页标题、栏目标签及发布标题和正文');
 return deck;
}
function showContentApproval(kind,preview,serialized,key){
 CONTENT.approval={kind,preview,serialized,key};$('content-consent').checked=false;
 const plan=kind==='series'?preview.plans[0]:preview.plan;
 const count=kind==='series'?preview.max_calls:1;
 const name=kind==='series'?'Seedream 余下页面':kind==='CONTENT_SCENE'?'Seedream 首页视觉':kind==='CONTENT_POLISH'?'Kimi 二次润色':'Kimi 文案起草';
 $('content-approval-title').textContent='确认 '+name;
 const transfer=kind==='CONTENT_SCENE'?'原始截图/商品图留在本地叠放，本次仅发送文字提示词。':kind==='series'?'余下页只发送首页视觉背景作风格参考；原始截图/商品图留在本地。':kind==='CONTENT_POLISH'?'只发送已编辑文案与润色方向，不重复发送图片。':`发送 ${preview.sent_assets.length} 张素材供 Kimi 起草。`;
 $('content-approval-summary').textContent=`接收方：${plan.recipient}；模型：${plan.model}；本次最多 ${count} 次调用。${transfer}`;
 $('content-consent-label').textContent=`同意按本次预览发送列明素材与文字，最多调用 ${count} 次；费用以供应商账单为准，不自动重试。`;
 $('content-confirm').textContent='确认并开始';
 const sent=kind==='series'?preview.plans[0].sent_assets:preview.sent_assets;
 $('content-sent-images').replaceChildren();
 sent.forEach(a=>{const im=node('img',undefined,'content-input-item');im.src='/api/assets/'+a.id;im.alt=a.source;$('content-sent-images').append(im);});
 $('content-sent-text').textContent=kind==='series'?preview.plans.map((p,i)=>`第${i+2}页：\n${p.prompt}`).join('\n\n'):plan.prompt;
 $('content-approval').hidden=false;contentStatus('请核对接收方、发送内容与调用次数；尚未调用模型。');
 $('content-approval').scrollIntoView({behavior:'smooth',block:'start'});
}
async function previewContentAction(mode){
 const payload=contentRequest(mode),serialized=JSON.stringify(payload),epoch=S.draftEpoch;contentBusy(true);contentStatus('准备外发预览…',true);
 try{const preview=await api('/api/jobs/preview',{method:'POST',body:serialized});if(epoch!==S.draftEpoch)return;showContentApproval(mode,preview,serialized,crypto.randomUUID());}
 finally{if(epoch===S.draftEpoch)contentBusy(false);}
}
async function previewContentCopy(e){e.preventDefault();await previewContentAction('CONTENT_COPY');}
async function previewContentSeries(){
 if(!CONTENT.series)throw new Error('请先生成首页样张');const epoch=S.draftEpoch;contentBusy(true);contentStatus('准备余下页面预览…',true);
 try{const preview=await api('/api/content/series/'+CONTENT.series+'/preview',{method:'POST'});if(epoch!==S.draftEpoch)return;showContentApproval('series',preview,CONTENT.series,crypto.randomUUID());}
 finally{if(epoch===S.draftEpoch)contentBusy(false);}
}
async function submitContentApproval(){
 if(!CONTENT.approval||!$('content-consent').checked)throw new Error('请先勾选本次调用授权');
 const {kind,preview,serialized,key}=CONTENT.approval;
 if(kind!=='series'&&JSON.stringify(contentRequest(kind))!==serialized)throw new Error('内容已改变，请重新预览');
 if(kind==='series'&&CONTENT.series!==serialized)throw new Error('首页已改变，请重新预览');
 const epoch=S.draftEpoch;contentBusy(true);$('content-confirm').disabled=true;
 try{
  if(kind==='series'){
   const jobs=await api('/api/content/series/'+serialized+'/submit',{method:'POST',headers:{'X-External-Confirmation':preview.confirmation_token}});
   if(epoch!==S.draftEpoch)return;CONTENT.approval=null;$('content-approval').hidden=true;CONTENT.job=jobs.at(-1).id;S.selected=CONTENT.job;await refresh();await showSceneSeries(serialized);contentStatus(`已提交 ${jobs.length} 页；每页单次调用，无自动重试。`,true);
  }else{
   const job=await api('/api/jobs',{method:'POST',headers:{'Idempotency-Key':key,'X-External-Confirmation':preview.confirmation_token},body:serialized});
   if(epoch!==S.draftEpoch)return;CONTENT.approval=null;$('content-approval').hidden=true;CONTENT.job=job.id;S.selected=job.id;await refresh();if(epoch===S.draftEpoch)await showContentJob(job.id);
  }
 }catch(e){if(epoch===S.draftEpoch)contentBusy(false);throw e;}finally{$('content-confirm').disabled=false;}
}
function fillContentRequest(request){
 const b=request.content_brief;contentKind(b.kind);CONTENT.ids=[...request.product_ids];
 for(const [id,key] of [['name','name'],['audience','audience'],['facts','facts'],['experience','experience'],['count','page_count'],['style','style'],['accent','accent']])$('content-'+id).value=b[key];
 renderContentInputs();if(request.content_deck)renderContentEditor(request.content_deck);
}
async function showContentJob(id){
 const epoch=S.draftEpoch,detail=await api('/api/jobs/'+id);if(epoch!==S.draftEpoch)return;
 const mode=detail.job.payload.request.mode,stamp=id+':'+detail.job.state;
 if(CONTENT.stamp===stamp&&document.body.dataset.tool==='content'){if(CONTENT.series)await showSceneSeries(CONTENT.series);return;}
 const restoring=CONTENT.job!==id||document.body.dataset.tool!=='content';
 if(restoring){resetTaskDraft();Object.assign(CONTENT,{deck:null,upload:false,approval:null,series:null,original:null});$('content-approval').hidden=true;$('content-editor').hidden=true;$('content-output').hidden=true;$('content-restore-copy').hidden=true;$('content-original').hidden=true;fillContentRequest(detail.job.payload.request);}
 CONTENT.job=id;CONTENT.stamp=stamp;S.selected=id;S.tool=null;setAssetDrawer(false);document.body.dataset.tool='content';syncGlassNav();
 const state=detail.job.state;
 if(mode==='CONTENT_SCENE')CONTENT.series=detail.job.payload.request.anchor_candidate_id||detail.candidate?.id||null;
 if(['queued','running'].includes(state)){contentBusy(true);contentStatus(mode==='CONTENT_SCENE'?'Seedream 正在生成视觉图…':'Kimi 正在处理文案…',true);if(CONTENT.series)await showSceneSeries(CONTENT.series);return;}
 contentBusy(false);
 if(state!=='succeeded'){contentStatus((detail.job.error||'任务未完成')+'；未自动重试。');if(CONTENT.series)await showSceneSeries(CONTENT.series);return;}
 if(mode==='CONTENT_COPY'||mode==='CONTENT_POLISH'){
  if(mode==='CONTENT_POLISH'){CONTENT.original=detail.job.payload.request.content_deck;$('content-restore-copy').hidden=false;$('content-original').hidden=false;$('content-original-text').textContent=CONTENT.original.pages.map((p,i)=>`第${i+1}页 · ${p.title}\n${p.body}`).join('\n\n')+'\n\n发布标题：'+CONTENT.original.post_title+'\n发布正文：'+CONTENT.original.post_body;}
  renderContentEditor(detail.analysis.data);
  contentStatus(mode==='CONTENT_POLISH'?'润色版已生成，原版仍可恢复。核对后再生成视觉样张。':'文案已起草。请核对、手改或选择 Kimi 二次润色。');
 }else if(mode==='CONTENT_SCENE'){
  if(!CONTENT.deck)renderContentEditor(detail.candidate.data.deck);
  await showSceneSeries(CONTENT.series);
  contentStatus(detail.job.payload.request.content_page_index===0?'首页视觉样张已完成；满意后确认生成余下页面。':'视觉图正在逐页完成。');
 }else if(mode==='CONTENT_RENDER'){
  if(!CONTENT.deck)renderContentEditor(detail.candidate.data.deck);
  renderContentOutput(detail);contentStatus('这是旧版本地排版记录，未调用 Seedream。');
 }
}
function appendSceneFigure(root,aid,index,deck){
 const fig=node('figure'),image=node('img');image.src='/api/assets/'+aid;image.alt=deck.pages[index].title;
 const caption=node('figcaption');caption.append(node('span',`${index+1} / ${deck.pages[index].label}`));
 const download=node('a','下载 PNG');download.href='/api/assets/'+aid+'?download=true';caption.append(download);fig.append(image,caption);root.append(fig);
}
async function showSceneSeries(candidateId){
 if(!candidateId||document.body.dataset.tool!=='content')return;
 const status=await api('/api/content/series/'+candidateId);
 const deck=status.deck,root=$('content-pages'),actions=$('content-output-actions');root.replaceChildren();actions.replaceChildren();
 appendSceneFigure(root,status.first_asset_id,0,deck);
 for(const task of status.tasks){
  if(task.asset_id)appendSceneFigure(root,task.asset_id,task.index,deck);
  else if(task.state!=='not_started')root.append(node('p',`第 ${task.index+1} 页：${task.state}${task.error?' · '+task.error:''}`,'hint'));
 }
 $('content-output').hidden=false;$('content-output-title').textContent=status.complete?'Seedream 整套视觉图':'Seedream 视觉样张与进度';
 if(status.tasks.every(t=>t.state==='not_started')){
  const go=node('button',`首页满意 · 确认生成余下 ${status.tasks.length} 页`,'primary');go.type='button';
  go.addEventListener('click',()=>previewContentSeries().catch(e=>message(e.message,true)));actions.append(go);
 }else if(status.complete){
  const link=node('a','下载整套 PNG 与文案 ZIP','primary');link.href='/api/content/series/'+candidateId+'/export';actions.append(link);
 }else if(status.tasks.some(t=>['failed','outcome_unknown','interrupted'].includes(t.state))){
  actions.append(node('p','部分页面失败或结果未知；已停止自动处理。请核对供应商账单与请求记录。','warning'));
 }
 const edit=node('button','修改文案 / 重做首页','secondary');edit.type='button';edit.addEventListener('click',()=>$('content-editor').scrollIntoView({behavior:'smooth',block:'start'}));actions.append(edit);
}
function renderContentOutput(detail){
 const data=detail.candidate.data;$('content-output').hidden=false;$('content-output-title').textContent=data.sample?'旧版本地排版样稿':'旧版本地排版套图';
 const root=$('content-pages');root.replaceChildren();data.pages.forEach((id,i)=>appendSceneFigure(root,id,i,data.deck));
 const actions=$('content-output-actions');actions.replaceChildren();const download=node('a','下载旧版排版 ZIP','secondary');download.href='/api/jobs/'+detail.job.id+'/export';actions.append(download);
}
function setupContent(){
 bind('choose-content','click',startContentTool);bind('content-form','submit',e=>previewContentCopy(e).catch(err=>message(err.message,true)));
 bind('content-confirm','click',()=>submitContentApproval().catch(err=>message(err.message,true)));
 bind('content-cancel','click',()=>{CONTENT.approval=null;$('content-approval').hidden=true;$('content-consent').checked=false;contentStatus('已取消本次预览；未调用模型。');});
 bind('content-upload','click',()=>$('content-file').click());bind('content-file','change',e=>uploadContent(e.target.files).catch(err=>message(err.message,true)));
 bind('content-library','click',()=>openContentLibrary().catch(err=>message(err.message,true)));
 bind('content-manual','click',()=>{const r=contentRequest('CONTENT_RENDER');renderContentEditor(contentManualDeck(r.content_brief,r.product_ids.length));contentInvalidate();contentStatus('逐页填写并核对文案，再预览 Seedream 首页调用。');});
 bind('content-polish','click',()=>previewContentAction('CONTENT_POLISH').catch(err=>message(err.message,true)));
 bind('content-restore-copy','click',()=>{if(CONTENT.original){renderContentEditor(CONTENT.original);contentInvalidate();contentStatus('已恢复润色前文案。');}});
 bind('content-sample','click',()=>previewContentAction('CONTENT_SCENE').catch(err=>message(err.message,true)));
 bind('content-copy-post','click',async()=>{const d=readContentDeck();await navigator.clipboard.writeText(d.post_title+'\n\n'+d.post_body);message('已复制发布标题与正文。');});
 for(const button of document.querySelectorAll('[data-content-kind]'))button.addEventListener('click',()=>{if(CONTENT.busy||CONTENT.kind===button.dataset.contentKind)return;contentKind(button.dataset.contentKind);CONTENT.ids=[];renderContentInputs();contentInvalidate(true);});
 $('content-form').addEventListener('input',e=>{if(e.target.id!=='content-file')contentInvalidate(e.target.id==='content-count');});
 $('content-editor').addEventListener('input',e=>{if(e.target.id!=='content-polish-note')contentInvalidate();});
 const drop=$('content-drop');drop.addEventListener('dragover',e=>{e.preventDefault();drop.classList.add('dragging');});drop.addEventListener('dragleave',()=>drop.classList.remove('dragging'));drop.addEventListener('drop',e=>{e.preventDefault();drop.classList.remove('dragging');uploadContent(e.dataTransfer.files).catch(err=>message(err.message,true));});
 document.addEventListener('paste',e=>{if(document.body.dataset.tool!=='content'||!e.clipboardData?.files.length)return;e.preventDefault();uploadContent(e.clipboardData.files).catch(err=>message(err.message,true));});
 setInterval(()=>{if(CONTENT.series&&document.body.dataset.tool==='content')showSceneSeries(CONTENT.series).catch(()=>{});},2500);
}
setupContent();
