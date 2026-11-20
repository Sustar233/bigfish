# 服务器版知乎日报（Codex 订阅额度）

部署目录 `/home/ubuntu/dailyZhihu`。北京时间每天 08:00 开始生成。

已于 2026-11-13 完成正式 systemd 环境的完整试跑：10 个话题、20 条回答，21:57:50 经 QQ SMTP 向 owner@example.com 发送 HTML 附件。服务正常退出，发送记录已保存，无遗留发送占位。Codex 使用 ChatGPT 账号订阅登录；已通过小型模型调用验证。程序现有 40 项测试通过。

`zhihu-daily.timer` 已启用并处于 active 状态，下一次运行：2026-11-14 08:00（Asia/Shanghai，与北京时间相同）。代理开机自动启动；电脑关机不影响服务器任务。

## 当前方案

Python 使用知乎官方接口抓取热榜与回答；Codex CLI 通过 ChatGPT 登录处理当前批次的英文精读与中文翻译；Python 校验、缓存并生成 HTML，再用国内邮箱 SMTP 发出附件。

`LLM_PROVIDER=codex` 为默认设置，模型额度用尽或登录失效时停止，不会自动切换付费 DeepSeek/OpenAI API。具体可用额度以账号套餐为准。

Codex 通过 `/home/ubuntu/.local/bin/codex-proxy` 启动，使用 `127.0.0.1:17891` 上的 Xray VLESS 客户端。代理由 `codex-proxy.service` 开机启动。该端口只监听服务器本机；系统默认网络及原 Harness 服务未修改。节点凭据在 `/home/ubuntu/.config/codex-proxy/config.json`，权限 600。

## 账号与邮件配置

```bash
# 本人打开官方页面并输入一次性代码完成授权
~/.local/bin/codex-proxy login --device-auth
~/.local/bin/codex-proxy login status
```

服务器上执行 `nano /home/ubuntu/dailyZhihu/.private/server.env`，填写：

```text
ZHIHU_ACCESS_SECRET=已授权迁移的知乎访问凭据
LLM_PROVIDER=codex
DELIVERY_MODE=smtp
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=发件QQ邮箱完整地址
SMTP_PASSWORD=邮箱SMTP授权码（不是网页登录密码）
SMTP_FROM=发件QQ邮箱完整地址
```

收件人沿用 `preferences.json`。其他国内邮箱使用其官方 SMTP 主机，支持 465 隐式 TLS 或 587 STARTTLS。不在聊天或代码仓库中提交凭据。

```bash
chmod 600 /home/ubuntu/dailyZhihu/.private/server.env
cd /home/ubuntu/dailyZhihu
python3 server_runner.py --check
# 仅抓取，不使用模型额度，不发邮件
python3 server_runner.py --collect-only
# 完整运行：使用 Codex 订阅额度并发出邮件
python3 server_runner.py
# 完整试跑成功后启用调度
sudo systemctl enable --now zhihu-daily.timer
systemctl list-timers zhihu-daily.timer
```

## 运维与恢复

日志：`journalctl -u zhihu-daily.service --no-pager -n 60`。
代理状态：`systemctl status codex-proxy.service`。
每日成品：`archive/YYYY-MM-DD.html`；最新成品：`output/zhihu-daily.html`；最近成功状态：`output/server-status.json`。

模型只接收当前未完成的语言批次，不接收知乎凭据或邮箱授权码；Codex 子进程环境移除这些凭据及付费 API Key，禁用 shell 工具和联网搜索，运行于只读沙箱及独立临时目录，用 JSON Schema 约束输出。

定时器使用明确的 Asia/Shanghai 时区；开机后补跑漏掉的执行。同一收件人当天已记录成功则跳过。锁防止并发；答案缺失时不交付；每批语言结果立即缓存；失败以非零退出，不无限重试。

SMTP 结果不确定时保留 `output/pending-delivery.json`，停止自动重发。先核实发件箱，再使用原 pipeline 的 record/release 流程处理；不要直接删除占位。SMTP 接受邮件表示已提交，最终送达以邮箱为准。

原 F: 盘项目及 Codex App 的暂停任务保持原状态。服务器使用独立缓存。更换模型后需人工抽查一次语言质量。
