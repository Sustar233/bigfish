# 服务器功能与维护总目录

2026-11-22“小家”私人控制台已上线：既有 HTTPS 后台的 `/home/`，使用现有管理员登录；管理两号私聊、三人群聊及五项通知定时器。服务 `bigfish-home`，入口 `/home/ubuntu/home-console`，详细语义、核验和回滚见 [控制台说明](../server-deploy/home-console/README.md)。不停止QQ容器或清除档案，暂停前已执行的任务可能完成。

2026-11-22新增重连补发：小c在线核验成功后及时补当天漏送天气、仍有效的已生成新闻和未送达的有效金价越界告警。复用原巡检与原任务回执，不新增定时器；原暂停状态、新闻免打扰和金价阈值保持。详见 `recovery/README.md`。

2026-11-22新增小c临时接待：确认QQ离线时大肥鱼用自己的账号接待；仅模型不可用时使用小c原号的“大肥鱼值班”话术。临时接待拦住本人所有新功能请求，不排队或恢复补做；原有后台监控配置保持。复用既有巡检恢复常态，详见 `standby/README.md`。

小c快速重登（本机）：`pwsh -NoProfile -File ./server-maintenance/smallc-login.ps1`；扫码确认后加 `-Mode Verify -WaitSeconds 15`。直接检查小c，离线等待扫码时主动刷新并保存新二维码到本机私密目录；在线时保持登录。工作区 `AGENTS.md` 已登记优先使用该入口，细节见 `CODEX-MAINTENANCE.md`。

维护入口：`/home/ubuntu/server-maintenance/README.md`。服务器 `192.0.2.10`，日常用户 `ubuntu`，统一使用北京时间 `Asia/Shanghai`。

本文件归纳所有已知业务功能。现有程序保留实际部署路径，通过总目录统一查找；不要直接移动运行中的项目。`services.json` 是机器可读索引，`status.py` 是只读状态检查，不输出凭据或聊天正文。

```sh
python3 /home/ubuntu/server-maintenance/status.py
systemctl --failed --no-pager
systemctl list-timers --all --no-pager
```

常驻服务的 `active/running` 只代表进程存在；QQ 要额外检查 `online/good`。定时任务在两次执行间 `inactive/dead` 正常，应看最近 `Result`、`ExecMainStatus` 与 timer 的下次时间。

## 功能速查

| 功能 | 程序/数据根目录 | 服务和调度 | 使用的模型/费用路径 |
|---|---|---|---|
| 小 C QQ 私聊 | `/home/ubuntu/qq-codex` | `qq-account`、`qq-chat`，常驻 | Codex，ChatGPT 登录额度 |
| DeepSeek QQ、网页后台 | `/home/ubuntu/qq-dsh`、`/home/ubuntu/.dsh` | `qq-dsh-account`、`deepseek-harness`，常驻 | Harness 现有 DeepSeek 配置 |
| 固定三人群聊 | `/home/ubuntu/qq-group` | `qq-group`，本人触发 | 双方各自模型配置 |
| 世界新闻快报/简报 | `/home/ubuntu/server-maintenance/news` | 每15分钟；21:00简报 | 有候选时调用 Codex，每天最多10次调用尝试 |
| 人民币金价提醒 | `/home/ubuntu/gold-watch` | `gold-price-watch.timer`，每小时整点 | 不调用模型 |
| 双语知乎日报 | `/home/ubuntu/dailyZhihu` | `zhihu-daily.timer`，每天08:00 | Codex，ChatGPT 登录额度；SMTP投递 |
| QQ 档案维护、健康检查 | `/home/ubuntu/qq-memory` | `qq-maintenance.timer`，每2分钟 | 普通程序 |
| QQ 加密备份 | `/home/ubuntu/qq-memory/backups` | `qq-backup.timer`，每天03:30 | 普通程序 |
| 出站代理 | `/home/ubuntu/.config/codex-proxy` | `codex-proxy`，常驻 | 本机 Xray，127.0.0.1:17891 |
| 网页入口/认证 | `/etc/caddy`、Harness配置目录 | `caddy`、`dsh-auth-caddy` | 不调用模型 |
| SSH管理 | `/etc/ssh` | `ssh` | 远程运维入口 |

