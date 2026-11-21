import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {readFile} from 'node:fs/promises';
const run=promisify(execFile);
const OWNER='1000000001',BOT='1000000003';
let busy=false;
let lastRefresh=0;
export function loginIntent(input,{recent=false}={}){
 const text=String(input??'').normalize('NFKC').toLowerCase().replace(/\s+/g,'');
 if(!text||text.length>300)return null;
 if(/不要|不用|先别|别帮|别重|暂时不|取消|不需要|什么意思|举例|比如|例如|别人说|引用|教程/.test(text)||/^(?:请|你)?别/.test(text))return null;
 const named=/小c/.test(text);
 const login=/重登|登录|重新登|登回|登上|二维码|登录码|扫码|扫好|扫完|扫了|过期/.test(text);
 if(!named&&/付款|支付|收款|微信|支付宝|别的账号/.test(text))return null;
 if(!named&&/(?:你|肥鱼|harness).{0,8}(?:重登|登录|掉线|离线)/.test(text))return login?'clarify':null;
 if(/已扫码|扫(?:好|完|过|了)|扫码.{0,8}(?:完成|成功|确认)|手机.{0,8}(?:已|点|完成).{0,4}确认|已经确认|确认好了/.test(text)){
  return named||recent||/^(?:我)?(?:已经|已)?(?:扫好了|扫完了|扫码完成|已扫码)[。！!，,]*$/.test(text)?'verify':null;
 }
 const expired=/(?:二维码|登录码|这(?:个|张)?码|码).{0,6}(?:过期|失效|超时|不行|不能用)|(?:过期|失效).{0,4}(?:二维码|登录码)/.test(text);
 const qrRequest=/(?:给|发|换|刷新|再来|重发|取|拿).{0,10}(?:二维码|登录码|新码)/.test(text);
 if(expired||qrRequest)return named||recent||/二维码|登录码/.test(text)?'prepare':'clarify';
 if(/重登|重新(?:登|登录)|登(?:回|上)(?:去|来|线)?/.test(text))return 'prepare';
 const offline=/掉线|又掉了|不在线|离线|登不上|没回复|不理我|没反应/.test(text);
 if(named&&offline)return /帮|弄一下|处理|修|重新|恢复/.test(text)?'prepare':'verify';
 if(named&&/在不在线|上线了吗|恢复了吗|登录状态|检查.{0,4}登录|确认.{0,4}登录/.test(text))return 'verify';
 if(named&&/登录|扫码/.test(text)&&/帮|请|麻烦|能不能|可以|想|要/.test(text))return 'prepare';
 if(recent&&/^(?:我)?(?:好了|好啦|弄好了|确认了|搞定了)[。！!]*$/.test(text))return 'verify';
 return null;
}
async function helper(mode){
 const {stdout}=await run('/usr/bin/python3',['-B','/home/ubuntu/qq-dsh/smallc-login/smallc_login.py','--mode',mode,'--wait',mode==='verify'?'15':'15'],{timeout:45000,maxBuffer:1500000});
 return JSON.parse(stdout);
}
export function loginText(result){
 switch(result.status){
 case 'online':return result.expected_account===true?'小c已经在线啦，不用再扫码。':'账号身份还没核对上，先不继续登录。';
 case 'wrong_account':return '当前登录的不是预期的小c账号，先停在这里，请检查手机QQ账号。';
 case 'confirm_on_phone':return '手机上还需要确认登录，先完成当前确认，不用重新扫码。';
 case 'verification_in_progress':return '小c正在验证登录，先完成手机上的现有验证。好了跟我说一声，我再查。';
 case 'initializing':return '登录正在初始化，先不刷新。稍后问我小c回来了没就行。';
 case 'qr_pending':return '新二维码还没生成好，稍后再让我取一次就行。';
 case 'offline':return '小c还没恢复在线。需要重新登录的话，直接跟我说就行。';
 default:return '这次没取到小c的登录状态，请稍后再试。我没有重启QQ或重试密码。';
 }
}
export async function handleSmallcLogin(inbound,selfId,call,deps={}){
 if(inbound?.kind!=='private'||String(inbound.userId)!==OWNER||String(selfId)!==BOT)return false;
 const text=String(inbound.text??'').trim();
 const now=(deps.now??Date.now)();
 const intent=loginIntent(text,{recent:lastRefresh>0&&now-lastRefresh<10*60*1000});
 if(!intent)return false;
 const send=async(message)=>{
  const result=await call('send_private_msg',{user_id:Number(OWNER),message,auto_escape:true});
  if(!result?.message_id)throw Error('send_uncertain');
 };
 if(busy){await send([{type:'text',data:{text:'正在检查小c登录，先等这次结果，别重复刷新。'}}]);return true;}
 if(intent==='clarify'){await send([{type:'text',data:{text:'你是想给小c重新登录吗？我这里可以帮它取登录码。'}}]);return true;}
 busy=true;
 try{
  // A recent refresh is only inspected, preserving the QR already on the phone.
  const mode=intent==='prepare'&&(now-lastRefresh>10000||/过期|失效|换|刷新/.test(text))?'prepare':'verify';
  let result;
  try{result=await(deps.helper??helper)(mode);}catch{result={status:'unavailable'};}
  if(result.status==='scan_qr'){
   if(mode!=='prepare')throw Error('unexpected_qr');
   const encoded=result.png_base64;
   if(typeof encoded!=='string'||encoded.length>1400000)throw Error('invalid_qr');
   const png=Buffer.from(encoded,'base64');
   if(png.length<8||png.subarray(0,8).toString('hex')!=='89504e470d0a1a0a'||!(result.age_seconds>=0&&result.age_seconds<=20))throw Error('invalid_qr');
   lastRefresh=now;
   await send([{type:'text',data:{text:'小c的新登录码来了。用小c账号1000000002的手机QQ扫码并确认，扫好跟我说一声，我再核对。'}},{type:'image',data:{file:'base64://'+encoded}}]);
  }else await send([{type:'text',data:{text:loginText(result)}}]);
 }finally{busy=false;}
 return true;
}
async function ownerCall(action,data){
 const c=JSON.parse(await readFile('/home/ubuntu/qq-dsh/napcat-runtime/.private/bridge-config.json','utf8'));
 if(String(c.owner_qq)!==OWNER||String(c.bot_qq)!==BOT||c.onebot_url!=='http://127.0.0.1:13101')throw Error('account_mismatch');
 const response=await fetch(c.onebot_url+'/'+action,{method:'POST',signal:AbortSignal.timeout(15000),headers:{Authorization:'Bearer '+c.onebot_token,'Content-Type':'application/json'},body:JSON.stringify(data)});
 const r=await response.json();if(!response.ok||r.status!=='ok'||r.retcode!==0)throw Error('send_uncertain');return r.data;
}
export function registerSmallcLogin(ctx,defineTool,authorize,deps={}){
 ctx.tools.register(defineTool({name:'smallc_login',description:'本人私聊明确要求帮小c重登、拿新登录码或检查扫码结果时使用。prepare按当前状态取码，verify只查登录。无需用户说固定口令。只处理小c，不能重登肥鱼或其他账号。否定、引用、讨论教程不执行。',parameters:{action:{type:'string',required:true,enum:['prepare','verify']}},output:{schema:{type:'object',additionalProperties:false,properties:{result:{type:'string',required:true}}},render:(_a,v)=>[{type:'text',text:v.result}]},async execute(args,exec){
  authorize(exec);if(!['prepare','verify'].includes(args.action))throw Error('invalid_action');
  await handleSmallcLogin({kind:'private',userId:OWNER,text:args.action==='prepare'?'重登小c':'检查小c登录'},BOT,deps.call??ownerCall,deps);
  return {result:'实际登录检查结果已经直接发给本人。不要重复发送或声称账号已登录，除非检查明确确认。'};
 }}));
 ctx.systemPrompt.section({name:'qq:smallc-natural-login',order:10510,text:'用户不需要记固定口令。本人以自然语言明确请求重新登录小c、获取新登录二维码、检查扫码是否完成时，可调用smallc_login；prepare取码，verify只查状态。可以结合本轮上下文理解同义表达；含糊、否定、引用或可能指另一个账号时先问清楚。二维码由程序直接私聊发送，不让用户读出或粘贴登录凭据。只有实际online并核对身份成功才能说小c已恢复。'});
}
