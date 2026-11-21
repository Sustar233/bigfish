import assert from 'node:assert/strict';
import { authorize } from './dafeiyu-codex.mjs';
import { registerPrivateDaily } from './private-daily.mjs';

// Use the deployment template's example identity. No real QQ or model calls.
const session = id => ({ agent: { session: { id } } });
let tool, reads = 0;
const ctx = { tools: { register: candidate => { tool = candidate; } }, systemPrompt: { section() {} } };
registerPrivateDaily(ctx, spec => spec, authorize, '1000000001', async topic => { reads++; return topic; });
await assert.rejects(tool.execute({ topic: 'weather' }, session('onebot-group-1000000004')));
await assert.rejects(tool.execute({ topic: 'weather' }, session('onebot-private-1000000004')));
const owner = session('onebot-private-1000000001');
await assert.rejects(tool.execute({ topic: 'invalid' }, owner));
assert.equal(reads, 0);
assert.deepEqual(await tool.execute({ topic: 'weather' }, owner), { result: 'weather' });
assert.equal(reads, 1);
