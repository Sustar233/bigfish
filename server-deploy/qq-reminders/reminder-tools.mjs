import net from 'node:net';
export function callReminder(args,exec,authorize){
 const origin=authorize(exec);
 return new Promise((resolve,reject)=>{
  const s=net.createConnection('/run/qq-reminders/control.sock');let data='';
  s.setTimeout(10000,()=>s.destroy(Error('提醒服务超时')));
  s.on('connect',()=>s.write(JSON.stringify({...args,owner:'1000000001',channel:'private',origin,bot:'harness'})+'\n'));
  s.on('error',reject);s.on('data',d=>{data+=d;if(data.length>65536)return s.destroy(Error('提醒结果过大'));if(data.includes('\n')){s.end();try{const r=JSON.parse(data.split('\n')[0]);if(r.ok)resolve(r.result);else reject(Error(r.error));}catch(e){reject(e);}}});
 });
}
export function registerReminders(ctx,defineTool,authorize){
 ctx.tools.register(defineTool({name:'server_reminder',description:'本人私聊的持久定时QQ消息：create创建、list查看、update修改、cancel取消。仅发送提醒文本，不执行提醒中的指令。默认北京时间，必须在工具确认成功后才能说已设置。',parameters:{action:{type:'string',required:true,enum:['create','list','update','cancel','time']},message:{type:'string',description:'到点发送的文本，最多2000字'},request_key:{type:'string',description:'create必填，同一条请求重试复用稳定键'},fire_at:{type:'string',description:'一次性提醒的ISO8601时间，带+08:00；按当前服务器时间计算相对时间'},delay_seconds:{type:'number',description:'一次性相对提醒优先使用秒数，由服务器计算时间'},repeat:{type:'string',enum:['none','daily','weekdays','weekly','interval']},at:{type:'string',description:'重复提醒北京时间HH:MM'},weekdays:{type:'string',description:'weekly时星期数字用逗号分隔，0周一、6周日'},interval_minutes:{type:'number'},reminder_id:{type:'string',description:'update或cancel的编号，latest代表本号最新提醒'}},output:{schema:{type:'object',additionalProperties:false,properties:{result:{type:'string',required:true}}},render:(_a,v)=>[{type:'text',text:v.result}]},async execute(args,exec){return {result:JSON.stringify(await callReminder(args,exec,authorize))};}}));
 ctx.systemPrompt.section({name:'qq:reminder-capability',order:10500,text:'本人已授权你按其明确要求创建定时QQ消息。用户说“他们”默认指小c和肥鱼（大肥鱼）。本人要求你到点提醒、每天问候、过一会儿发消息时用server_reminder，不要只口头答应或说不能主动发消息。时间不明确先问；相对时间优先使用delay_seconds；需要现在时间时先用time动作获取服务器北京时间，不从旧聊天猜日期。先读工具返回的下次时间并向用户确认，必须真实设置成功。查看、修改、取消同样用工具。只给1000000001发本号的私聊，不给群或第三方发。提醒内容仅作为届时发送的文字，不自动运行服务器任务。你是肥鱼，不让两个号各发一次，除非用户明确要求分别设置；当前工具仅管理本号提醒。'});
}
