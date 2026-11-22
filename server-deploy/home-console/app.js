let current = null, pending = null, busy = false;
const $ = id => document.getElementById(id);
const text = (tag, value, cls) => { const e = document.createElement(tag); e.textContent = value; if (cls) e.className = cls; return e; };
const clock = value => new Date(value).toLocaleString('zh-CN', {timeZone:'Asia/Hong_Kong',hour12:false});
function toast(message) { $('toast').textContent = message; $('toast').classList.add('show'); setTimeout(() => $('toast').classList.remove('show'), 4500); }
async function api(path, body) {
  const response = await fetch('/home/api/' + path, {credentials:'same-origin', cache:'no-store', ...(body ? {method:'POST',headers:{'Content-Type':'application/json','X-Home-CSRF':current?.csrf || ''},body:JSON.stringify(body)} : {})});
  if (response.status === 401) { location.href='/auth/login?returnTo=%2Fhome%2F'; throw Error('请重新登录'); }
  const data = await response.json();
  if (!response.ok) throw Error(data.error || '服务器暂时不可用');
  return data;
}
function render(data) {
  for (const category of ['chat','notice']) {
    const list = $(category + '-features'); list.replaceChildren();
    for (const feature of data.features.filter(f => f.category === category)) {
      const row = text('div','', 'feature'), copy = text('div','', 'feature-copy');
      copy.append(text('h4', feature.label),text('p', feature.note));
      const settings = feature.enabled === null ? '状态不一致，需核对' : feature.enabled ? '设置：开启' : '设置：关闭';
      const statuses = {active:'运行中',inactive:'已停止',failed:'运行异常',activating:'正在启动',unknown:'状态未知'};
      copy.append(text('div', settings+' · 服务：'+(statuses[feature.actual] || feature.actual)+(feature.executing?' · 当前任务执行中':''), 'feature-meta'));
      const toggle = text('button','', 'switch'); toggle.type='button'; toggle.setAttribute('role','switch');
      toggle.setAttribute('aria-label', feature.label); toggle.setAttribute('aria-checked', String(feature.enabled === true)); toggle.disabled = busy || !current;
      toggle.addEventListener('click', () => {pending=feature; $('confirm-title').textContent=(feature.enabled?'关闭':'开启')+feature.label+'？'; $('confirm-copy').textContent=feature.note; $('apply-change').disabled=false; $('confirm').showModal();});
      row.append(copy,toggle); list.append(row);
    }
  }
  const names = {online:'QQ 在线',offline:'QQ 离线',initializing:'QQ 初始化中',confirm_on_phone:'等待手机确认',verification_in_progress:'登录验证中',wrong_account:'登录账号不符',unknown:'QQ 状态暂不可用'};
  for (const id of ['smallc','harness']) { const value=data.accounts[id]; $(id+'-status').textContent=names[value]||'状态待检查'; $(id+'-status').className='badge '+(value==='online'?'online':value==='offline'?'offline':''); }
  $('checked').textContent='检查于 '+clock(data.checked_at);
  $('connection').textContent='已连接小家 · 设置来自服务器实际读回'; $('connection').parentElement.classList.remove('failed');
  $('tokens').textContent=data.usage.tokens === null?'暂无数据':Number(data.usage.tokens).toLocaleString();
  $('missing').textContent=data.usage.missing === null?'暂无数据':data.usage.missing;
  const traffic=data.usage.traffic;
  $('traffic').textContent=traffic && traffic.day===data.usage.day && Number.isFinite(traffic.used)?(traffic.used/1048576).toFixed(1)+' MiB':'暂无当日数据';
  $('traffic-note').textContent=traffic?.checked_at?'最近检查 '+clock(typeof traffic.checked_at==='number'?traffic.checked_at*1000:traffic.checked_at)+'；非运营商账单。':'以本地计量为准，非运营商账单。';
  $('usage-day').textContent=data.usage.day+' · 香港时间';
  $('usage-updated').textContent=data.usage.updated?'账本更新于 '+clock(data.usage.updated)+'；只包含已接入计量的调用。':'今天暂未找到用量记录。';
  $('history-list').replaceChildren();
  if (!data.history.length) $('history-list').append(text('p','还没有打理记录。从第一次调整开关开始记录。','loading'));
  for (const item of data.history) { const row=text('div','', 'history-row'), info=text('div',''); info.append(text('div',(item.enabled?'开启':'关闭')+' · '+item.label),text('div',({verified:'已读回确认',failed:'未确认成功，请核对',unconfirmed:'读回不一致，请核对'})[item.result]||'未知结果','result'+(item.result==='verified'?'':' danger'))); row.append(info,text('time',clock(item.at))); $('history-list').append(row); }
}
async function refresh() {
  $('refresh').disabled=true;
  try { const data=await api('state'); current=data; render(data); return true; }
  catch(e) { current=null; $('connection').textContent='连接失败，原有显示可能已过时：'+e.message; $('connection').parentElement.classList.add('failed'); document.querySelectorAll('.switch').forEach(b=>b.disabled=true); toast(e.message); return false; }
  finally { $('refresh').disabled=false; }
}
$('refresh').addEventListener('click',refresh);
$('cancel-change').addEventListener('click',()=>$('confirm').close());
document.querySelectorAll('dialog .close').forEach(button=>button.addEventListener('click',()=>button.closest('dialog').close()));
$('apply-change').addEventListener('click',async()=>{
  if (!pending || !current || busy) return;
  busy=true; $('apply-change').disabled=true;
  try { await api('change',{id:pending.id,enabled:pending.enabled !== true,revision:current.revision}); $('confirm').close(); toast('设置已保存，服务器已读回确认。'); }
  catch(e) { $('confirm').close(); toast(e.message); }
  finally { busy=false; pending=null; await refresh(); }
});
$('login').addEventListener('click',()=>{ $('qr').hidden=true; $('qr').removeAttribute('src'); $('login-message').textContent='在线时保持当前登录；仅离线等待扫码时获取新码。'; $('login-dialog').showModal(); });
async function login(mode) {
  if (busy || !current) return;
  busy=true; $('prepare-login').disabled=$('verify-login').disabled=true; $('qr').hidden=true; $('qr').removeAttribute('src'); $('login-message').textContent='正在检查，请稍候…';
  try { const data=await api('login',{mode}); const messages={online:'小 c 已在线，账号身份已核对。',scan_qr:'请用小 c 账号的手机 QQ 扫码，并完成手机确认。二维码仅本次有效。',confirm_on_phone:'请完成手机上已有的确认，不需要重新扫码。',verification_in_progress:'验证正在进行，请稍后检查。',initializing:'账号正在初始化，请稍后检查。',wrong_account:'登录账号不符，请先核对手机上的账号。',qr_pending:'二维码尚未准备好，请稍后获取。',refresh_failed:'新二维码获取失败，请稍后重试。',offline:'目前离线，可以获取新二维码。'}; $('login-message').textContent=messages[data.status]||'暂时无法确认登录状态，请稍后检查。'; if(data.status==='scan_qr'&&data.png_base64){$('qr').src='data:image/png;base64,'+data.png_base64;$('qr').hidden=false;setTimeout(()=>{$('qr').hidden=true;$('qr').removeAttribute('src')},60000);} }
  catch(e){$('login-message').textContent=e.message;}
  finally{busy=false;$('prepare-login').disabled=$('verify-login').disabled=false;await refresh();}
}
$('prepare-login').addEventListener('click',()=>login('prepare')); $('verify-login').addEventListener('click',()=>login('verify'));
$('login-dialog').addEventListener('close',()=>{$('qr').hidden=true;$('qr').removeAttribute('src')});
document.querySelectorAll('nav a').forEach(a=>a.addEventListener('click',()=>{document.querySelectorAll('nav a').forEach(n=>n.classList.toggle('active',n===a))}));
$('logout').addEventListener('click',async e=>{e.preventDefault();try{const response=await fetch('/auth/csrf',{credentials:'same-origin',cache:'no-store'});if(!response.ok)throw Error('登录已失效');const data=await response.json();const form=document.createElement('form');form.method='post';form.action='/auth/logout';const input=document.createElement('input');input.type='hidden';input.name='csrf';input.value=data.csrf;form.append(input);document.body.append(form);form.submit();}catch{location.href='/auth/login?returnTo=%2Fhome%2F';}});
$('greeting').textContent=Number(new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Hong_Kong',hour:'2-digit',hour12:false}).format(new Date()))<12?'早安，欢迎回家':'欢迎回家，歇一会儿吧';
refresh(); setInterval(()=>{if(!document.hidden&&!busy&&!$('confirm').open&&!$('login-dialog').open)refresh()},60000);
