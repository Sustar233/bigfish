// Owner-only native Codex image job client for the DeepSeek OneBot adapter.
import { readFile } from 'node:fs/promises';
export function parseImageCommand(text) {
    if (['/生图状态', '生图状态'].includes(text.trim())) return { action: 'status', prompt: '' };
    const match = /^(?:生图\s*[:：]|\/生图(?:\s+|$))([\s\S]*)$/u.exec(text.trim());
    return match ? { action: 'generate', prompt: match[1].trim() } : null;
}
export async function codexImageCommand(text, key, bot) {
    const parsed = parseImageCommand(text);
    if (!parsed) return null;
    if (parsed.action === 'generate' && (!parsed.prompt || [...parsed.prompt].length > 4000))
        return '用法：生图：一个可爱的小猪\n每条描述请控制在1–4000字，一次画一张。';
    try {
        const token = (await readFile('/home/ubuntu/server-maintenance/images/.private/client-token', 'utf8')).trim();
        const status = parsed.action === 'status';
        const response = await fetch('http://127.0.0.1:13210' + (status ? '/status' : '/jobs'), {
            method: 'POST', headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
            body: JSON.stringify(status ? { bot } : { bot, event_key: key, prompt: parsed.prompt }),
            signal: AbortSignal.timeout(8000),
        });
        if (!response.ok && response.status !== 400) throw new Error('unavailable');
        const result = await response.json();
        if (result.error) return result.error === 'busy' ? '画架前还有几单排着，稍等一会儿再来。' : '这单没接上，稍后再试。';
        if (status) {
            if (!result.job) return '还没有生图任务。可以发：生图：一个可爱的小猪';
            const labels = { queued: '排队中', generating: '正在画', generated: '已画好，待投递', sending: '正在发图', sent: '已发出', failed: '未完成', uncertain: '发送结果待核对，未自动重发' };
            return '[绘图' + result.job.id.slice(0, 6) + '] ' + (labels[result.job.status] ?? result.job.status);
        }
        if (result.duplicate) return '这条生图请求已经接过啦，没有重复开画。';
        return '大肥鱼接到画单啦，交给Codex画一张，画好就递给大人。[绘图' + result.id.slice(0, 6) + ']';
    } catch {
        return '画架这会儿没接上，暂时不能生图，稍后再试。';
    }
}
