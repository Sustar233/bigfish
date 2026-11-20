# QQ 生图

2026-11-20：小c（1000000002）和大肥鱼（1000000003）可在本人1000000001的QQ私聊中接收：

```text
生图：一个可爱的小猪
生图: 一片星空下的鱼塘，水彩插画
/生图 一个可爱的小猪
/生图状态
```

每次一张，原账号回图；明确前缀触发，不经过普通聊天模型判断。当前只做文字生图，群聊、参考图编辑不在本次范围内。描述1–4000字，共用串行队列，最多4条等待/进行中的任务。两个角色的QQ收件人都固定为1000000001，不接收请求提供的目标、路径或命令。

## 运行

- 入口 `/home/ubuntu/server-maintenance/images`；常驻 `qq-image-generation.service`。
- 内部HTTP仅监听127.0.0.1:13210，Bearer令牌在`.private/client-token`，权限600；不对公网开放。
- 小c在现有`Bridge.command`中调用`image_commands.py`；大肥鱼在OneBot插件`lib/inbound.js`的白名单检查之后、聊天分发之前调用新增的`codex-image.js`。插件升级覆盖此文件时需复核补丁。
- `install_patch.py`只修改当前代码上的小段接缝，先备份并校验语法，保留其他维护变更；备份路径记录于`.private/deployment.json`。
- 原QQ容器不重启；部署只需重启聊天桥、Harness和新增的图片服务。

## 生成、投递与记录

调用服务器已有`codex-proxy exec --ignore-user-config --ephemeral`及原ChatGPT登录，开启`image_generation`。关闭shell、apps、远端插件、多代理、hooks及搜索；使用read-only沙箱，只传本次图片描述，不传聊天记忆、角色档案、QQ凭据。没有API付费后备。

使用内置图片工具；CLI 0.169.0会把图片保存在`/home/ubuntu/.codex/generated_images`，但JSONL目前不输出图片item。优先识别原生图片item；兼容路径只接受调用前后恰好一个新生成的图片文件，不相信助手文字声称的任意路径。校验图片类型和12 MiB大小限制，然后复制到本服务私密输出目录，再通过对应QQ账号发给固定本人。

`.private/jobs.sqlite3`记录任务、描述、状态、QQ回执；`.private/outputs/<任务号>/image.png`保存结果，权限600。只在日志打印任务号、错误类别及回执，不打印描述或凭据。

按账号与消息ID持久去重。生成前验证QQ在线及实际账号；单次生成上限420秒，不自动重画。进程中断后的生成任务记为失败；已进入发送阶段但结果不明记为uncertain，不自动重发。任务失败时给出对应提示；QQ离线时提示本身可能无法送达，可恢复后查看`/生图状态`。

用量归`qq_image_generation`。普通token日志不能完整代表生图额度；内置生图使用一般Codex额度，具体以账号官方额度为准：[官方生图说明](https://learn.chatgpt.com/docs/image-generation?surface=cli)。

```sh
systemctl status qq-image-generation qq-chat deepseek-harness --no-pager
sudo journalctl -u qq-image-generation -n 20 --no-pager
cd /home/ubuntu/server-maintenance/images
python3 -m unittest -v test_image_service
node test-codex-image.mjs
```

2026-11-20同时经用户授权，将备用代理每日上限从300 MiB提高到400 MiB，保留提前2 MiB停用和原有累计，不清零已用流量。
