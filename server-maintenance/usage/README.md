# 每日各项目 token 记录

服务器入口：`/home/ubuntu/server-maintenance/usage`。

- 每日表格：`data/daily/YYYY-MM-DD.csv`，同名 `.md` 可直接阅读。
- 全日期汇总：`data/daily_totals.csv`（UTF-8 BOM，可用 Excel 打开）。
- 原始账本：`data/.private/usage.sqlite3`，只记录时间、项目、计数、来源与调用状态，不保存提示词、回复或密钥。

记录金价监控、新闻监控、知乎日报、小 C 私聊、小 C 群聊、DeepSeek 私聊/群聊、系统验证和普通维护。

金价与普通采集/备份不调用模型，记0。Codex读取真实 `turn.completed.usage`；聊天搜索和回复合成都归属对应私聊/群聊项目。DeepSeek读取本地 Harness `assistant/message.data.usage`，按日志路径与事件序号去重，忽略重复的流式快照。

字段：调用尝试次数、输入token（包含缓存）、缓存输入token（输入子集）、输出token、已记录总量、usage缺失次数、记录范围。**总量=输入+输出，缓存不再额外相加**。DeepSeek日志格式中的普通输入和缓存输入分开，导入时先统一成含缓存的输入口径。

2026-11-17开始接入 Codex 实时计量。安装前无usage的历史不能估算为真实消耗；能核实调用次数的历史仅记录次数并标记usage缺失。所有用量都缺失时数字留空。安装当天属于部分记录，后续按北京时间自然日归档。DeepSeek可回填本机仍保留的带usage日志，不能据此保证账号全量账单完整。

每次Codex调用结束自动更新报表；金价服务每小时结束后同步DeepSeek增量日志并更新报表。无需新增模型调用来统计。计量失败不会阻断聊天或定时任务，失败调用若缺usage会明确标注。token量不等于人民币费用，也不是订阅剩余额度。

```sh
python3 /home/ubuntu/server-maintenance/usage/usage_meter.py --sync-harness --export
cat /home/ubuntu/server-maintenance/usage/data/daily/$(date +%F).md
```

回滚代码备份在 `usage/.backups/`。对应service的 `token-usage.conf` 仅允许写 `usage/data`；金价服务另有导出报表的 ExecStartPost。
