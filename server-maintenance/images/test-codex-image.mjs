import assert from 'node:assert/strict';
import { parseImageCommand } from './codex-image.js';
for (const command of ['生图：小猪', '生图:小猪', '/生图 小猪'])
    assert.deepEqual(parseImageCommand(command), { action: 'generate', prompt: '小猪' });
for (const text of ['研究生图功能', '比如生图：小猪', '你好']) assert.equal(parseImageCommand(text), null);
assert.deepEqual(parseImageCommand('生图状态'), { action: 'status', prompt: '' });
console.log('7 image command checks passed');
