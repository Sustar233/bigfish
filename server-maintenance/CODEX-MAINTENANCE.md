# 小c 与服务器 Codex 维护约定

2026-11-17：用户指定本聊天主要负责小c维护，同时负责服务器 Codex 的相关维护。

- 小c：QQ账号1000000002，现有总目录称“小c”；包括QQ接入、私聊/群聊桥接、登录状态、故障定位与恢复。
- Codex：CLI版本、ChatGPT登录状态、额度与重置时间、出站代理，以及服务调用失败的诊断。
- 其他业务仍以总目录登记的原有调度为准。本约定不新增定时任务或扩大临时掉线观察。
- 更新前核对兼容性和运行任务，保存必要备份；例行诊断不自动升级、清除登录数据或消耗额度重置券。

## 额度查询

服务器入口：

```sh
python3 /home/ubuntu/server-maintenance/codex_quota.py
```

脚本通过现有 Codex app-server 的 `account/rateLimits/read` 查询，不发起模型对话。只输出额度桶、窗口长度、已用比例及北京时间重置时间，不输出账号令牌。查询结束关闭本次创建的进程组。

交互式CLI也可在启动 `codex` 后输入 `/status`；`codex login status` 仅确认认证状态，不能替代额度查询。

2026-11-17实测：CLI版本0.169.0，ChatGPT认证仍有效；app-server初始化成功，但额度请求超时，经现有代理访问对应额度端点亦超时，代理service仍active。尚未取得服务器本次实时额度和重置时间，不能据此推断额度耗尽，也不能套用本地桌面账号的额度。脚本超时输出`unavailable`并返回非零退出码；后续须以成功返回的官方数据为准。

官方协议说明：https://learn.chatgpt.com/docs/app-server#6-rate-limits-chatgpt

## 临时掉线观察

已排除其他电脑端登录挤占；每6小时观察登录失效、兼容性及网络异常，连续7天可验证稳定后自动停用本轮临时观察。临时观察状态：`.private/qq-observation.json`；原有2分钟健康检查、备份等常规服务保留。
补充实测：交互式CLI独立启动（--no-daemon，不改共享后台服务）后，在account/read阶段返回 workspace routing discovery timed out (code -32603)，未能显示/status额度信息。本次查询阻塞在工作区路由发现，不能据此推断额度耗尽或具体重置时间。

2026-11-17补充实测：服务器Codex真实最小生成测试70秒超时。国内直连HTTPS返回200；通过代理访问Google及Codex端点超时；当前VLESS上游节点TCP连接亦超时，但codex-proxy保持active/running。当前证据指向上游节点连接故障，额度仍未知。未更改代理配置；探针用量归system_verification。
2026-11-19 用户统一命名：QQ1000000002今后在文字、语音、新闻、天气、邮件、群聊、表情和维护提示中统一称为小c。固定回复、风格文件、用量标签及两个既有自动任务已同步。24项现有语音与群聊检查通过；正确账号重新扫码后私聊与群聊均恢复。
2026-11-20：用户要求不控制本机键鼠。FlClash默认TUN路由造成SSH握手超时，ssh -b 192.0.2.20绑定以太网已验证正常；物理地址变化时先只读查询，不修改VPN或全局路由。小c昨晚18:53掉线，今早10:40重新扫码恢复，两QQ在线。DeepSeek QQ默认qq-natural-v3未开放Bash或Codex委派，群聊执行工具禁用，网页standard预设包含Bash；服务器Codex已登录但最小生成与代理TLS探针未通过。没有扩权。
