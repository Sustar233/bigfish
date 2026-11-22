# 小家：客厅与私人控制台

**2026-11-22 已按用户明确授权上线。** 入口为现有 HTTPS 后台 origin 的 `/home/`，原个人主页导航已增加“小家”。使用现有后台管理员账号登录。

## 页面与功能

- 客厅：原创 SVG 小屋，大肥鱼与小 c 住户卡片，QQ 登录状态。
- 控制台：两号私聊、三人群聊、新闻快报、晚间简报、天气、知乎日报、金价提醒，共八个独立开关。
- 登录恢复：复用已有小 c 登录脚本；在线不刷新，等待手机确认时不打断；仅管理员发起时获取新二维码。二维码不写入控制台磁盘或日志。
- 用量：读取当日 CSV 的真实 token 与缺失计数；读取备线有效流量，不展示订阅凭据，也不推算费用或订阅余额。
- 操作记录：私密 SQLite 保存时间、功能、目标状态及读回结果，不包含聊天正文。

网页位于既有 HTTPS origin 的 `/home/`。沿用现有 Harness 管理员账号，不创建新账号、不修改口令。原 HTTP 个人页只新增小家链接，不显示私密状态。

## 权限与操作语义

每个页面和 API 请求都调用现有 `/auth/verify`，仅接受认证系统返回的 `admin` 角色，忽略浏览器自报身份。修改请求同时校验固定 HTTPS Origin 和与会话绑定的 CSRF token。静态资源固定白名单；私人响应禁止缓存；后台只监听 `127.0.0.1:13220`。

聊天暂停通过持久文件门控保留 QQ 登录及档案。小 c 在收消息、开始处理、发送前检查；大肥鱼在新私聊入口检查；群聊同时维护原数据库暂停状态并增加入口门控。已开始的发送、工具调用或通知可能完成，暂停期间的新消息不补答。群内原暂停状态也会读回到控制台。

通知开关使用 `systemctl enable/disable --now` 操作固定五个 timer。停止后续调度，不取消正在执行的 service，也不保证清空原投递队列。新闻完全暂停须同时关闭快报和晚报。所有开关修改后读回确认；旧页面不能覆盖其他入口的新设置。

受限 root helper 仅能操作固定 timer，另提供不含凭据的备线统计读取。没有终端、任意服务重启、任意命令、上传文件或账号删除接口。root helper 与源码安装到 root 拥有的 `/usr/local`，使用 Python isolated 模式，不从用户可写路径导入代码。

## 已完成验证

Windows 与 Linux 隔离副本测试覆盖：匿名访问、非管理员访问、伪造身份、跨站与 CSRF 拒绝、非法开关、并发旧版本、持久化、读回不一致与审计、路径遍历、群聊状态、受限 helper 命令白名单。前端 JavaScript 已通过语法检查。没有真实消息投递或付费模型调用。

`preflight.py` 只读核对线上三个模块的补丁锚点、幂等性和 Python/JavaScript 语法；不写线上文件、不调整开关、不重启服务。

上线验收：Windows、Linux 各16项隔离测试通过；真实管理员口令登录、私人页面及八项状态读取成功；小 c 暂停标记实际切换后恢复原设置；固定金价 timer helper 在服务沙箱中成功重设原状态；真实会话错误 CSRF 被403拒绝；验证会话已登出。两号QQ在线，七个相关服务均active，控制台开机启动已启用。没有发送QQ测试消息或调用模型。公网HTTPS证书检查与匿名登录重定向通过，匿名状态API返回401。浏览器视觉和手机实机效果尚未实测。

`verify_live.py` 仅在服务器由管理员运行：使用本机已有登录凭据完成一次端到端核验，绝不输出密码、Cookie或二维码；会短暂切换小 c 暂停开关并恢复，再重设金价 timer 的原状态。原凭据失效时停止，不猜测或重置密码。

## 已完成上线变更

1. 安装独立程序到 `/home/ubuntu/home-console`，状态存放其 `data/` 私密目录。
2. 注册 `bigfish-home.service` 并启用开机启动。
3. 安装 root 拥有的固定 timer helper 与对应 sudoers 规则；应用只能调用该 helper。
4. 在现有三个 QQ 模块增加小范围暂停门控，逐文件备份，保留线上其他补丁；不使用仓库基础文件覆盖。
5. 在既有 HTTPS Caddy 增加 `/home`、`/home/*` 路由，原 HTTP 主页导航增加小家链接。
6. 配置和代码校验通过后，短暂重启 `qq-chat`、`qq-group`、`deepseek-harness`、`caddy`；不重启 QQ 容器或服务器，不更改账号登录数据。

安装脚本在 `/home/ubuntu/home-console/deploy-backups/<UTC时间>/` 保存逐文件副本与 manifest。失败会恢复原文件并重启原服务。手动回滚须先核对后续变更，按差异撤回本次门控与路由，再移除新 service、helper 和规则，保留状态及审计数据。

本次上线备份：`/home/ubuntu/home-console/deploy-backups/20261122T021354Z/`。服务端先运行隔离检查和只读预检，再安装；安装包可附带仓库 `server-maintenance/smallc_login.py` 作为登录脚本依赖。源码仓库内直接运行安装器时也会查找该相对路径。运行程序只从 `/home/ubuntu/home-console/` 加载，staging 不是线上站点。

## 本地检查

```powershell
python -m unittest discover -s server-deploy/home-console -p test_home.py -q
node --check server-deploy/home-console/app.js
```

HTTP 测试需回环联网权限。测试只使用临时目录和 mock，不调用生产开关。