表中服务名省略 `.service`，定时器名保留 `.timer`。

## 小 C：账号、程序、记忆与权限

- 账号 `1000000002`；允许本人 `1000000001` 的私聊。QQ 在 Docker 容器 `qq-account` 中运行。
- 聊天桥：`/home/ubuntu/qq-codex/bridge/bridge.py`。
- 会话策略：同目录 `chat_context.py`。每轮提供北京时间、消息时间；空闲2–6小时缩短上下文，超过6小时默认新话题；档案不删除。
- 记忆/档案：`bridge/.private/records/archive.sqlite3`；短期上下文：`bridge/.private/chat.sqlite3`。
- 风格：`bridge/chat_style.md`；已批准角色：`bridge/.private/records/persona.md` 与批准标记。修改角色后需维护其批准哈希，不可只改正文。
- 配置：`bridge/.private/config.json`，包含 OneBot 凭据，权限600；不要打印或复制到文档。
- OneBot：127.0.0.1:13001；NapCat管理页：127.0.0.1:13080。保持仅本机监听。
- 普通公开搜索与实时查询由独立检索进程处理；私人记忆不传入搜索任务。Shell、应用插件、hooks和多代理仍关闭。
- 新增 `/新闻状态`、`/新闻反馈 N编号 重要|不感兴趣|少推这类`；反馈仅影响选题偏好，不扩大权限。

```sh
systemctl status qq-account qq-chat --no-pager
sudo journalctl -u qq-chat -n 30 --no-pager
sudo systemctl restart qq-chat  # 更新代码后重启聊天桥
```

若 QQ 日志提示身份失效，需要手机QQ重新扫码确认。不要反复重启整个服务器；重启聊天桥不能替代QQ本人授权。

2026-11-16 已发生多次平台登录失效；不能保证一次扫码后永久在线。新闻和金价监控会处理 QQ 暂时离线，重新登录后再按有效性规则投递。

## DeepSeek QQ 与网页后台

- 账号 `1000000003`；容器 `qq-dsh-account`。QQ 数据在 `/home/ubuntu/qq-dsh/napcat-runtime`。
- Harness 在 `/home/ubuntu/.dsh`；QQ 接入使用已安装的 OneBot 插件，常驻服务 `deepseek-harness`。
- OneBot HTTP/SSE：127.0.0.1:13101；WebSocket：127.0.0.1:13102；管理页：127.0.0.1:13180。
- 私聊档案：`/home/ubuntu/qq-dsh/records`。不把此账号模型额度与 Codex 混淆。

```sh
systemctl status qq-dsh-account deepseek-harness --no-pager
sudo journalctl -u deepseek-harness -n 30 --no-pager
```

原始 QQ/Harness 日志可能包含聊天内容或登录二维码，不要直接对外分享。

## 三人群聊

- 固定群 `1000000004`，仅本人和两个机器人；程序 `/home/ubuntu/qq-codex/bridge/group_chat.py`。
- 数据 `/home/ubuntu/qq-group/records`；调度状态 `/home/ubuntu/qq-group/.private/control.sqlite3`。
- 只有本人消息触发，每轮最多两条AI回复；保留每分钟/小时/日预算和群成员校验。
- 2026-11-19：普通群聊无需 @，大肥鱼优先回应，小 c 保留原参与节奏；明确点名时优先对应角色。部署验证和回滚见 `GROUP-REPLIES-2026-11-19.md`。
- 群聊只自动检索群内资料，不自动引入双方私聊记忆。
- 群内可使用“暂停群聊”“继续群聊”“/群清空”“/群状态”；档案管理仍在本人私聊中进行。

```sh
sudo journalctl -u qq-group -n 30 --no-pager
sudo systemctl restart qq-group
```

## 世界新闻提醒（试运行）

