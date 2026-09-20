const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
function setup(mode){
 const values={mode,reference:'',back:'',instructions:'',preserve:'',strategy:'reference_recipe',ratio:'1:1',execution:'real',background:'#ffffff','background-image':'','subject-image':'','product-set':'views'};
 const elements=Object.fromEntries(Object.entries(values).map(([id,value])=>[id,{value}]));
 elements.products={selectedOptions:[{value:'own-product'}]};
 elements['change-background']={checked:true};elements['change-subject']={checked:false};
 const context=vm.createContext({document:{getElementById:id=>elements[id]}});
 vm.runInContext(fs.readFileSync('src/studio/web/static/app.js','utf8').replace("start().catch(err=>message(err.message,true));",''),context);
 vm.runInContext("S.tool='promo'",context);
 return {elements,context};
}
test('scene step requires an explicit reference and keeps result image as product',()=>{
 const {elements,context}=setup('B2');
 assert.throws(()=>vm.runInContext('requestPayload()',context),/参考场景/);
 elements['background-image'].value='chosen-scene';
 const r=vm.runInContext('requestPayload()',context);
 assert.equal(r.product_ids[0],'own-product');assert.equal(r.background_id,'chosen-scene');
});
test('white and drawing steps exclude a previously selected scene',()=>{
 for(const mode of ['A_white','A_views']){
  const {elements,context}=setup(mode);elements['background-image'].value='stale-scene';
  const r=vm.runInContext('requestPayload()',context);
  assert.equal(r.mode,mode);assert.equal(r.background_id,null);assert.equal(r.execution,'real');
 }
});

test('drawing slot limits reject overflow and keep the selected main view first',()=>{
 const {context}=setup('A_views');
 assert.throws(()=>vm.runInContext("planSlotSelection('main',[],['a','b'],null)",context),/1 张/);
 const replaced=vm.runInContext("planSlotSelection('main',['front','side','back'],['new-front'],'front')",context);
 assert.deepEqual(Array.from(replaced.ids),['new-front','side','back']);
 assert.equal(replaced.main,'new-front');
 const full=vm.runInContext("planSlotSelection('angles',['front','a','b','c','d'],['e'],'front')",context);
 assert.equal(full.ids.length,6);
 assert.throws(()=>vm.runInContext("planSlotSelection('angles',['front','a','b','c','d','e'],['f'],'front')",context),/5 张/);
 assert.equal(vm.runInContext("planSlotSelection('angles',['front','a'],['a'],'front').ids.length",context),2);
});
test('drawing submission requires the main view and rejects more than five supplementary views',()=>{
 const {context,elements}=setup('A_views');
 vm.runInContext('S.drawingMain=null',context);
 assert.throws(()=>vm.runInContext('requestPayload()',context),/主视图/);
 vm.runInContext("S.drawingMain='own-product'",context);
 elements.products.selectedOptions=Array.from({length:7},(_,i)=>({value:i?'angle-'+i:'own-product'}));
 assert.throws(()=>vm.runInContext('requestPayload()',context),/最多 5 张/);
});
test('result placeholder stops loading for every terminal state',()=>{
 const {context}=setup('A_white');
 for(const state of ['queued','running'])assert.equal(vm.runInContext(`resultPhase({job:{state:'${state}'}}).busy`,context),true);
 for(const state of ['succeeded','failed','outcome_unknown','interrupted'])assert.equal(vm.runInContext(`resultPhase({job:{state:'${state}'}}).busy`,context),false);
 assert.equal(vm.runInContext('resultPhase(null,true).busy',context),true);
});

test('white input replaces the old selection and rejects multiple photos before submission',()=>{
 const {context,elements}=setup('A_white');
 const result=vm.runInContext("planSlotSelection('white',['old','old-angle'],['new'],null)",context);
 assert.deepEqual(Array.from(result.ids),['new']);
 assert.throws(()=>vm.runInContext("planSlotSelection('white',[],['front','back'],null)",context),/1 张/);
 elements.products.selectedOptions=[{value:'front'},{value:'back'}];
 assert.throws(()=>vm.runInContext('requestPayload()',context),/白底图只使用 1 张/);
 elements.products.selectedOptions=[{value:'front'}];elements.back.value='stale-back';
 assert.equal(vm.runInContext('requestPayload().back_id',context),null);
 assert.equal(vm.runInContext('defaultInputRole()',context),'white');
});

