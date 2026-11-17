# DeepSeek Harness 私人 QQ 接入

目标账号 2223525305，原 QQ 插件仅允许 17162047 好友私聊；插件的原生群聊保持关闭。2026-11-14 用户另行授权固定三人群 628128804，由独立 qq-group.service 统一调度，Harness 通过禁用工具的 qq-group headless profile 回复；详见 [群聊使用说明](../qq-codex/群聊使用说明.md)。用户选择沿用 Harness 现有 DeepSeek API 模型配置。

部署已完成，最终核验时间 2026-11-14 01:51:46（香港／北京时间）。用户已确认收到 Harness 自动回复，QQ 服务重启免扫码恢复已验证，账号服务与 Harness 均 active / enabled。

## 运行布局

- 服务器：43.142.167.150。
- 目录：/home/ubuntu/qq-dsh；QQ 数据：napcat-runtime/qq-data。
- 容器：qq-dsh-account；服务：qq-dsh-account.service，当前 active / enabled。
- 复用已校验的 NapCat 4.18.42 镜像；普通用户 1000:1001、根目录只读、移除全部 capabilities、禁止提权；1 GiB 内存及 1.5 核 CPU 上限。
- 独立固定 MAC：02:42:2b:8e:a7:02。
- OneBot HTTP/SSE：127.0.0.1:13101；正向 WS：127.0.0.1:13102；WebUI：127.0.0.1:13180。
- 随机接口令牌在服务器生成并持久保存，未写入本文。

## Harness

宿主 0.2.1-rc.2，服务 deepseek-harness.service，web profile。插件 dsh-onebot-qq 0.10.0，npm 元数据仓库为 mario841859784/dsh-onebot；下载校验 SHA-512 integrity 后以本地 tgz 安装，禁用了生命周期脚本。

源码与文档：https://github.com/mario841859784/dsh-onebot

安装包：/home/ubuntu/qq-dsh/dsh-onebot-qq-0.10.0.tgz。
完整性记录：/home/ubuntu/qq-dsh/npm-integrity.json。
安装前 profile 的 package.json、cordis.patch.yml、pnpm-workspace.yaml、pnpm-lock.yaml 已备份到 /home/ubuntu/qq-dsh/backups/profile-web-before-onebot，属私密资料。

web profile 的 bundles 增加 dsh-onebot-qq；cordis.patch.yml 增加顶层 id=dsh-onebot 配置，使用 forward WS 到 13102。adminUsers 和 allowFrom 均仅 17162047；dmPolicy=allowlist；groupPolicy=disabled；allowAllUsers=false；ignoreSelf=true；workspacePath=/home/ubuntu/qq-dsh/workspace。

实际插件 dmAllowed / groupAllowed 函数的 4 项检查已通过：允许大号，拒绝 Codex 控制的小号 1103828665，拒绝陌生号，拒绝群聊。机器人互聊尚未启用。

## 已完成验收

1. get_login_info 确认扫码实际登录 2223525305；get_status 为 online=true / good=true，大号已是好友。
2. Harness 日志确认 OneBot connected，lifecycle 身份是 2223525305。
3. 重启 QQ 服务后固定 MAC 保持、免扫码自动恢复。
4. 大号发送真实测试消息，用户确认收到 Harness 自动回复。用户明确选择沿用现有 DeepSeek API 配置，此账号的模型调用独立于 Codex 额度。
5. qq-dsh-account.service、deepseek-harness.service 均 active / enabled；原 Codex QQ 及知乎日报定时器仍 active / enabled。

未重启整台服务器；后续平台可能要求重新扫码。插件调用与会话使用 Harness 的现有权限和模型设置，没有放宽宿主工具审批。

## 使用与维护

用大号 17162047 私聊新号 2223525305 即可。模型切换与工作区等命令可在 QQ 中发送 `/help` 查看插件实际帮助。

```sh
systemctl is-active qq-dsh-account.service deepseek-harness.service
systemctl is-enabled qq-dsh-account.service deepseek-harness.service
sudo systemctl restart qq-dsh-account.service
sudo systemctl restart deepseek-harness.service
```

后一个命令会重启整个 Harness Web 服务。现有 Codex QQ 使用独立容器和服务，不依赖 Harness。

WebUI 只可通过 SSH 转发访问服务器 127.0.0.1:13180；不要开放公网端口或公开令牌。原始 Harness/QQ 日志、配置、会话和 profile 备份可能包含私密资料，不要直接分享。

不含正文或密钥的核验记录：服务器 `/home/ubuntu/qq-dsh/deployment-complete.json`，本地 `../results/qq-dsh-deployment-complete.json`。

两机器人现在可在固定三人群中有限互动：只由用户新发言开启、最多各一句，不能相互触发新轮。私聊仍不接收另一机器人的消息。
