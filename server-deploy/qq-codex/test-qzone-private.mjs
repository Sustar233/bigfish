import assert from 'node:assert/strict';
import { handleQzoneInbound, isQzoneCommand } from './qzone-private.js';

const base = { kind: 'private', userId: 'owner', text: '给我最新一条说说点赞', messageId: '123', media: [] };
let calls = 0;
const deps = { identity: async () => ({ owner: 'owner', bot: 'bot' }), run: async text => {
    assert.equal(text, base.text); calls += 1; return 'verified';
} };
assert.equal(await handleQzoneInbound(base, 'bot', deps), 'verified');
assert.equal(calls, 1);
for (const change of [{ kind: 'group' }, { userId: 'stranger' }, { messageId: undefined },
    { replyId: 'quoted' }, { forwardId: 'forwarded' }, { media: [{ kind: 'image' }] },
    { text: '不要给我最新一条说说点赞' }, { text: '给我最新一条说说点赞？' }]) {
    assert.equal(await handleQzoneInbound({ ...base, ...change }, 'bot', deps), null);
}
assert.equal(await handleQzoneInbound(base, 'wrong-bot', deps), null);
assert.equal(calls, 1);
const failed = await handleQzoneInbound(base, 'bot', { ...deps, run: async () => { throw new Error('unavailable'); } });
assert.match(failed, /暂时没法/);
assert.equal(isQzoneCommand('/空间状态'), true);
assert.equal(isQzoneCommand('引用：给我说说点赞'), false);
console.log('private Qzone owner, bot, quote, media and failure gates: passed');
