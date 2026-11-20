# 小c长沙早间天气

固定QQ账号1000000002，私聊1000000001。每天北京时间06:00发当天长沙城区天气，按口语化人设报信；不调用模型生成事实，避免Codex额度/路由故障阻止天气推送。

- 位置：长沙城区28.2282°N、112.9388°E，非精确住址。
- 上班08:30–10:00，下班18:00–19:00，读取与通勤区间重叠的逐小时降水概率及降水量，明确概率是单小时最高值，不能当作整个通勤段的概率。
- 天气主源为MET Norway，遵守同一全球预报3小时缓存要求；备用Open-Meteo。MET Norway的next_1_hours按未来一小时转换，缺概率只说明降水信号，不捏造百分比。气温为06:00至今晚逐小时范围。Open-Meteo降水时间表示前一小时：早高峰使用09:00和10:00；晚高峰使用19:00。不能把18:00对应的17–18点误当晚高峰。
- 空气：CAMS / Open-Meteo模型估算，展示美标AQI、相应等级和PM2.5；明确区别于中国AQI及站点实测。超过2小时或缺失的数据不报具体值。
- QQ离线或天气获取失败：06:00–08:20每10分钟重试；成功每天仅一条。发送结果不确定或进程在发送中中断时不自动重发。
- 08:20之后不补发；不把昨日天气当今日。失败记录在`.private/weather.sqlite3`，只记录状态，不保存令牌或聊天正文。
- 正常调度由服务器systemd timer执行。Codex每日自动任务仅作同一入口的补偿执行；共用文件锁和数据库去重，不额外生成第二条天气。
- 用户指定06:00发送，属于新闻23:00–08:00免打扰的明确单独例外。

```sh
python3 /home/ubuntu/server-maintenance/weather/weather_morning.py --dry-run
python3 /home/ubuntu/server-maintenance/weather/weather_morning.py --status
systemctl list-timers changsha-weather.timer
sudo journalctl -u changsha-weather --no-pager -n 20
sudo systemctl stop changsha-weather.timer
```

暂停时同时暂停Codex中的“小c长沙早间天气”补偿自动任务，避免单独停timer后补偿任务仍投递。

数据定义：https://open-meteo.com/en/docs ，https://open-meteo.com/en/docs/air-quality-api 。按来源要求在消息中署名Open-Meteo和CAMS。预报只表示获取时的模型结果，城区不同地点及临近出门时仍可能变化。
