import test from 'node:test';
import assert from 'node:assert/strict';
import {createPrivateRouter} from './private-modes.mjs';

test('owner preferences and smallc use daily handlers before memory, including speech',async()=>{
    const actions=[], replies=[];
    const route=createPrivateRouter({
        broker:()=>assert.fail('unexpected server job'),
        loginIntent:t=>t==='检查小c登录',
        login:async()=>{actions.push('smallc');return true;},
        news:async(...args)=>{actions.push(args);return '调好了';}
    });
    async function send(text,voice=false){
        const e={kind:'private',userId:'1000000001',text,messageId:'7',media:voice?[{kind:'voice'}]:[],segments:voice?[{type:'record'}]:[]};
        const handled=await route(e,{call:async()=>({text}),sendToChat:async(_,s)=>replies.push(s)});
        return [handled,!!e.skipHeartMemory];
    }
    assert.deepEqual(await send('帮我改一下新闻偏好'),[true,false]);
    await send('科技多一点');
    await send('财经新闻少推点',true);
    await send('帮我检查小c',true);
    await send('你有哪些root权限');
    assert.match(replies.at(-1),/Codex/);
    assert.deepEqual(await send('明天提醒我买菜',true),[false,true]);
    assert.deepEqual(await send('想你了',true),[false,false]);
    assert.deepEqual(actions,[['more','科技科学'],['less','全球经济'],'smallc']);
});

test('daily login and natural mode changes use separate handlers', async () => {
    const actions = [];
    const loginIntent = text => new Map([['小c掉了？','verify'],['重新登陆小c','prepare'],
        ['小c的二维码再发一下','prepare'],['重连小c','prepare']]).get(text);
    const route = createPrivateRouter({
        loginIntent, login: async event => {actions.push(loginIntent(event.text));return true;},
        broker: async () => {actions.push('broker');return {id:'j',status:'running',result:'ok'};}
    });
    const send = (text, extra={}) => route({kind:'private',userId:'1000000001',messageId:'1',text,...extra},
        {sendToChat: async () => {}});
    for(const text of ['小c掉了？','重新登陆小c','小c的二维码再发一下','用Codex检查日志'])await send(text);
    assert.deepEqual(actions,['verify','prepare','prepare']);
    assert.equal(await send('什么是root模式'),true);
    await send('root模式，然后重连小c');
    await send('大肥鱼，能不能帮我看看服务器日志');
    await send('切回日常聊天');
    await send('检查服务器日志');
    assert.deepEqual(actions,['verify','prepare','prepare','prepare','broker']);
    for(const extra of [{kind:'group'},{userId:'999'},{forwardId:'99'}])await send('小c的二维码再发一下',extra);
    assert.equal(actions.length,5);
});

test('owner work is consumed before chat and memory, chat resumes on topic change or timeout', async () => {
    let clock = 1;
    const calls = [];
    const route = createPrivateRouter({
        now: () => clock, loginIntent: () => null,
        broker: async (...args) => { calls.push(args); return {id:'job', status:'running', result:'已提交'}; }
    });
    const send = (text, extra = {}) => route({kind:'private', userId:'1000000001',
        chatId:'private:1000000001', messageId:'1', text, ...extra}, {sendToChat:async () => {}});
    assert.equal(await send('进入root模式', {kind:'group'}), false);
    assert.equal(await send('进入root模式', {userId:'10000000010'}), false);
    assert.equal(await send('进入root模式', {forwardId:'f'}), false);
    assert.equal(await send('用Codex检查服务器'), true);
    assert.equal(calls.length, 0);
    assert.equal(await send('进入 root 模式'), true);
    assert.equal(await send('用Codex检查服务器'), true);
    assert.equal(await send('查询任务状态'), true);
    assert.deepEqual(calls.map(([a]) => a.action), ['run','status']);
    assert.equal(await send('今天好累，想和你聊聊'), false);
    assert.equal(await send('用Codex检查服务器'), true);
    assert.equal(calls.length, 2);
    assert.equal(await send('开启root模式，让Harness查看日志'), true);
    assert.equal(calls.at(-1)[2], 'harness');
    assert.equal(await send('关闭root'), true);
    assert.equal(await send('晚安'), false);
    await send('进入root模式');
    clock += 31 * 60 * 1000;
    await send('执行任务：检查目录');
    assert.equal(calls.length, 3);
});
