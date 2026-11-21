import assert from 'node:assert/strict';
import { handleTodayInbound } from './today-private.js';

const event = { kind: 'private', text: '/今日', messageId: 1, userId: 'owner', media: [] };
let calls = 0;
const dependencies = {
    config: async () => ({ owner_qq: 'owner', bot_qq: 'bot' }),
    render: async bot => { calls++; assert.equal(bot, 'bot'); return '今日汇总'; },
};
for (const changes of [{ kind: 'group' }, { userId: 'other' }, { text: '/今日 abc' },
                        { media: [{}] }, { replyId: 1 }, { forwardId: 2 }]) {
    assert.equal(await handleTodayInbound({ ...event, ...changes }, 'bot', dependencies), null);
}
assert.equal(await handleTodayInbound(event, 'other', dependencies), null);
assert.equal(calls, 0);
assert.equal(await handleTodayInbound(event, 'bot', dependencies), '今日汇总');
assert.equal(calls, 1);
