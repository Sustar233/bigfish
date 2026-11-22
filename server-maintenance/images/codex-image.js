// Owner-only native Codex image job client for the DeepSeek OneBot adapter.
import { readFile } from 'node:fs/promises';
const ROOT = '/home/ubuntu/server-maintenance/images/.private/';
const RULES = JSON.parse(await readFile(new URL('./image_intents.json', import.meta.url), 'utf8'));
const matches = (key, text) => new RegExp(RULES[key], 'iu').test(text);
export function parseImageCommand(text, imageCount = 0) {
    text = text.trim();
    if (['/生图状态', '生图状态', '/改图状态', '改图状态'].includes(text)) return { action: 'status', prompt: '' };
    let match = /^(?:生图\s*[:：]|\/生图(?:\s+|$))([\s\S]*)$/u.exec(text);
    if (match) return { action: 'generate', prompt: match[1].trim() };
    match = /^(?:(?:改图|修图|编辑图片|修改图片)\s*[:：]|\/(?:改图|修图)(?:\s+|$))([\s\S]*)$/u.exec(text);
    if (match) return { action: 'edit', prompt: match[1].trim() };
    if (!text || text.startsWith('/') || ['analysis_first', 'negative', 'generation_question', 'non_image_generation'].some(key => matches(key, text))) return null;
    if (!imageCount && matches('previous', text)) return { action: 'previous', prompt: text };
    if (!matches('generation_question', text) && !matches('non_image_generation', text)
        && !/^(?:比如|例如|举例|假设|假如|[“"「『])/u.test(text)
        && RULES.generation.some(pattern => new RegExp(pattern, 'iu').test(text)))
        return { action: 'generate', prompt: text };
    if (!imageCount) return null;
    if (matches('edit_action', text) && !/哪里需要|如何修改|怎么修改/u.test(text)) return { action: 'edit', prompt: text };
    return matches('non_edit', text) ? null : { action: 'edit', prompt: text };
}
export async function handleImageInbound(inbound, selfId, authorize, dispatch = codexImageCommand) {
    if (inbound.kind !== 'private' || inbound.messageId === undefined
        || inbound.forwardId !== undefined
        || !inbound.media.every(ref => ref.kind === 'image')) return null;
    const count = inbound.media.length;
    const text = Array.isArray(inbound.segments) ? inbound.segments
        .filter(segment => segment.type === 'text' && typeof segment.data?.text === 'string')
        .map(segment => segment.data.text).join('').trim() : inbound.text;
    const quoted = inbound.replyId != null && !count && !matches('negative',text) && !matches('analysis_first',text)
        && (matches('edit_action',text) || /按这张|照这张/u.test(text));
    if (inbound.replyId != null && !quoted || !quoted && !parseImageCommand(text, count)) return null;
    const config = authorize ?? JSON.parse(await readFile(ROOT + 'accounts.json', 'utf8'));
    if (inbound.userId !== config.owner || config.accounts[selfId]?.port !== 13101) return null;
    if (quoted) return dispatch(text, `${inbound.time}/${inbound.messageId}`, selfId, count, inbound.messageId, inbound.replyId);
    return dispatch(text, `${inbound.time}/${inbound.messageId}`, selfId, count, inbound.messageId);
}
export async function codexImageCommand(text, key, bot, imageCount = 0, messageId = null, quote = null) {
    const parsed = quote != null ? { action:'previous', prompt:text } : parseImageCommand(text, imageCount);
    if (!parsed) return null;
    if (parsed.action === 'edit' && imageCount && !parsed.prompt) parsed.prompt = RULES.default_edit;
    if (parsed.action === 'edit' && (!imageCount || messageId == null))
        return '图没跟过来，把图和要改的地方放同一条消息里发我。';
    if (parsed.action !== 'status' && (!parsed.prompt || [...parsed.prompt].length > 4000))
        return '用法：生图：一个可爱的小猪\n每条描述请控制在1–4000字，一次画一张。';
    if (imageCount > 5) return '一次最多5张就好，第一张放要改的图，后面放参考图。';
    try {
        const token = (await readFile(ROOT + 'client-token', 'utf8')).trim();
        const status = parsed.action === 'status';
        const response = await fetch('http://127.0.0.1:13210' + (status ? '/status' : '/jobs'), {
            method: 'POST', headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
            body: JSON.stringify(status ? { bot } : { bot, event_key: key, prompt: parsed.prompt,
                kind: parsed.action, message_id: imageCount ? String(messageId) : quote }),
            signal: AbortSignal.timeout(8000),
        });
        if (!response.ok && response.status !== 400) throw new Error('unavailable');
        const result = await response.json();
        if (result.error === 'missing_image') return '没找到你指的那张图，把原图发我就能接着改。';
        if (result.error) return result.error === 'busy' ? '这会儿还有几张在画，等会儿再来找我。' : '刚才没接上，过会儿再试一下。';
        if (status) {
            if (!result.job) return '还没画过呢。想画什么，发“生图：……”给我就行。';
            const labels = { queued: '前面还有图在画，稍等我一下。', generating: '还在画，画好就发你。', generated: '图已经好了，等QQ连上就发。', sending: '画好了，正在发给你。', sent: '图已经发过去啦。', sent_relayed: '图已经补发过去啦。', delivery_failed: '图好了，但QQ没传上去，成品还留着。', failed: '这次没弄成。', uncertain: '刚才没确认发没发到，你先看看聊天里有没有图，我先不重发。' };
            return '[绘图' + result.job.id.slice(0, 6) + '] ' + (labels[result.job.status] ?? result.job.status);
        }
        if (result.duplicate) return '这条我接过了，没再画一遍。';
        if (parsed.action === 'edit') return imageCount > 1 ? '行，第一张我来改，后面的拿来参考。' : '行，这张交给我。';
        return imageCount ? '行，照着参考图画。' : '行，开画。画好了给你。';
    } catch {
        return '画图那边暂时没连上，过会儿再试。';
    }
}
