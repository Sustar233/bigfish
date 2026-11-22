import { readFile } from 'node:fs/promises';
import { spawn } from 'node:child_process';

async function identity() {
    const config = JSON.parse(await readFile('/home/ubuntu/qq-dsh/napcat-runtime/.private/bridge-config.json','utf8'));
    return {owner:String(config.owner_qq), bot:String(config.bot_qq)};
}
async function query(text) {
    return await new Promise((resolve,reject)=>{
        const child=spawn('/usr/bin/python3',['/home/ubuntu/qq-codex/bridge/standby.py','--actor','harness'],{stdio:['pipe','pipe','pipe']});
        let output='';const timer=setTimeout(()=>{child.kill('SIGTERM');reject(Error('standby_timeout'));},10000);
        child.stdout.setEncoding('utf8');child.stdout.on('data',part=>{output+=part;if(output.length>20000){child.kill();reject(Error('output_limit'));}});
        child.stderr.resume();child.on('error',error=>{clearTimeout(timer);reject(error);});
        child.on('close',code=>{clearTimeout(timer);try{if(code!==0)throw Error('failed');resolve(JSON.parse(output));}catch(error){reject(error);}});
        child.stdin.on('error',()=>{});child.stdin.end(JSON.stringify({text}));
    });
}
export async function standbyPrivate(inbound,selfId,deps={}) {
    if(inbound.kind!=='private'||inbound.messageId===undefined)return null;
    const ids=await (deps.identity??identity)();
    if(String(inbound.userId)!==ids.owner||String(selfId)!==ids.bot)return null;
    try{
        const result=await (deps.query??query)(String(inbound.text??''));
        if(result.active===false)return null;
        if(result.active===true&&typeof result.reply==='string')return result.reply;
        throw Error('invalid_state');
    }catch{return '现在先由大肥鱼值班，功能先不开，等小c回来再说吧。';}
}
