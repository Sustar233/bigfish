# 大肥鱼 QQ 委托 Codex

2026-11-20 接入本人 QQ 私聊。聊天预设 `qq-natural-v3` 注册专用 `server_codex` 工具，支持提交、查询和取消本会话任务。普通闲聊不调用 Codex。

## 部署与验证

- 实际插件：服务器 `/home/ubuntu/qq-dsh/codex-integration/dafeiyu-codex.mjs`；本地维护源：同目录下的 `dafeiyu-codex.mjs`。
- 预设配置：`/home/ubuntu/.dsh/profiles/web/cordis.patch.yml`。备份：`/home/ubuntu/qq-dsh/codex-integration/backup-20261120-130919/cordis.patch.yml`。
- 专用工作目录：`/home/ubuntu/qq-dsh/codex-workspace`；任务及结果：`/home/ubuntu/qq-dsh/.private/codex-tasks`。
- 已通过接口 schema、本人私聊限制、跨会话隔离、幂等提交、并发、状态查询、取消和异步通知测试。
- 已通过真实链路：QQ 对应的 DeepSeek 会话调用工具，Codex 返回结果，程序向本人 QQ 投递成功。真实测试的任务编号和投递回执仅保留在服务器私密记录中。
- 该次写文件任务未完成：Ubuntu AppArmor 的 `unprivileged_userns` 拒绝 bwrap 的 net_admin/setpcap，测试文件没有创建。不能把模型进程正常结束解释为用户任务已成功。
- 临时部署验收触发器已从配置移除；不会在以后重启时自动提交测试任务。

## 沙箱前置条件（待用户明确授权）

已按官方前置条件安装 Ubuntu bubblewrap（50.4 kB 下载）；未升级系统 AppArmor。通过 Ubuntu 软件源下载并解包了 apparmor-profiles，仅准备官方 `bwrap-userns-restrict` 配置，尚未安装或加载。自动审批要求明确授权，因为配置会持久影响本机 `/usr/bin/bwrap` 的命名空间及挂载权限。没有关闭全局 AppArmor 限制，也没有切换 Codex 到无沙箱模式。

待加载文件：`/home/ubuntu/qq-dsh/codex-integration/apparmor-package/usr/share/apparmor/extra-profiles/bwrap-userns-restrict`。获得明确授权后先解析检查，再安装到 `/etc/apparmor.d/bwrap-userns-restrict` 并加载；验证 bwrap 和真实工作目录写入，之后再次核对 QQ 回传。

参考：[Codex 官方沙箱前置条件](https://learn.chatgpt.com/docs/sandboxing#prerequisites)。

## 任务与维护

每个任务最多 5 分钟，同时运行一个；稳定 request_key 防止重复提交。长任务完成后自动投递到本人 QQ，投递结果不确定时不自动重发，可查询任务记录。服务重启后旧任务若无运行进程，标记为状态不可确认，避免误报成功。单条回传最多约 3600 字符，结果记录最多 6000 字符。

`workspace_write` 仅允许专用工作目录内写入，`read_only` 用于只读；任意服务器路径修改不在这个接口的直接写入范围。当前 AppArmor 问题解决前，涉及执行工具的任务会受到限制，文字分析和生成链路已经验证。

Codex 使用服务器现有 ChatGPT 登录额度，沿用 `codex-proxy`；真实 usage 记录为“**大肥鱼委托Codex**”。token 账本不保存任务正文。调试时不得打印代理配置、OneBot token、Codex 登录文件或完整私聊记录。

回滚：先确认无运行任务，再恢复上述预设配置备份并重启 `deepseek-harness`；保留任务记录。专用依赖链接指向已安装 Harness 的 dsh-tools 包，升级 Harness 后需要核对链接。

## 群聊修复

此前候选修复已上线：同时提及大肥鱼和 Codex 时优先大肥鱼；一位失败后另一位仍可回复。线上原有 15 项群聊回归通过；本地含新增场景的 17 项离线检查此前通过。仅重启 qq-group，备份位于 `/home/ubuntu/qq-codex/bridge/.private/backup-group-codex-20261120-131250/`。本次 Codex 工具先接本人私聊，群聊没有自动获得服务器任务执行权。

## SSH 管理入口

本地新 VPN 下需绑定以太网：`ssh -b 192.0.2.20 ubuntu@192.0.2.10`。密码仅使用用户明确授权的现有服务器凭据，不写入文档或源码。以太网地址变化时重新核对，不能直接认定服务器 SSH 故障。
