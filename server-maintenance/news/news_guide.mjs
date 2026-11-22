import { spawn } from 'node:child_process';

function updateGuide(request) {
  return new Promise((resolve, reject) => {
    const child = spawn('/usr/bin/python3', ['-B', '/home/ubuntu/server-maintenance/news/news_preferences.py'], {
      stdio: ['pipe', 'pipe', 'ignore'], timeout: 12000,
    });
    let out = '';
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', part => { out += part; });
    child.once('error', reject);
    child.once('close', code => {
      if (code === 0 && out.trim()) resolve(out.trim());
      else reject(new Error('共享新闻指南操作未完成，请核对参数后再试。'));
    });
    child.stdin.on('error', reject);
    child.stdin.end(JSON.stringify(request));
  });
}

export function registerNewsGuide(ctx, defineTool, authorize, update = updateGuide) {
  ctx.tools.register(defineTool({
    name: 'shared_news_preferences',
    description: '本人私聊专用。查看和修改与小c、Codex、新闻推送共用的新闻偏好指南。',
    parameters: {
      action: { type: 'string', required: true, enum: ['show', 'set_weight', 'adjust_weight', 'set_rule', 'feedback_item'] },
      topic: { type: 'string', enum: ['国际政治', '战争安全', '全球经济', '灾害卫生', '科技科学', '中国及周边'] },
      weight: { type: 'number', description: '0–5，1 为正常' },
      direction: { type: 'string', enum: ['more', 'less'] },
      name: { type: 'string', description: '固定规则名。修改现有规则时复用原名。' },
      value: { type: 'string', description: '新闻选题或表达规则，空串删除指定规则。' },
      item: { type: 'string', description: '反馈用已送达新闻的编号、简报序号或刚才。' },
      rating: { type: 'string', enum: ['重要', '不感兴趣', '少推这类', '多推这类'] },
    },
    output: {
      schema: { type: 'object', additionalProperties: false, properties: { result: { type: 'string', required: true } } },
      render: (_args, value) => [{ type: 'text', text: value.result }],
    },
    async execute(args, context) {
      authorize(context);
      return { result: await update(args) };
    },
  }));
  ctx.systemPrompt.section({ name: 'qq:shared-news-guide', order: 10530,
    text: '本人要查看、记录或调整新闻选题偏好时用shared_news_preferences。该工具与小c、桌面Codex和实际新闻定时服务同读同写一份指南。查看现有规则后复用对应的规则名。反馈具体新闻时用feedback_item。收到成功结果后再说已保存；无需在聊天记忆里另建一份。' });
}
