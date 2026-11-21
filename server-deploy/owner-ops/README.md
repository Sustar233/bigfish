# 本人 QQ 的服务器执行权限

2026-11-21 用户明确授权：仅在两个号与 QQ 1000000001 本人私聊时，可按本人指令调用服务器 Codex、DeepSeek Harness。群聊和其他账号不开放任务执行。

## 使用

小c私聊支持明确指令：

- `/codex 任务正文` 或 `让 Codex：任务正文`
- `/harness 任务正文` 或 `让 Harness：任务正文`
- `/服务器任务 查询 任务编号`
- `/服务器任务 取消 任务编号`

大肥鱼私聊通过既有 `server_codex` 和新增 `server_harness` 工具提交、查询、取消，可用自然语言明确点名执行器。每个任务最长5分钟，同一时刻最多一个任务。长任务先返回编号，用户可查询结果；本轮没有新增自动通知。

`returned` 只表示执行器返回，不能代替任务成功验证。测试实际读回了两个执行器创建的文件。取消停止后续执行，不会自动撤销已发生的文件修改。

## 限定范围

- 小c既有真实QQ事件白名单保持不变，在私聊命令入口再次核对配置中本人号。
- Harness工具执行时验证受信会话 ID 为 `onebot-private-1000000001` 或其派生私聊会话，群会话、其他号及相似号码被拒绝。
- 本机Unix socket仅ubuntu可访问；服务核验本机UID及来源、本人号、私聊类型。普通群聊模型没有调用该服务的工具。
- 各会话只能管理自己的任务；幂等键避免同一消息重复提交。
- 任务服务以ubuntu运行，`NoNewPrivileges` 阻止提权，系统文件和home默认只读，SSH目录不可访问。只开放现有QQ、日报、媒体、监控和维护项目目录、任务工作区及Codex认证刷新目录写入。
- 不更改全局AppArmor。Codex写任务在独立systemd外层沙箱中运行，避免先前bwrap命名空间故障；Codex内部使用外部沙箱执行模式。只读请求仍使用Codex的read-only模式，不将它悄悄提升为写任务。
- 新Harness执行profile为 `qq-owner`：从已有无界面profile复制，启用文件、搜索和终端等任务工具，维持无QQ发送、无子代理、无插件管理、无定时任务工具。日常大肥鱼仍用 `qq-natural-v3`。

## 实际部署

服务：`qq-owner-ops.service`，已启用开机启动。主目录 `/home/ubuntu/qq-owner-ops`，socket `/run/qq-owner-ops/control.sock`，任务记录 `tasks/*.json`，权限600。

接线：小c线上 `bridge.py` 的真实 `command(self, text, key, image_count=0, message_id=None)` 入口插入 `owner_client.py`；保留媒体/点赞等功能。大肥鱼复用现有 `dafeiyu-codex.mjs`，注册额外 `owner-tools.mjs`，仅加入QQ限定预设。群聊代码及群profile没有改动。

备份在主目录 `backup-*`，`backup-path.txt` 记录原桥接、原委派插件和原web profile。部署中途发现线上函数有媒体参数，已按真实签名完成补丁；最终服务、模块导入和两种实际写任务均通过。

验证：三种非法来源拒绝；Harness近似号码拒绝；跨会话任务查询拒绝；普通聊天不触发；两个执行器均创建并读回内容 `OWNER_EXEC_OK` 的测试文件。没有发送QQ测试消息。用户从QQ触发后的整条回复链路仍需用户新指令验收。

## 回滚

确认没有运行任务后，先停止 `qq-owner-ops`，用 `backup-path.txt` 中原件恢复 bridge.py、dafeiyu-codex.mjs、web profile，重启 `qq-chat` 与 `deepseek-harness`；保留任务记录。若其他维护已经改过同一文件，应按差异撤回，不可直接覆盖。
