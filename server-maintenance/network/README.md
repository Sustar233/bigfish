# 选择性代理与计费备线

服务器入口仍为 `127.0.0.1:17891`，由既有 Xray 内核运行，不开启 TUN 或系统全局代理。订阅只提取必要 VMess 节点，没有导入订阅的全局规则、脚本或自动测速。

- 默认 DIRECT。QQ、DeepSeek、国内服务、GitHub、软件更新和其他未列入规则的域名不走计费备线。
- OpenAI/ChatGPT 的 HTTPS 使用日本备选节点；BBC RSS、Guardian、Le Monde、Al Jazeera 使用香港备选节点；上金所使用已验证可读取完整行情的美国节点。具体白名单以生产配置中 `restricted-ai`、`restricted-web`、`restricted-gold` 三条规则为准。
- 原线路独立保留在本机 `17890`，每分钟探测一次。恢复后白名单业务自动切回原线路；原线路失效时才使用备线。切换会重启代理，已有代理连接可能短暂中断。
- 金价、新闻、天气抓取均先尝试直连，失败才尝试本机选择性代理。
- 不对备选节点做定时测速，不用备线下载软件或抓取媒体。搜索结果中的任意外部网页仍默认直连；需要新增代理站点时，经实际故障核实后逐项加入白名单。
- 每日 1 GiB（2026-11-21 确认保留线上值），提前 2 MiB 停用备线，次日北京时间重新计算。达到阈值只阻断需要代理的业务，直连和原线路恢复探测继续。计量故障也停止备线。
- 这是按分钟检查的保护阈值，并非运营商硬限额。Xray 记录的出站有效字节不含全部协议开销；服务商账单为准。大流量连接在两次检查间仍可能超额。

维护根：`/home/ubuntu/server-maintenance/network`。

| 入口 | 用途 |
|---|---|
| `policy.json` | 每日字节阈值、提前停止余量，下一分钟自动读取 |
| `status.json` | 最近检查、当前路线、当天备线累计有效字节 |
| `traffic_guard.py` | 原线探测、备线计量、自动切换 |
| `.private/traffic_state.json` | 跨重启的计费保护状态，不应删除 |
| `.private/original-full.json` | 修改前原代理配置备份，仅本机私密保存 |
| `.private/original-probe.json` | 原线路探测实例配置 |
| `.private/backup-subscription.url` | 订阅地址，权限 600，不进入文档或日志 |
| `/home/ubuntu/.config/codex-proxy/config.json` | 实际分流配置，包含节点凭据，权限 600 |

```sh
sudo cat /home/ubuntu/server-maintenance/network/status.json
systemctl status codex-proxy original-proxy-probe network-route-guard.timer --no-pager
sudo journalctl -u network-route-guard -n 10 --no-pager
cd /home/ubuntu/server-maintenance/network && python3 -m unittest -v test_traffic_guard
```

配置中的统计 API 仅监听 `127.0.0.1:17895`；全部代理端口均不向公网开放。调度使用服务器 systemd，与个人电脑是否在线无关。

暂时停用备线：将 `policy.json` 的 `daily_backup_limit_bytes` 设为 `0`，随后 `sudo systemctl start network-route-guard.service`。不要只停止 timer，停止 timer 不会关闭当前备线连接。

原订阅失效或原线路凭据改变时，需人工更新 `.private/original-full.json`、`.private/original-probe.json` 和生产配置中的 `original` 出站，测试后重启原线探测服务。自动恢复只检测当前保存的原线路，不会猜测新订阅凭据。

备选订阅目前为手动刷新，避免静默改变节点及费用路径。刷新时直接下载订阅、仅提取节点、暂存验证并备份，再更新生产中的三个备选出站；不能导入订阅的全局规则或做全节点测速。
