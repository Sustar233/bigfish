// QQ-native transcription enters the image queue BEFORE an ordinary chat turn.
import { readFile } from 'node:fs/promises';
import { parseImageCommand, codexImageCommand } from './codex-image.js';

export function normalizeVoice(text) {
    if (typeof text !== 'string') return '';
    return text.trim().replace(/^(?:(?:嗯+|呃+|啊|那个|就是|你好|小c|大肥鱼|请你|我(?:现在)?(?:想要?|需要|希望)(?:让你|你)?)[，,。:：\s]*)+/iu, '').trim();
}

export async function handleVoiceImageInbound(inbound, selfId, call, dependencies = {}) {
    if (inbound.kind !== 'private' || inbound.messageId === undefined
        || inbound.replyId !== undefined || inbound.forwardId !== undefined
        || !Array.isArray(inbound.media) || !inbound.media.some(ref => ref.kind === 'voice')
        || !inbound.media.every(ref => ['voice', 'image'].includes(ref.kind))) return null;
    const config = dependencies.authorize ?? JSON.parse(await readFile('/home/ubuntu/server-maintenance/images/.private/accounts.json', 'utf8'));
    if (String(inbound.userId) !== String(config.owner) || config.accounts[selfId]?.port !== 13101) return null;
    let transcript = '';
    for (let attempt = 0; attempt < 2; attempt++) {
        try {
            const result = await call('fetch_ptt_text', { message_id: inbound.messageId });
            if (typeof result?.text === 'string' && result.text.trim()) { transcript = result.text.trim(); break; }
        } catch { /* Ordinary voice handling remains available if native STT fails. */ }
        if (!attempt) await (dependencies.pause ?? (() => new Promise(resolve => setTimeout(resolve, 1000))))();
    }
    if (!transcript) return null;
    inbound.voiceTranscript = transcript;
    const caption = Array.isArray(inbound.segments) ? inbound.segments
        .filter(segment => segment.type === 'text' && typeof segment.data?.text === 'string')
        .map(segment => segment.data.text).join('').trim() : '';
    const text = normalizeVoice((caption ? caption + '\n' : '') + transcript);
    const count = inbound.media.filter(ref => ref.kind === 'image').length;
    if (!parseImageCommand(text, count)) return null;
    return (dependencies.dispatch ?? codexImageCommand)(text, `${inbound.time}/${inbound.messageId}`,
        selfId, count, inbound.messageId);
}
