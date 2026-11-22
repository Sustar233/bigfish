import {readFile as readOffer, unlink as clearOffer} from 'node:fs/promises';
import {goldReply} from './gold-controls.mjs';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
const exec = promisify(execFile);
const owner = '1000000001';
const capabilities = '可以呀。你说 root，我就知道你想让我操作服务器。我能查磁盘、进程和服务日志，也能让服务器上的 Codex 或 Harness 修改已授权项目、跑测试，再按任务编号查结果或取消任务。';
const topics = [['国际政治',/国际政治|外交/],['战争安全',/战争|军事|战事/],['全球经济',/经济|财经|金融/],['灾害卫生',/灾害|卫生|疫情/],['科技科学',/科技|科学|人工智能/],['中国及周边',/中国及周边|中国周边/]];
async function newsReply(action,topic) {
    const {stdout} = await exec('/usr/bin/python3',['-B','/home/ubuntu/qq-dsh/codex-integration/daily_news.py',action,topic],{timeout:5000});
    return stdout.trim();
}
function preference(text) {
    const more = /多(?:给我)?(?:推|发|看|来)|多一?点|增加|优先推/.test(text);
    const less = /少(?:给我)?(?:推|发|看|来)|少一?点|减少|降低/.test(text);
    const normal = /恢复|调回|改回/.test(text) && /默认|正常|原来/.test(text);
    const matches = topics.filter(([,pattern])=>pattern.test(text));
    if (!/新闻|快报|简报/.test(text) && !(matches.length && /[多少](?:给我)?推/.test(text))) return null;
    if (/新闻偏好|新闻设置/.test(text) && !more && !less && !normal)
        return /改|调|设一下/.test(text) ? ['ask'] : ['show',''];
    if (!more && !less && !normal) return null;
    if (matches.length!==1 || Number(more)+Number(less)+Number(normal)!==1 || /别|不要|不想|如果|假设|比如|[“「]|怎么说|为什么/.test(text)) return ['ask'];
    return [normal?'normal':more?'more':'less',matches[0][0]];
}
const idleLimit = 30 * 60 * 1000;
const mode = String.raw`(?:root\s*模式|工作模式|运维模式|服务器管理模式)`;
const enter = new RegExp(String.raw`^(?:(?:大肥鱼|肥鱼)[，,\s]*)?(?:(?:请|帮我|麻烦你|现在|先)\s*)*(?:(?:进入|开启|打开|切换到|切到|切换成|进|开)\s*(?:一下\s*)?(?:${mode}|root)|${mode})(?:吧|一下)?(?:[。！!\s]*$|[，,:：。\n]\s*(?:然后|接着|顺便)?\s*(.+)$)`, 'isu');
const leave = new RegExp(String.raw`^(?:请|帮我)?(?:(?:关闭|退出|结束|关掉|关了|退出一下)\s*(?:${mode}|root)|(?:回到|切回|恢复)(?:日常|普通|正常)(?:聊天|模式)?|不聊工作了)(?:吧|一下)?[。！!\s]*$`, 'iu');
const taskWords = /服务器|codex|harness|服务状态|部署|进程|日志|磁盘|仓库|脚本|测试用例|配置文件|数据库|工作目录|README|运行测试|重启服务|修复.{0,10}(?:报错|故障)|执行命令/iu;
const instruction = /^(?:\/codex\b|\/harness\b|(?:请|帮我|麻烦你?)?(?:用|让|调用|委托|运行|检查|查看|查|看看|部署|重启|排查|修改|修复|执行|把|把握|在|给|清理|更新|列出|分析|读取|测试|打开|停止|启动|编写))/iu;
const explicitTask = /^(?:执行任务|服务器任务|执行指令)[：:\s]+(.+)/su;
const management = /^(?:帮我|请)?(查询|查看|取消)(?:(?:一下)?(?:上个|上一个|该|这个|最近的)?任务(?:状态|结果|进度)?)?\s*([a-f\d-]{36})?[。！!\s]*$/iu;