test('batch review keeps every product after the first result and waits for approval',()=>{
 const {context}=setup('B2');
 vm.runInContext(`
 var first={id:'first-job',state:'succeeded',payload:{request:{mode:'B2',product_ids:['one'],product_view_ids:[],batch_product_ids:['one','two'],batch_index:0}}};
 var sample={id:'sample',job_id:'first-job'};
 var detail={job:first,candidate:sample};
 `,context);
 assert.deepEqual(Array.from(vm.runInContext('requestProducts(first.payload.request)',context)),['one','two']);
 const p=vm.runInContext('batchProgress(detail,[first],[sample])',context);
 assert.equal(p.ready,true);assert.equal(p.remaining,1);assert.equal(p.submitted,0);
 assert.equal(p.rows[1].asset,'two');assert.equal(p.rows[1].state,'awaiting_approval');
});
test('remaining-job review resolves the approved sample and excludes another batch attempt',()=>{
 const {context}=setup('B2');
 vm.runInContext(`
 var first={id:'first-job',state:'succeeded',payload:{request:{mode:'B2',product_ids:['one'],batch_product_ids:['one','two'],batch_index:0}}};
 var sample={id:'sample',job_id:'first-job'};
 var child={id:'child-job',state:'running',payload:{request:{...first.payload.request,product_ids:['two'],batch_index:1,anchor_candidate_id:'sample'}}};
 var unrelated={...child,id:'other-job',state:'succeeded',payload:{request:{...child.payload.request,anchor_candidate_id:'other-sample'}}};
 `,context);
 const p=vm.runInContext('batchProgress({job:child},[first,unrelated,child],[sample])',context);
 assert.equal(p.first.id,'first-job');assert.equal(p.submitted,1);assert.equal(p.rows[1].job.id,'child-job');
 assert.equal(p.rows[1].state,'running');
 assert.deepEqual(Array.from(vm.runInContext('requestProducts(child.payload.request)',context)),['one','two']);
});

test('new task clears restored draft and approval without deleting assets or jobs',()=>{
 const {context,elements}=setup('B2');
 const stub=()=>({value:'old',checked:true,hidden:false,textContent:'old',replaceChildren(){this.cleared=true;},close(){this.open=false;}});
 context.document.getElementById=id=>elements[id]||(elements[id]=stub());
 const requirements={open:true};context.document.querySelector=()=>requirements;
 elements.products.options=[{value:'product',selected:true},{value:'other',selected:true}];
 vm.runInContext("S.data={assets:[{id:'asset'}],jobs:[{id:'running-job',state:'running'}]};S.draftEpoch=3;S.selected='old-job';S.productOrder=['product'];S.approval={key:'signed-old-request'};S.pendingPayload='old';S.drawingMain='product';",context);
 vm.runInContext('resetTaskDraft()',context);
 assert.ok(elements.products.options.every(o=>!o.selected));
 for(const id of ['instructions','preserve','background-image','back','subject-image','reference','analysis','recipe','source'])assert.equal(elements[id].value,'');
 assert.equal(elements.ratio.value,'1:1');assert.equal(elements['product-set'].value,'views');
 assert.equal(elements['external-preview'].hidden,true);assert.equal(requirements.open,false);
 assert.equal(vm.runInContext('S.selected',context),null);assert.equal(vm.runInContext('S.approval',context),null);
 assert.equal(vm.runInContext('S.draftEpoch',context),4);
 assert.equal(vm.runInContext('S.data.assets[0].id',context),'asset');
 assert.equal(vm.runInContext('S.data.jobs[0].state',context),'running');
});
