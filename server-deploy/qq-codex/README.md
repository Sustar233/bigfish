# 私人 QQ 与 Codex

**最新状态（2026-11-14）**：10:50 QQ 通知“当前登录已失效”，用户重新扫码后已核验 Codex 在线、身份正确、聊天桥重新连接；Harness 在线。两号人设、独立档案、记忆及备份升级均已接入。详见 [故障记录](incidents/2026-11-14-qq-offline.md)。

已部署于腾讯云服务器 43.142.167.150。2026-11-14 已升级独立聊天档案、确认式记忆、加密备份和掉线提醒，详见 [记忆与人设使用说明](记忆与人设使用说明.md)。

现已按用户新要求接入固定三人群 628128804：无需点名，自然接话，每轮最多两次生成；机器人消息不能续开新轮。各自可检索自己的私聊旧记录，群档案单独保存。见 [群聊使用说明](群聊使用说明.md)。

小号 **1103828665** 只响应大号 **17162047** 的好友私聊文本。用户已确认收到实际自动回复；QQ 服务重启后免扫码恢复已验证。QQ、聊天桥、代理均已运行并设为开机启动，知乎日报定时器保持正常。

## 实际方案

QQ → NapCat 4.18.42 / Linux QQ 3.2.34-53644 → OneBot HTTP/SSE → `bridge.py` → 已通过 ChatGPT 登录的 Codex CLI → 固定大号 QQ。

本 Codex 小号使用现有 Codex 额度，未接入付费模型 API。Harness 小号 2223525305 仍沿用其 DeepSeek 配置。Codex 当前只支持文本聊天，不执行服务器命令、读取用户文件、搜索网络或调用插件。QQ 上下文独立于桌面聊天，保留最近 20 轮，另有总长度限制；完整文字档案独立持久保存，并支持关键词检索、相关历史召回和导出。

- `/帮助` 或 `/help`：显示使用说明。
- `/清空` 或 `/new`：清空当前话题上下文，保留档案与长期记忆。
- `/记住 内容`、`/查看记忆`、`/待确认记忆`、`/确认记忆 编号`、`/忘记 编号`：管理长期记忆。
- `/查记录 关键词`、`/导出 md|html|jsonl [YYYY-MM-DD]`：检索或接收档案附件。
- `/导出 Harness md`、`/记住 Harness 内容`：从 Codex 号管理 Harness 独立档案与记忆。

## 隔离与存储

QQ 在独立 Docker 容器 `qq-account` 中以 UID 1000 / GID 1001 运行；根目录只读，移除全部 capabilities，禁止提权，内存上限 1 GiB、CPU 上限 1.5 核。没有挂载 Docker socket、Codex 登录文件、知乎凭据或邮箱配置。已用精简启动脚本替代归档原入口。

固定 MAC `02:42:2b:8e:a7:01`，避免容器重启时设备身份漂移。OneBot 仅发布到 `127.0.0.1:13001`，WebUI 仅发布到 `127.0.0.1:13080`；两个接口均使用独立随机令牌，不开放公网。

服务器路径：

- `/home/ubuntu/qq-codex/napcat-runtime/qq-data`：QQ 登录状态与客户端数据。
- `/home/ubuntu/qq-codex/napcat-runtime/app/napcat/config`：NapCat / OneBot / WebUI 配置。
- `/home/ubuntu/qq-codex/bridge/.private/config.json`：聊天桥配置，权限 600。
- `/home/ubuntu/qq-codex/bridge/.private/chat.sqlite3`：事件去重及最近对话，私密目录中保存。
- `/home/ubuntu/qq-codex/inspection/deployment-complete.json`：不含正文或令牌的最终核验记录。

聊天桥日志只记录运行事件，不记录正文或令牌。NapCat / QQ 自身的日志与数据仍属于私密资料，不要公开原始容器日志、配置或备份。

## 运维

```sh
systemctl is-active qq-account.service qq-chat.service codex-proxy.service
systemctl is-enabled qq-account.service qq-chat.service
sudo journalctl -u qq-chat.service -n 30 --no-pager
sudo systemctl restart qq-chat.service
sudo systemctl restart qq-account.service
```

暂停自动回复：`sudo systemctl stop qq-chat.service`。恢复：`sudo systemctl start qq-chat.service`。

需要查看管理页时，通过 SSH 将本机端口转发到服务器 `127.0.0.1:13080`，在私密环境中使用服务器配置里的 WebUI 令牌。不要在公网开放接口或把令牌贴到聊天里。

本次服务重启恢复已验证，未重启整台服务器；平台后续仍可能要求重新扫码。模型额度不足、ChatGPT 登录失效或代理不可用时，需要处理对应问题，程序不会改用付费 API。

本次 15 项单元测试通过，包含白名单、防重复、固定回复对象、上下文与档案分离、账号隔离、待确认记忆、历史召回与安全导出；此前 SSE 空闲超过 30 秒后继续接收事件的实际连接测试也已通过。部署细节见 [部署进度](部署进度.md)，早期路线比较见 [历史调研](research/方案调研-2026-11-13.md)。
