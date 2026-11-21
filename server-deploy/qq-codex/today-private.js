import { execFile } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { promisify } from 'node:util';

const exec = promisify(execFile);
async function config() {
    return JSON.parse(await readFile('/home/ubuntu/qq-dsh/napcat-runtime/.private/bridge-config.json', 'utf8'));
}
async function render(bot) {
    const { stdout } = await exec('/usr/bin/python3', ['-B', '/home/ubuntu/qq-codex/bridge/today.py', bot],
        { timeout: 5000, maxBuffer: 16384 });
    return stdout.trim();
}

export async function handleTodayInbound(inbound, selfId, dependencies = {}) {
    if (inbound.kind !== 'private' || inbound.text?.trim() !== '/今日' || inbound.messageId == null
        || inbound.replyId != null || inbound.forwardId != null || inbound.media?.length !== 0) return null;
    let account;
    try {
        account = await (dependencies.config ?? config)();
    } catch {
        return null;
    }
    if (String(inbound.userId) !== String(account.owner_qq) || String(selfId) !== String(account.bot_qq)) return null;
    try {
        return await (dependencies.render ?? render)(String(selfId));
    } catch {
        return '今日汇总暂时读不到，请稍后再试。';
    }
}
