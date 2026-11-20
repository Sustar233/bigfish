# 大肥鱼个人测试页

访问：<http://192.0.2.10/>（公网 HTTP 测试入口，暂无域名与 HTTPS）。

这是独立静态页面，没有依赖、数据库或表单后端。暖白、墨黑、青柠绿视觉，包含响应式布局、原创 SVG 插画、作品概念弹窗、锚点导航与复制链接。介绍与作品为演示文案，联系方式未配置。

- 本地源码：`index.html`
- 服务器源码：`/home/ubuntu/personal-page/index.html`
- Caddy 静态目录：`/srv/personal-page`，只发布 `index.html`
- 入口：`/etc/caddy/Caddyfile` 的 `http://192.0.2.10` 块
- 首次配置备份：`/etc/caddy/Caddyfile.before-personal-page.20261116T154806Z`

修改页面后，上传本目录的 `index.html` 和 `deploy.py` 到服务器 `/home/ubuntu/personal-page/`，再运行 `sudo python3 /home/ubuntu/personal-page/deploy.py`。脚本仅接受原空 HTTP 块或本页创建的配置，备份配置、验证后发布；Caddy 管理接口已关闭，因此使用服务重启。其他 HTTPS 路由保持原配置。现有 WebUI 管理器日后重写 Caddyfile 时可能覆盖该入口。

2026-11-16 核验：Caddy 配置校验通过；服务器本机与 Windows 公网请求均 HTTP 200；Caddy、QQ 和代理服务均 active；内联 JavaScript 语法及导航目标检查通过。内置浏览器对公网 HTTP IP 返回 ERR_BLOCKED_BY_CLIENT，尚未完成浏览器视觉和手机实测。
