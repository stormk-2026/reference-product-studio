(()=>{
 const menu=document.getElementById('account-menu');
 async function refreshAccount(){const response=await fetch('/api/account');if(response.status===401){location.replace('/login');return;}if(!response.ok)return;const account=await response.json();if(!account.enabled)return;menu.hidden=false;document.getElementById('account-label').textContent=account.username+' · '+(account.owner?'不限次数':'剩余 '+account.quota.remaining+' 次');document.getElementById('account-quota').textContent=account.owner?'主账户 · 生成次数不限':'图片额度 '+account.quota.remaining+' / '+account.quota.limit+' 次';}
 document.getElementById('logout').addEventListener('click',async()=>{const session=await(await fetch('/api/session')).json();const response=await fetch('/api/auth/logout',{method:'POST',headers:{'X-CSRF-Token':session.csrf}});if(response.ok)location.replace('/login');});
 refreshAccount().catch(()=>{});setInterval(()=>{if(!document.hidden)refreshAccount().catch(()=>{});},5000);
 window.addEventListener('focus',()=>refreshAccount().catch(()=>{}));
})();
