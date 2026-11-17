# 2026-11-14 Codex QQ 不回复

当前状态：用户已重新扫码，核验 Codex QQ 身份正确、online=true、聊天桥出现 connected。用户确认两个号都能正常回复，并提出缩短回复与增强日常聊天感的优化要求，已接入 natural-qq-v2。Harness 小号在线。

早前恢复记录：用户先在手机 QQ 完成账号恢复，再重新扫码；get_login_info 验证 1103828665，get_status 在线。qq-account 与 qq-chat 已重新运行；聊天桥出现 connected 和 reply_sent，数据库 sent 从 13 增至 14，用户明确确认收到自动回复。

## 10:50 再次掉线

- 10:50:20 QQ KickedOffLine：“你的账号当前登录已失效，请重新登录。”
- 10:50:24 QQ Worker 自动重启；快速登录提示“你的用户身份已失效，为保证账号安全，请你重新登录。”
- 10:57 最终核验发现 Codex 离线，OneBot 随后 ConnectionResetError；Harness 在线。不是仅凭 systemd active 就认为能正常聊天。
- 本轮没有重启 Codex QQ 容器，仅在此前空闲时更新过聊天桥；不能据此确定平台作废登录的具体原因。
- 已启用的两分钟巡检记录到离线，并按连续两次失败策略通知；没有自动反复重登。11:00 后提取自动更新的新二维码交给用户。
- 用户确认扫码后，get_login_info 核对身份成功、get_status online=true，qq-chat 出现 connected；维护程序已再次执行以识别恢复。

恢复前曾收到 serverErrorCode=168、账号安全风险提示，因而暂停小号服务等待手机端恢复。Harness、代理与日报未中断。

## 已查明

- qq-account.service、qq-chat.service、codex-proxy.service 均仍 active；容器无 OOM、无宿主服务重启。
- 事件数据库已有 13 次 sent，之后新消息没有进入聊天桥；OneBot get_login_info / get_status 持续 ConnectionResetError。
- QQ 日志记录 11-14 05:01:18 账号离线；05:02:18 NapCat 自动重启 Worker 以重建登录服务。
- 05:02:23 新 Worker 日志为“没有 -q 指令指定快速登录，将使用二维码登录方式”。WebUI 状态 isLogin=false、coreReady=false、loginPhase=waiting_qrcode。
- 手动重启服务后已保存登录未能恢复；随后用户完成扫码，但 QQ 明确拒绝登录，错误码 168、账号安全风险提示。因此目前阻碍是平台账号限制，不能仅靠重启或反复刷新二维码恢复。最初掉线是否由同一限制触发没有充分证据。

## 已修复配置

- container-start.sh 增加 NAPCAT_QUICK_ACCOUNT=1103828665，让内部 Worker 继承明确的快捷登录账号。
- 现有 webui.json 设置 autoLoginAccount=1103828665；prepare_napcat.py 同步该默认配置，避免重新部署时遗漏。
- 保留固定 MAC、普通用户和只读容器限制，未修改 Harness QQ 账号。
- shell 语法检查通过，QQ 服务已重启并重新生成二维码。聊天桥仍运行并等待 QQ 接口恢复。

这些配置使内部重启有机会自动尝试快捷登录；若 QQ 平台要求重新验证，仍需扫码，不能保证永不掉线。

## 后续验证

1. 已完成：用户扫码后确认 get_login_info 为 1103828665、get_status 在线。
2. 已完成：聊天桥重新 connected，大号发送新测试消息，用户确认回复正常。
3. 如需验证内部 Worker 重启，应在没有待发送消息时通过管理接口触发，并观察是否保留账号选择；不要反复重启打断用户会话。
4. 已更新本记录。为避免刚恢复的账号再次中断，本次未额外触发 Worker 重启；新增配置不能保证平台限制永不再次发生。
