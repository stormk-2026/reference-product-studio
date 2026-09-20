const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
function setup(){
 const elements={'scene-status':{},'scene-file':{value:'same.png'},file:{value:''},'upload-target':{value:'background-image'}};
 const context=vm.createContext({document:{getElementById:id=>elements[id]}});
 const source=fs.readFileSync('src/studio/web/static/app.js','utf8').replace("start().catch(err=>message(err.message,true));",'');
 vm.runInContext(source,context);
 return {elements,context};
}
test('oversize scene reports error locally and resets picker for same-file retry',async()=>{
 const {elements,context}=setup();
 await assert.rejects(vm.runInContext("uploadFiles([{size:16*1024*1024,type:'image/png'}],'background-image')",context),/15 MB/);
 assert.match(elements['scene-status'].textContent,/未上传.*15 MB/);
 assert.equal(elements['scene-file'].value,'');
});
test('successful scene upload reports selection and clears the picker',async()=>{
 const {elements,context}=setup();
 vm.runInContext("uploadFilesCore=async(files,role)=>{if(role!=='background-image')throw Error('wrong role');}",context);
 await vm.runInContext("uploadFiles([{size:100,type:'image/png'}],'background-image')",context);
 assert.match(elements['scene-status'].textContent,/已上传并选中/);
 assert.equal(elements['scene-file'].value,'');
});
