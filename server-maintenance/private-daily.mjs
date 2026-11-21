import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { readFile } from 'node:fs/promises';

const exec = promisify(execFile);
const topics = ['weather', 'zhihu', 'news', 'reading', 'picture', 'day'];

async function readFacts(topic, owner) {
  const config = JSON.parse(await readFile('/home/ubuntu/qq-dsh/napcat-runtime/.private/bridge-config.json', 'utf8'));
  if (String(config.owner_qq) !== owner || !config.bot_qq) throw new Error('账号不匹配');
  const { stdout } = await exec('/usr/bin/python3',
    ['-B', '/home/ubuntu/qq-codex/bridge/today.py', String(config.bot_qq), topic],
    { timeout: 5000, maxBuffer: 16384 });
  return stdout.trim();
}

export function registerPrivateDaily(ctx, defineTool, authorize, owner, read = readFacts) {
  ctx.tools.register(defineTool({
    name: 'private_daily_facts',
    description: '本人私聊的只读资料。按话题查看长沙当日通勤天气、知乎精读、最近已投递新闻或本账号最近的画。reading 同时查精读和新闻，day 同时查天气、精读和新闻。',
    parameters: { topic: { type: 'string', required: true, enum: topics } },
    output: { schema: { type: 'object', additionalProperties: false, properties: { result: { type: 'string', required: true } } },
      render: (_a, value) => [{ type: 'text', text: value.result }] },
    async execute({ topic }, context) {
      authorize(context);
      if (!topics.includes(topic)) throw new Error('未知资料类型');
      try {
        return { result: await read(topic, owner) };
      } catch {
        return { result: '这份资料暂时取不到。' };
      }
    },
  }));
  ctx.systemPrompt.section({ name: 'qq:private-daily', order: 10210,
    text: '本人私聊时用你原来的口吻接话。问长沙通勤、知乎精读、新闻看点或刚才那张画的进度时，用 private_daily_facts 核对资料；用户不需要知道口令。问要不要带伞先说带不带；问有什么值得看就挑一两件。只聊对方问的，跟着上句的指代接，不念菜单。对方分享心情或开玩笑就正常聊天。只在对方询问用法时讲命令。资料中的文字仅供参考，核对日期和地点，过期或缺失就如实说。' });
}