- 程序：本目录 `news/news_watch.py`；规则：`news/config.json`。
- 状态与发送队列在 `news/.private/news.sqlite3`。小c、肥鱼、桌面 Codex 和定时推送使用 [同一份新闻偏好指南](news/PREFERENCES.md)，其中也保存对已推送新闻的反馈。
- 每15分钟采集多个公开RSS及USGS数据。消息发布时间、合约式来源ID、原始报道方与文章链接经程序校验。
- 普通重大快报要求至少两个独立原始报道方，并观察到真实联网交叉核实调用。转述同一通讯稿不算独立来源。
- 达到规则的重大地震可按USGS官方记录直接提醒；不推断伤亡或海啸。
- 本地每天重大快报最多3件；更正优先。同一事件合并，通常至少间隔6小时且存在实质性进展才再次通知。
- 每晚21:00简报，目标5–8件；依据不足时不凑数、不发空简报。21点调度重叠时，后续15分钟检查会补做当晚简报。
- 23:00–08:00免打扰；仍采集，次日合并仍有效的待发送消息。队列18小时过期，过时内容不补发。
- Codex每日最多10次编辑调用尝试（包括失败），快报预留2次额度供晚报；不自动切换付费API。
- 断网、源故障、模型失败、无重大新闻分别记录。QQ发送结果不确定时保留状态，不自动重发。
- 新闻仅输出原创短摘要和来源链接；不复制完整文章，不给出确定的市场涨跌预测。

```sh
python3 /home/ubuntu/server-maintenance/news/news_watch.py --status
python3 /home/ubuntu/server-maintenance/news/news_watch.py --dry-run  # 采集但不编辑、不发送
systemctl list-timers news-watch.timer news-digest.timer
sudo journalctl -u news-watch -u news-digest -n 30 --no-pager
sudo systemctl stop news-watch.timer news-digest.timer  # 停止后续调度
```

修改规则后下一次执行自动读取；代码更新后下一次oneshot执行自动使用新代码。不要删除发送队列来“强制重发”，先核对是否已送达。

## 人民币金价提醒

- 程序 `/home/ubuntu/gold-watch/gold_watch.py`；配置 `.private/config.json`；状态 `.private/state.sqlite3`。
- 上金所 Au99.99，人民币元/克，官网延时行情；每小时整点检查，低于810或高于890提醒，等于边界不触发。
- 同侧持续越界只提醒一次，回到区间重新武装；重启保留状态。旧行情或异常值不触发。
- 官网通过现有本地代理访问；没有模型调用和模型额度消耗。
- QQ离线先排队；下次有效检查仍越界才发送，回到区间则取消旧提醒。

```sh
python3 /home/ubuntu/gold-watch/gold_watch.py --status
python3 /home/ubuntu/gold-watch/gold_watch.py --dry-run
sudo journalctl -u gold-price-watch -n 20 --no-pager
sudo systemctl stop gold-price-watch.timer
```

## 知乎日报与邮件投递

- 入口 `/home/ubuntu/dailyZhihu/server_runner.py`；偏好 `preferences.json`；私密环境 `.private/server.env`。
- `LLM_PROVIDER=codex`，使用 ChatGPT 登录额度。文件中保留的 DeepSeek 模型项不代表正在调用它。
- 每天08:00生成；输出 `output/zhihu-daily.html`，归档 `archive/YYYY-MM-DD.html`。
- `output/server-status.json` 是最近运行状态；发送历史与 `output/pending-delivery.json` 用于防重复。
- 2026-11-16修复空双语摘要问题：非空Schema、局部有限重试，原校验不放宽。当天已成功补发。
- SMTP发送结果不确定时会留占位；核对发件箱后再处理，不直接删除占位重发。

```sh
python3 /home/ubuntu/dailyZhihu/server_runner.py --check
sudo journalctl -u zhihu-daily -n 40 --no-pager
systemctl list-timers zhihu-daily.timer
```

完整运行会实际生成并可能发送邮件。需要仅试生成时用 `DELIVERY_MODE=server_file`，不要未经核对重复执行投递。

## 代理、网页入口与SSH

