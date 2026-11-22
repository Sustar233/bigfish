import {execFile} from 'node:child_process';
import {readFile} from 'node:fs/promises';
import {existsSync,readFileSync} from 'node:fs';

const bridge='/home/ubuntu/qq-codex/bridge/';
const localPolicy=new URL('./reply-policy.json',import.meta.url);
const policy=JSON.parse(readFileSync(existsSync(localPolicy)?localPolicy:bridge+'reply-policy.json','utf8'));
const voiceTurns=new Set();
export function rememberVoice(turn) {
    if (voiceTurns.size>=128) voiceTurns.delete(voiceTurns.values().next().value);
    voiceTurns.add(turn);
}
export function takeVoice(turn) { return voiceTurns.delete(turn); }
function python(file,text,timeout,args=[]) {
    return new Promise((resolve,reject)=>{
        const p=execFile('/usr/bin/python3',['-B',bridge+file,...args],{encoding:'buffer',timeout,maxBuffer:2*1024*1024},
            (err,data)=>err?reject(err):resolve(data));
        p.stdin.on('error',()=>{});p.stdin.end(text);
    });
}
export async function emotionalContext(inbound,selfId,transcript) {
    if (inbound.skipHeartMemory || inbound.kind!=='private' || inbound.replyId!=null || inbound.forwardId!=null) return '';
    try {
        const c=JSON.parse(await readFile('/home/ubuntu/qq-dsh/napcat-runtime/.private/bridge-config.json','utf8'));
        if (String(inbound.userId)!==String(c.owner_qq)||String(selfId)!==String(c.bot_qq)) return '';
        const voice=inbound.media?.some(ref=>ref.kind==='voice');
        const text=voice ? (typeof transcript==='string' ? transcript.trim() : '') : inbound.text;
        if (!text) return '';
        const notes=JSON.parse(await python('heart_memory.py',text,3500,voice?['--voice-text']:[]));
        if (notes[0]?.操作结果) return {feedback:notes[0].操作结果};
        return notes.length?'\n过去此人亲口说过的情感片段，仅供参考，按日期理解：'+JSON.stringify(notes):'';
    } catch { return ''; }
}
export async function voiceFile(text) {
    return 'base64://'+(await python('cosyvoice_feiyu.py',text,32000)).toString('base64');
}
export function bubbles(text) {
    const chars=Array.from(text);
    if(chars.length<policy.split_at_characters||policy.keep_whole_if_contains.some(s=>text.includes(s))) return [text];
    const ends=[...text.matchAll(new RegExp(policy.break_pattern,'gu'))].map(m=>m.index+m[0].length).filter(i=>i<text.length);
    const mid=chars.length/2;
    const distance=i=>Math.abs(Array.from(text.slice(0,i)).length-mid);
    const cut=ends.length?ends.reduce((a,b)=>distance(a)<=distance(b)?a:b):chars.slice(0,Math.floor(mid)).join('').length;
    return [text.slice(0,cut).trim(),text.slice(cut).trim()].filter(Boolean);
}
