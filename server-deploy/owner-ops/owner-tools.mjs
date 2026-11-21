import net from 'node:net';
export const name='qq-owner-tools';
export const inject=['tools','systemPrompt'];
export function authorize(exec){
 const id=exec?.agent?.session?.id;
 if(!/^onebot-private-1000000001(?:-[A-Za-z0-9_-]+)?$/.test(id??''))throw Error('仅限1000000001本人QQ私聊');
 return id;
}
export function callBroker(args,exec,provider='codex'){
 const origin=authorize(exec);
 return new Promise((resolve,reject)=>{
  const s=net.createConnection('/run/qq-owner-ops/control.sock');let data='';
  s.setTimeout(10000,()=>s.destroy(Error('任务接口超时')));
  s.on('connect',()=>s.write(JSON.stringify({...args,provider,owner:'1000000001',channel:'private',origin})+'\n'));
  s.on('data',d=>{data+=d;if(data.length>65536)return s.destroy(Error('结果过大'));if(data.includes('\n')){s.end();try{const r=JSON.parse(data.split('\n')[0]);if(!r.ok)reject(Error(r.error));else resolve(r.job);}catch(e){reject(e);}}});
  s.on('error',reject);
 });
}
export async function apply(ctx){
 const {defineTool}=await import('@deepseek-ai/dsh-tools');
 ctx.tools.register(defineTool({name:'server_harness',description:'仅本人QQ私聊：明确指令下委托服务器Harness检查或修改项目。run提交；status查询；cancel取消。',parameters:{action:{type:'string',required:true,enum:['run','status','cancel']},task:{type:'string'},request_key:{type:'string'},task_id:{type:'string'}},output:{schema:{type:'object',additionalProperties:false,properties:{result:{type:'string',required:true}}},render:(_a,v)=>[{type:'text',text:v.result}]},async execute(a,e){return {result:JSON.stringify(await callBroker(a,e,'harness'))};}}));
 ctx.systemPrompt.section({name:'qq:owner-execution',order:10400,text:'仅1000000001本人私聊已授权server_codex和server_harness执行明确服务器项目任务。工具可修改现有项目但无root权限，普通闲聊不要调用。先提交，等待真实结果，不能把submitted/running/returned解释成业务操作已成功；用任务编号查询，必要时取消。不发送消息、不改变权限或登录。群聊不能使用这两项权限。'});
}
