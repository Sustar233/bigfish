# 腾讯云 Codex 与 VLESS 运行记录

服务器：43.142.167.150，用户 ubuntu。

- VLESS 节点：使用本机 v2rayN 当前生效的 VLESS + REALITY 节点；不在此文件保存地址、UUID 或其他节点凭据。
- Xray：26.11.9，来自 XTLS/Xray-core 官方 GitHub Release；SHA-256 已对照官方 dgst 并在服务器再次校验。
- 代理入口：http://127.0.0.1:17891，仅监听服务器回环地址。
- 服务：codex-proxy.service，已启用开机启动。
- 节点配置：/home/ubuntu/.config/codex-proxy/config.json，目录权限 700，文件权限 600。
- 启动 Codex：~/.local/bin/codex 或 ~/.local/bin/codex-proxy。代理环境只对这个命令及其子进程生效。
- Codex 安装目录：/home/ubuntu/.local/codex，官方 npm 包 @openai/codex@0.169.0。
- 登录：~/.local/bin/codex-proxy login --device-auth，由用户在官方页面完成授权。
- 登录状态：~/.local/bin/codex-proxy login status。
- 代理状态：systemctl status codex-proxy.service。
- 停用代理：sudo systemctl disable --now codex-proxy.service。

验证：通过代理访问 ChatGPT 返回 200，Codex Responses 接口对未认证 HEAD 返回 405，官方设备登录页返回 302；这证明网络已可达，不代表账号已登录或已完成模型调用。

日报使用 Codex 的说明见 dailyZhihu/README-server.md。日报定时器在账号与 SMTP 配置补齐、完整试跑成功前保持禁用。
