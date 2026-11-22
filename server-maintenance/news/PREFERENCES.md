# 共享新闻偏好

线上生效文件为 `/home/ubuntu/server-maintenance/news/.private/preferences/interest_preferences.json`。小 c 私聊、大肥鱼私聊和桌面 Codex 共用 `news_preferences.py`。新闻推送从该文件读取权重、编辑规则和反馈。新增入口也接这个模块，用户的运行配置留在服务目录。

小 c 支持「查看新闻偏好」「以后多推科学新闻」「新闻偏好改成……」和 `/新闻偏好 规则 数学突破：优先关注重大数学成果`。肥鱼按自然语言使用 `shared_news_preferences`。两个号可以通过新闻序号或事件编号评价已发布的内容。桌面 Codex 经现有 SSH 入口调用 `/home/ubuntu/server-maintenance/news/news_preferences.py`，通过标准输入传结构化操作，回读结果再确认成功。

权重 1 为正常，0 过滤普通消息。重要数学、AI 和基础科学突破提高优先级，局部战事通常降级，重大的外溢影响或人道危机保留核验入口。科学进展区分正式公布、独立复核和正式认可。

## 其他功能的配置归属

| 功能 | 线上权威位置 |
|---|---|
| 新闻兴趣、规则、反馈 | `server-maintenance/news/.private/preferences/interest_preferences.json` |
| 两号定时提醒 | `qq-reminders/data/reminders.sqlite3`，按发送账号隔离，通过 `qq-reminders` 服务维护 |
| 知乎日报选材和交付 | `dailyZhihu/preferences.json` |
| 金价提醒阈值 | `gold-watch/.private/config.json`，由 `gold-watch/gold_limits.py` 和监控任务共用 |
| 定时服务开关 | systemd 中实际运行的各业务 `.timer`，网页控制台操作同一批定时器 |
| 小 c 私聊语音和表情 | `qq-codex/bridge/.private/media-settings.json`，按小 c 账号维护 |

以上相对路径均位于 `/home/ubuntu`。桌面、QQ 和网页入口维护业务设置时调用对应服务的读写接口。聊天档案、人物记忆和项目源码不作业务设置的事实来源。
