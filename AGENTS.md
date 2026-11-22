# 小c重登快捷流程

用户说“小c掉线”“重登小c”“重新登录小c”时，优先直接执行以下入口，不先重复扫描仓库、查询全部服务或读取聊天历史：

```powershell
pwsh -NoProfile -File ./server-maintenance/smallc-login.ps1
```

- 此入口自动从现有 known_hosts 找到服务器、选择当前物理网卡绕过TUN，直接查询小c；离线且等待扫码时主动刷新二维码。网络请求需要当前工具沙箱的联网权限，按正常审批机制执行。
- `scan_qr`：立即把返回的绝对 `image_path` 作为Markdown图片展示，让用户用小c账号手机QQ扫码。不要打印二维码base64、令牌、密码或原始QQ日志。
- 用户确认扫码后执行 `pwsh -NoProfile -File ./server-maintenance/smallc-login.ps1 -Mode Verify -WaitSeconds 15`。只在 `online` 且 `expected_account=true` 时确认登录恢复；需要确认聊天收发时，再检查私聊/群聊桥接连接。
- `online`：不刷新二维码，不重启服务，直接说明账号已在线；用户仍说不能回复时再诊断桥接/模型。
- `confirm_on_phone`、`verification_in_progress`、`initializing`：保留当前登录流程，提示用户完成现有确认或稍后复查，不重复刷新或密码重试。
- `qr_pending`：可再次调用入口获取新码；不展示旧图或声称已登录。其他错误、身份不符、SSH失败时才进入详细诊断。
- 不自动重启QQ容器、清除登录数据、改网络、升级QQ或加密集重登定时任务。二维码只保存在Git忽略目录 `.private/smallc-login/`。

此流程只针对小c；用户明确说大肥鱼掉线时按对应账号处理。原有项目改动与其他业务保持各自范围。

## 共享业务偏好

查看或修改新闻偏好时，经 `server-maintenance/connect-ssh.ps1` 调用服务器上的 `/home/ubuntu/server-maintenance/news/news_preferences.py`，用标准输入传 JSON，核对操作结果再回复。这个入口和小c、肥鱼共用同一份线上指南。其他业务先查 [配置归属](server-maintenance/news/PREFERENCES.md)，通过对应服务或配置更新。

## 服务器项目副本

在服务器路径 `/home/ubuntu/qq-owner-ops/workspace/bigfish` 中，处理本人私聊明确委托的养殖基地项目修改时，在此仓库内修改并运行相关检查。完成后检查差异，只提交本次任务修改的源码、测试、文档或配置模板，向本人报告提交短号和验证结果。凭据、聊天档案和运行数据保存在各服务的私有目录。部署到正在运行的服务属于单独操作，按本人当次委托范围执行。
