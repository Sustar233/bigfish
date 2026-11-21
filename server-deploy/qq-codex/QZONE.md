# 小c与大肥鱼空间说说点赞

2026-11-20 接入小c、大肥鱼本人白名单私聊和现有固定三人群。私聊任意一个账号可发送：

```text
给我最新一条说说点赞
/空间点赞
/空间状态
```

每次只处理现有私密配置 `owner_qq` 最新可见的一条说说，由对应的 `bot_qq` 点赞。固定命令在模型生成前执行，不消耗模型额度；没有新增自动点赞定时任务。

在现有固定三人群中：

```text
你们给我最新一条说说点赞
/空间点赞
大肥鱼给我说说点赞
小c给我说说点赞
/空间状态
```

“你们”或无点名的命令由两位分别执行；点名或只 @ 一位则只由对应账号执行。两号分别反馈结果，一位失败不会阻止另一位。群聊沿用本人、固定群、三人成员核验、双消息源去重、暂停状态及请求预算。机器人反馈不触发下一轮模型聊天。

私聊的引用/转发/媒体消息不触发大肥鱼点赞入口；普通问题、嵌入文本和指定其他账号的参数不触发写入。私聊与群聊共用同一账号的操作账本。

## 接口与结果

- NapCat 4.18.42 原生列表：`get_qzone_msg_list`，固定 `target_uin=owner_qq`、`format=native`。线上默认兼容列表出现“响应不完整”，因此使用原生列表。
- 只选作者身份匹配、`app_id=311` 且具有有效 `tid` 和发布时间的说说；按时间选择当前页最新一条。可见范围由QQ空间权限决定，不能据此声称读取了全部历史。
- 原生列表的 `feed_ref` 可能为空。点赞使用同版本支持的 `like_qzone`，传 `target_uin`、`tid`、`abstime`；写入异常时不切换接口或自动重试。
- 只有回读同一作者、同一 `tid` 的 `feed.cell_like.liked=true` 才报告已验证成功。原本已点赞时直接告知，不再写入。
- 各账号 `records/qzone-likes.sqlite3` 权限600，仅保存目标、说说标识、结果及时间；不保存说说正文或QQ凭据。写入前提交唯一记录，避免超时、并发或重复命令再次发送。结果未确认时 `/空间状态` 会显示待核对。
- 若用户之后自行取消赞，本地历史仍保留；再次请求同一条时先人工核对，不自动重复点赞。`/空间状态` 显示最近操作记录，不能替代当前空间状态。

## 维护与验证

小c私聊实现：`qzone_commands.py`，由 `patch_qzone_bridge.py` 接入。大肥鱼由 `qzone-private.js` 在 OneBot 白名单检查之后、模型分发之前接入，调用固定账号的 `qzone_runner.py`；插件实际路径为 `/home/ubuntu/.dsh/profiles/web/node_modules/dsh-onebot-qq/lib/`，升级覆盖插件时需复核补丁。

群聊实现：`qzone_group.py`，由 `patch_qzone_both.py` 接入 `Room.admit` 的本人身份核验及事件去重之后。两个账号并行执行，不调用模型。部署基于线上源文件打补丁，保留既有媒体、生图、新闻和Codex委派功能；本轮重启 `qq-chat`、`qq-group` 和 `deepseek-harness`，QQ容器保持运行。

```sh
python3 -m unittest -v test_qzone_commands test_qzone_group test_qzone_group_integration test_bridge test_group_chat
node test-qzone-private.mjs
```

2026-11-20 22:06（北京时间）：15项相关测试通过，另通过基于实际线上代码的模拟命令分发验证。实际执行一次点赞，回读同一说说 `liked=true`，小c仍 `online=true`、`good=true`。未评论、发说说或新增调度。

线上备份：`bridge/.private/backup-qzone-20261120-220541/`。实际验证结果：`bridge/.private/qzone-verification.json`。

2026-11-20 22:40（北京时间）：40项Python检查、私聊JS身份/引用/附件/失败检查、线上插件依赖导入及真实Room双源去重检查通过。大肥鱼通过实际JS私聊处理器与Python入口执行一次真实点赞；两个账号均身份正确、在线且回读 `liked=true`。用真实OneBot接口在临时群聊上下文验证两号分别返回“已经点过赞”，没有再次点赞，也没有向QQ群发送测试消息。实际群SSE触发和群内回执尚待用户发送命令验证。

本轮备份：`bridge/.private/backup-qzone-both-20261120-223927/`。验证结果：`bridge/.private/qzone-both-verification.json`。

本机另验证42项检查通过，含本地版本额外的两项群聊回归；Windows隔离入口禁止真实模型调用，并在旧测试离开临时目录前关闭SQLite连接，以适配Windows文件锁。服务器40项检查直接在Linux运行，未使用这些适配。