// One instance per live adapter. A process restart always starts in chat mode.
export function createPrivateRouter({ broker, loginIntent, login, consumeOffer = consumeLoginOffer, news = newsReply, now = Date.now }) {
    let expires = 0;
    let lastJob;
    let preferenceUntil = 0;
    return async function route(event, ctx) {
        if (event.kind !== 'private' || String(event.userId) !== owner) return false;
        const reply = async text => { await ctx.sendToChat(event.chatId, text); return true; };
        let plain = event.replyId == null && event.forwardId == null &&
            !event.media?.length && (!event.segments || event.segments.every(s => s.type === 'text'));
        let raw = (event.text || '').trim();
        if (!plain && !event.replyId && !event.forwardId && event.messageId && event.media?.length===1 &&
            event.media[0].kind==='voice' && event.segments?.every(s=>s.type==='record')) {
            try {event.voiceTranscript = (await ctx.call('fetch_ptt_text',{message_id:event.messageId})).text?.trim();} catch {}
            if (event.voiceTranscript) {raw=event.voiceTranscript;plain=true;}
        }
        const directAnswer = plain || (event.replyId != null && event.forwardId == null &&
            !event.media?.length && event.segments?.every(s=>['reply','text'].includes(s.type)));
        if (directAnswer && await consumeOffer(raw)) {
            if (agreesToLogin(raw)) return await login({...event,text:'重登小c'},ctx);
            if (/^(?:不用|不要|先不|不了|取消|算了)/u.test(raw)) return reply('好，这次先不重登。');
        }
        const opening = plain && (raw.match(enter) || (/^root[。！!\s]*$/iu.test(raw) && [raw]));
        const wasAskingPreference=now()<preferenceUntil;
        preferenceUntil=0;
        if (plain && leave.test(raw)) {
            expires = 0;
            return reply('已回到日常聊天。');
        }
        if (opening) expires = now() + idleLimit;
        const active = now() < expires;
        if (!plain) {
            expires = 0;
            if (active) return reply('已退出工作模式。请重新发送想聊的内容。');
            return false;
        }
        const text = opening ? (opening[1] || '').trim() : raw;
        if (/^(?:大肥鱼[，, ]*)?你(?:现在|都|平时)?(?:能做什么|能做哪些事|会做什么|能干什么)[呢呀啊？?。]*$/u.test(text))
            return reply('平时可以直接让我调新闻偏好、看小c在不在线、拿扫码登录码、设提醒或查今日天气和精读。'+capabilities);
        if (opening && !text) return reply('已进入工作模式。'+capabilities);
        if (/root|服务器工作模式/iu.test(text) && /权限|能做|做什么|能干|干什么|可以做|能不能|是什么|什么是|什么意思|会什么|有什么用/iu.test(text))
            return reply(capabilities+(active?' 现在就在工作模式。':' 想开始就说「进入 root 模式」。'));
        const pref = preference(text) || (wasAskingPreference && topics.some(([,p])=>p.test(text)) && preference('新闻'+text));
        if (pref) {
            if (pref[0]==='ask') {
                preferenceUntil=now()+120000;
                return reply('想怎么调？比如跟我说「科技多一点」或「财经恢复正常」。');
            }
            try {return await reply(await news(...pref));} catch {return reply('这次没能确认新闻偏好，你可以让我再查一下。');}
        }
        const gold = await goldReply(text);
        if (gold !== null) return reply(gold);
        const command = text.match(explicitTask);
        const manage = text.match(management);
        const checkSmallc = /(?:查查|查一下|检查|看看|瞅瞅|瞧瞧|确认一下)\s*(?:一下)?\s*小\s*c(?:的)?(?:状态|情况|还在不在)?[。？！!?]*$/iu.test(text) && !/别|不|如果|比如|[“「]/u.test(text.replace('在不在',''));
        const loginText = checkSmallc ? '检查小c登录' : text;
        if (loginIntent(loginText) && await login({...event, text:loginText}, ctx)) return true;
        if (/提醒我|帮我.{0,4}提醒|(?:查看|取消|修改).{0,5}提醒|(?:今天|明天).{0,8}(?:天气|带伞)|(?:今天|今日).{0,6}(?:新闻|精读)/u.test(text)) event.skipHeartMemory=true;
        const request = text.replace(/^(?:(?:大肥鱼|肥鱼|能不能|可以|能否|可否|麻烦|请|帮忙|帮我|你|顺便)[，,\s]*)+/u,'');
        const work = command || (instruction.test(request) && taskWords.test(text)) ||
            (taskWords.test(request) && /(?:帮我|麻烦|能不能|能否).{0,10}(?:查|看|跑|改|修|测)|(?:状态|日志|进度|结果)(?:怎么样|如何|呢)[？?。]*$/u.test(text)) ||
            /^(?:codex|harness)\s*[：:,，]\s*\S/iu.test(text);
        if (!active && (work || (manage && /任务|[a-f\d-]{36}/iu.test(text)))) {
            return reply('请先说「进入root模式」，再交代服务器任务。');
        }
        if (!active) return false;
        if (!opening && !work && !manage && /^(?:继续执行|再试一次|重新执行|继续检查|结果呢|进度呢)[。？?！!]*$/u.test(text)) {
            if (/结果|进度/u.test(text) && lastJob) {
                const job = await broker({action:'status',task_id:lastJob}, {agent:{session:{id:'onebot-private-' + owner}}}, 'codex');
                return reply('任务 ' + job.id + '（' + job.status + '）\n' + job.result);
            }
            return reply('请用「执行任务：具体内容」说明这次要做的操作。');
        }
        if (!opening && !work && !manage) {
            expires = 0;
            return false;
        }
        expires = now() + idleLimit;
        const provider = /harness/iu.test(text) ? 'harness' : 'codex';
        let args;
        if (manage) {
            const id = manage[2] || lastJob;
            if (!id) return reply('请附上要查询或取消的任务编号。');
            args = {action: manage[1] === '取消' ? 'cancel' : 'status', task_id: id};
        } else {
            if (!event.messageId) return reply('这条消息缺少 QQ 消息编号，请重新发送任务。');
            args = {action: 'run', task: command?.[1] || text, request_key: 'root-mode-' + event.messageId};
        }
        let job;
        try {
            job = await broker(args, {agent: {session: {id: 'onebot-private-' + owner}}}, provider);
        } catch (error) {
            return reply('任务服务返回：' + error.message);
        }
        lastJob = job.id;
        return reply('任务 ' + job.id + '（' + job.status + '）\n' + job.result);
    };
}

const offerFile='/home/ubuntu/qq-codex/bridge/.private/records/smallc-relogin-offer';
function agreesToLogin(text) {
    return /^(?:嗯+|好[的啊呀嘞吧]?|可以[啊呀]?|行[啊呀]?|同意|是的|要|确认|重登吧|发吧|发码吧|发给我吧|yes|ok)[。！!，,\s]*(?:(?:帮我)?(?:重登|重新登录|发码|发二维码)(?:吧|一下)?[。！!]*)?$/iu.test(text.trim());
}
export async function consumeLoginOffer(text,path=offerFile,now=Date.now()) {
    try {
        const created=Number(await readOffer(path,'utf8'))*1000;
        await clearOffer(path);
        return now>=created && now-created<24*3600000;
    } catch (error) {
        if (error.code==='ENOENT') return false;
        throw error;
    }
}
