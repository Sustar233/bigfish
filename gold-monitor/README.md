# 小 C 金价提醒

- 标的：上海黄金交易所 Au99.99，人民币元/克，官网延时行情。
- 每个北京时间整点检查；低于 810 或高于 890 时私聊本人（1000000001），发送账号为小 C（1000000002）。
- 等于边界不触发；相对上次预警报价累计上涨或下跌达到 10%（含）也触发，一次检查至多发一条。回到区间后重新武装；直接跳到另一侧会触发另一侧提醒。
- 第一次有效报价若已越界，立即提醒。有了预警基准后，回到区间内也检查 10% 涨跌。
- 校验合约、最新价列、价格有效性与行情日期。旧行情、抓取失败不会触发价格提醒。
- 官网直连在本服务器超时，使用现有本地代理读取官网；保留同一官网手机页面及直连备用路径。不调用 AI 模型，不消耗 Codex 或 DeepSeek 额度。
- QQ 离线时暂存事件；下次有效检查若触发条件仍成立才再尝试，回到区间则取消过时提醒。发送结果不确定时保留记录，不自动重发。
- 数据与去重状态保存在服务器 `.private/state.sqlite3`，重启不丢失。
- QQ 登录状态仍由 QQ 平台决定；需要保持小 C 在线。

本人私聊大肥鱼可直接说「把金价预警下限改成800，上限改成920」「金价预警上限调到930」「金价预警上下限是多少」。金额单位为元/克，下次整点检查采用保存后的设置。

服务器目录：`/home/ubuntu/gold-watch`。

```sh
python3 /home/ubuntu/gold-watch/gold_watch.py --status
python3 /home/ubuntu/gold-watch/gold_watch.py --dry-run
systemctl list-timers gold-price-watch.timer
sudo journalctl -u gold-price-watch.service -n 20 --no-pager
sudo systemctl stop gold-price-watch.timer  # 暂停后续检查
```

来源：https://www.sge.com.cn/sjzx/yshqbg

仅按每小时抽样到的官网延时报价判断，不保证捕获两次检查之间短暂发生的越界。

部署验证：2026-11-16 17:13，首次正式检查成功，报价 828.5 元/克，未越界且未发消息。10 项测试通过，定时器 active/enabled，下一次检查 18:00。
