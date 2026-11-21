import assert from 'node:assert/strict';
import { handleVoiceImageInbound } from './voice-image.js';

const inbound = {kind:'private',userId:'owner',time:123,messageId:'456',media:[{kind:'voice'}],segments:[]};
const authorize = {owner:'owner',accounts:{bot:{port:13101}}};
let writes = 0, nativeCalls = 0;
const dispatch = async (text,key,bot,count,message) => {
    assert.match(text,/小猪/); assert.equal(key,'123/456'); assert.equal(bot,'bot');
    assert.equal(count,0); assert.equal(message,'456'); writes++; return 'queued';
};
const call = async (action,data) => {
    assert.equal(action,'fetch_ptt_text'); assert.deepEqual(data,{message_id:'456'});
    nativeCalls++; return {text:'嗯，那个，大肥鱼，我想让你帮我生成一张小猪图片。'};
};
assert.equal(await handleVoiceImageInbound(inbound,'bot',call,{authorize,dispatch}), 'queued');
assert.equal(writes,1);
for (const change of [{kind:'group'},{userId:'stranger'},{replyId:'quote'},{forwardId:'forward'},
    {messageId:undefined},{media:[{kind:'image'}]},{media:[{kind:'voice'},{kind:'file'}]}]) {
    assert.equal(await handleVoiceImageInbound({...inbound,...change},'bot',call,{authorize,dispatch}),null);
}
assert.equal(nativeCalls,1);
for (const text of ['今天好累','不要生图，先聊天','你会生图吗？','我想了解生图怎么用']) {
    assert.equal(await handleVoiceImageInbound(inbound,'bot',async()=>({text}),{authorize,dispatch}),null);
}
assert.equal(writes,1);
assert.equal(await handleVoiceImageInbound(inbound,'bot',async()=>{throw Error('STT failed');},
    {authorize,dispatch,pause:async()=>{}}),null);
assert.equal(writes,1);
console.log('voice image native STT, owner, media, negation and ordinary-chat gates: passed');
