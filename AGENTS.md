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