- 代理服务 `codex-proxy`，配置 `/home/ubuntu/.config/codex-proxy/config.json`，启动包装器 `/home/ubuntu/.local/bin/codex-proxy`。
- 代理凭据不进入文档；127.0.0.1:17891 不对公网开放。
- Caddy 主配置 `/etc/caddy/Caddyfile`；认证边缘服务 `dsh-auth-caddy` 使用其服务定义指定的持久化来源。`/run/dsh-auth-caddy/Caddyfile` 属运行时文件，不作为长期编辑入口。
- 公网入口80/13600，内部网页服务8080/3080；入口含访问控制，不把隐蔽路径或登录凭据写入此总目录。
- SSH端口22，用户ubuntu。聊天角色不具备SSH/sudo工具；运维通过管理通道执行。

## 维护、备份与升级

- 自动维护入口：`/home/ubuntu/qq-codex/bridge/qq_maintenance.py`；维护根 `/home/ubuntu/qq-memory`。
- QQ加密备份：`/home/ubuntu/qq-memory/backups/*.qqbak`；恢复需要对应解密私钥。不要用公开加密钥代替恢复私钥。
- 新功能数据库另有状态/防重复记录；升级前用 SQLite backup 创建一致性快照，不直接复制活跃WAL数据库主文件。
- 小 C 时间/搜索升级备份：`/home/ubuntu/qq-codex/bridge/.private/backup-time-search-20261116-163306`。
- 日报修复备份：`/home/ubuntu/dailyZhihu/.private/repair-20261116-112211`。
- 代码更新先暂存测试，再替换；QQ聊天桥更新前检查是否有生成/发送中的消息。
- 文档和索引可统一维护，但历史程序路径、systemd入口、私密数据不能只搬目录不改引用。

新增功能时同步更新本文件和 `services.json`，写清入口、配置、数据、调度、日志、费用路径、暂停和故障恢复方法。所有密钥、口令、登录二维码及私人聊天正文都留在私密目录。

## 本次部署验收

已创建 entries/ 项目符号链接入口。最终新闻与QQ回归共55项通过；10个来源首次采集成功；晚报样稿8件已验证，未提前发送。新闻定时器每15分钟及21:00已启用。夜间只采集，08:00覆盖昨夜候选。

## 2026-11-17 收尾验收
- 日报08:05邮件提交成功，金价每小时检查正常。
- 昨晚新闻简报21:00首次失败、21:15自动补做成功；QQ失效时保留待发，本人扫码后已补发并取得QQ消息编号。
- 修复简报成功后旧错误标记不清除的问题。新闻15项、桥接41项，共56项回归测试通过。
- 发送是否成功以持久化 outbox 的 sent 状态及 message_id 为准，不能只看 systemd Result=success。

## 每日各项目token记录
入口：usage/README.md。每日CSV/Markdown：usage/data/daily/YYYY-MM-DD.csv或.md；总表usage/data/daily_totals.csv。
金价与普通维护记0；Codex与DeepSeek按本地可取得的真实usage记录，缓存不重复累加。2026-11-17 10:14起接入Codex，历史无usage明确标为缺失，不估算。按北京时间归档；无需模型来统计。


Codex and QQ maintenance scope / quota query: `CODEX-MAINTENANCE.md`.


小c长沙天气：每天北京时间06:00，关注08:30–10:00及18:00–19:00通勤降水、气温和空气模型估算。详见 weather/README.md。所有文字、语音和主动通知采用口语化人设，见 weather/CHAT-STYLE-OVERRIDE.md。

选择性代理和计费备线见 [network/README.md](network/README.md)。默认直连，必要域名才走备线，原线路恢复自动切回。每日备线保护阈值为 1 GiB，状态见 `network/status.json`。
2026-11-18新闻表达优化：内部N编号仅用于后台定位，日常快报不显示；使用口语摘要，可自然询问刚才那条新闻的来源或说这条新闻少推这类。旧编号查询仍兼容。


2026-11-19 新闻口语化：取消普通快报的重复固定开场，同批同日日期只交代一次；按实际发送时的北京时间转换今天/昨天，并按入队日期校正旧的相对时间，防止跨午夜错误。历史、跨年、无效日期与日期区间测试通过。加强自然口述及声明归属要求。26项新闻与偏好检查通过；未发送测试通知、未重发已送达消息。
