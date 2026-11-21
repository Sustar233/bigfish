// Explicit private commands only. The Python runner owns account and target selection.
import { readFile } from 'node:fs/promises';
import { spawn } from 'node:child_process';

const COMMANDS = new Set([
    '/空间点赞', '/说说点赞', '/空间点赞最新', '/说说点赞最新', '/空间状态',
    '给我最新一条说说点赞', '给我的最新一条说说点赞', '给我最新的说说点赞',
    '给我的最新说说点赞', '赞一下我最新的说说', '给我说说点赞', '给我的说说点赞',
    '给我空间点赞', '给我最新一条说说点个赞', '给我的最新一条说说点个赞',
]);
export function isQzoneCommand(text) {
    if (typeof text !== 'string') return false;
    const compact = text.replace(/\s+/gu, '').replace(/[。！!]+$/u, '');
    return COMMANDS.has(compact) || /^\/(空间点赞|说说点赞|空间状态)/u.test(compact);
}

async function run(text) {
    return await new Promise((resolve, reject) => {
        const child = spawn('/usr/bin/python3', ['/home/ubuntu/qq-codex/bridge/qzone_runner.py', '--bot', 'harness'],
            { stdio: ['pipe', 'pipe', 'pipe'] });
        let output = '';
        const timer = setTimeout(() => { child.kill('SIGTERM'); reject(new Error('qzone_timeout')); }, 180000);
        child.stdout.setEncoding('utf8');
        child.stdout.on('data', chunk => {
            output += chunk;
            if (Buffer.byteLength(output) > 32768) { child.kill('SIGTERM'); reject(new Error('qzone_output_limit')); }
        });
        child.stderr.resume();
        child.on('error', error => { clearTimeout(timer); reject(error); });
        child.on('close', code => {
            clearTimeout(timer);
            if (code !== 0) return reject(new Error('qzone_runner_failed'));
            try {
                const result = JSON.parse(output);
                if (result.handled !== true || typeof result.reply !== 'string') throw new Error('invalid_reply');
                resolve(result.reply);
            } catch (error) { reject(error); }
        });
        child.stdin.on('error', () => {});
        child.stdin.end(JSON.stringify({ text }));
    });
}

async function identity() {
    const config = JSON.parse(await readFile('/home/ubuntu/qq-dsh/napcat-runtime/.private/bridge-config.json', 'utf8'));
    return { owner: String(config.owner_qq), bot: String(config.bot_qq) };
}

export async function handleQzoneInbound(inbound, selfId, dependencies = {}) {
    if (inbound.kind !== 'private' || !isQzoneCommand(inbound.text)
        || inbound.messageId === undefined || inbound.replyId !== undefined || inbound.forwardId !== undefined
        || !Array.isArray(inbound.media) || inbound.media.length !== 0) return null;
    try {
        const ids = await (dependencies.identity ?? identity)();
        if (String(inbound.userId) !== ids.owner || String(selfId) !== ids.bot) return null;
        return await (dependencies.run ?? run)(inbound.text);
    } catch {
        return '这次空间接口没接上，暂时没法完成点赞。';
    }
}
