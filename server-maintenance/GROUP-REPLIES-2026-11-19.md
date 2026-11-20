# 群聊回复策略调整

2026-11-19 11:19（北京时间）已部署到固定三人群 1000000004。

- 普通群聊无需 @，DeepSeek 大肥鱼优先回应，小 c 保留原参与节奏；明确点名小 c 或大肥鱼时，由对应角色优先回复。
- 连续消息仍按 2 秒静默合并，每轮最多两条；本人触发、成员校验、暂停、去重和原调用上限保持。
- 56 项回归检查通过。仅重启 qq-group；两账号 online/good 均为 true，两个群聊事件连接均已恢复。没有发送额外测试消息或发起真实模型测试。
- 备份：服务器 `/home/ubuntu/qq-codex/bridge/.private/backup-group-responsiveness-20261119-111929/`。回滚时恢复其中 group_chat.py、test_group_chat.py 并重启 qq-group。
- 服务器 README.md、CHANGELOG.md 已追加本次记录。
- 另外核实小 c 当前音色为 `zh-CN-XiaoxiaoNeural`；此前“小c维护”聊天已执行切换和测试，此处没有重复发送。
