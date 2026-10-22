const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
function setup(){
 const elements={};
 const context=vm.createContext({structuredClone,document:{},$:(id)=>elements[id]??(elements[id]={value:'',hidden:false}),S:{draftEpoch:1}});
 vm.runInContext(fs.readFileSync('src/studio/web/static/content.js','utf8').replace('setupContent();',''),context);
 return {context,elements};
}
test('app and product plans have distinct sections and only reference selected images',()=>{
 const {context}=setup();
 for(const kind of ['app','product']){
  const d=vm.runInContext(`contentManualDeck({kind:'${kind}',name:'演示',facts:'真实资料',page_count:6},2)`,context);
  assert.equal(d.pages.length,6);assert.deepEqual(Array.from(d.pages,p=>p.image_index),[0,1,0,1,0,1]);
  assert.equal(d.pages[1].label,kind==='app'?'功能亮点':'商品卖点');
 }
 const long=vm.runInContext("contentManualDeck({kind:'app',name:'长'.repeat(48),facts:'资料',page_count:3},1)",context);
 assert.equal(long.pages[0].title.length,36);assert.equal(long.post_title.length,40);
});
test('content requests require material and facts, and rendering never requests real generation',()=>{
 const {context,elements}=setup();
 assert.throws(()=>vm.runInContext("contentRequest('CONTENT_COPY')",context),/截图/);
 vm.runInContext("CONTENT.ids=['screenshot'];",context);
 for(const [name,value] of Object.entries({name:'应用',facts:'真实功能',count:'3',style:'clean',accent:'#2563eb'}))elements['content-'+name]={value};
 const copy=vm.runInContext("contentRequest('CONTENT_COPY')",context),render=vm.runInContext("contentRequest('CONTENT_RENDER')",context);
 assert.equal(copy.execution,'real');assert.equal(render.execution,'fixture');assert.equal(render.ratio,'3:4');
 assert.equal(copy.content_brief.kind,'app');assert.equal(copy.product_ids[0],'screenshot');
 vm.runInContext('CONTENT.upload=true',context);assert.throws(()=>vm.runInContext("contentRequest('CONTENT_COPY')",context),/上传完成/);
});
test('failed copy submit keeps the same confirmation and idempotency key for explicit retry',async()=>{
 const {context}=setup();let calls=[];
 context.api=async(_url,opts)=>{calls.push(opts);throw new Error('network');};
 vm.runInContext(`contentRequest=()=>({mode:'CONTENT_COPY'});contentBusy=()=>{};CONTENT.approval={kind:'CONTENT_COPY',serialized:JSON.stringify({mode:'CONTENT_COPY'}),preview:{confirmation_token:'bound-token'},key:'stable-key'};$('content-consent').checked=true;`,context);
 for(let i=0;i<2;i++)await assert.rejects(vm.runInContext('submitContentApproval()',context),/network/);
 assert.equal(calls.length,2);assert.equal(calls[0].headers['Idempotency-Key'],calls[1].headers['Idempotency-Key']);
 assert.equal(calls[1].headers['X-External-Confirmation'],'bound-token');
});
