import { authorize } from './owner-tools.mjs';
import { registerPrivateDaily } from './private-daily.mjs';
import { registerReminders } from './reminder-tools.mjs';

export const name = 'qq-daily-tools';
export const inject = ['tools', 'systemPrompt'];
export async function apply(ctx) {
    const { defineTool } = await import('@deepseek-ai/dsh-tools');
    ctx.systemPrompt.section({name:'qq:work-mode-meaning',order:10211,text:'本人提到大肥鱼的 root，指的是服务器工作模式。可以用自己的口吻回答：可以呀，进入工作模式后能检查服务器状态、委托服务器上的 Codex 或 Harness 检查和修改授权项目、跑测试和查询结果。问有哪些能力就举实际例子。直接说 root 或进入 root 模式可开启；是否执行、成功与否按真实任务结果回答。新闻偏好、小c登录检查和扫码不需要切换。'});
    registerReminders(ctx, defineTool, authorize);
    registerPrivateDaily(ctx, defineTool, authorize, '1000000001');
}
