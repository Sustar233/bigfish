import { readFileSync } from 'node:fs';
export const name = 'qq-natural-persona';
export const inject = ['systemPrompt'];
export function apply(ctx) {
  const style = readFileSync('/home/ubuntu/qq-codex/chat_style.md', 'utf8');
  ctx.effect(() => ctx.systemPrompt.section({
    name: 'deployment:persona-prefix', order: 0,
    text: '你通过 QQ 与用户交流。默认把闲聊当作聊天，不把每句话都理解为编程或办事请求。用户明确提出实际任务时认真处理，权限与审批规则保持有效。你是 AI，不编造真人身份或线下经历。',
  }));
  ctx.effect(() => ctx.systemPrompt.section({name: 'qq:natural-style-v3', order: 10300, text: style}));
}
