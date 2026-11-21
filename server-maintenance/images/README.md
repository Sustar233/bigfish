# QQ 生图

## 语音请求绘图（2026-11-21）

本人私聊小c或大肥鱼时，可以直接发QQ语音，例如“帮我生成一张小猪图片”或“我想让你画一条摇尾巴的鱼GIF”。QQ原生转写成功后，明确的绘图请求进入原生图队列；GIF仍走原文件投递。支持忽略开头的“嗯、那个、小c、大肥鱼、我想让你”等口语成分。普通闲聊、否定、能力提问和举例不会因提到“生图”而开画。

小c通过 `voice_image.py` 在原有语音转写后、模型聊天前分发；大肥鱼通过插件 `voice-image.js`，在本人白名单校验后读取当前消息的 `fetch_ptt_text` 并分发，避免后台STT只送给聊天模型。绘图仍沿用原账号、原消息ID去重和图片附件角色。大肥鱼此入口不处理群、陌生人、引用、转发或文件/视频混合消息；转写不可用时保留原有语音处理。

补丁入口 `patch_voice_image.py`，需应用在已安装媒体和当前自然语言生图规则的线上桥接代码上；仓库静态桥接未应用媒体补丁时，`test_voice_pipeline.py` 会跳过运行时集成检查。当前 `image_commands.py`、`codex-image.js` 与 `image_intents.json` 已同步本次线上通用版本，不含账号凭据。

2026-11-21 16:50：服务器隔离副本40项图片/GIF/语音检查、JS语音门禁和插件导入检查通过，包含真实小c工作队列接收模拟原生转写并只提交一次绘图的检查。部署重启 `qq-chat` 与 `deepseek-harness`，两服务 active；未重启QQ，未调用模型或回放用户旧语音。真实QQ录音到最终图片的完整链路待下一条新语音验收。备份 `.private/backup-voice-image-20261121-165008/`。

## GIF动图（2026-11-21）

小c、大肥鱼的生图描述中明确要求 `GIF`、`动图` 或 `动态表情` 时，Codex仍使用现有内置图片工具生成连续动画帧，服务将4列2行的8帧画面合成为真正的多帧GIF，再通过原账号 `upload_private_file` 发送 `.gif` 原文件。默认约2秒循环，每帧最长边512像素。不是把PNG改后缀，也不走普通图片或表情消息。

```text
生图：一个小猪挥手的GIF动图
生图：一条鱼摇尾巴的动态表情，透明背景
```

静态图片沿用原链路。GIF会校验文件头、解码后帧数、帧间差异和有效播放时长；静态或无效输出不会冒充动图发送。依赖Ubuntu `python3-pil`，无新增付费API，Codex仍关闭Shell和其他账号工具；GIF编码由受控服务完成。上传回执使用 `file_id`，发送结果不确定时仍不自动重传。

2026-11-21 16:42：服务器36项相关检查通过；两账号分别向固定本人上传一份8帧、2秒的测试GIF文件，两份均取得文件回执。测试动图为程序生成的投递诊断样本，未调用模型；实际Codex画面内容及动画连贯性须在下一次用户生图时验证。本机Python环境无Pillow且沙箱禁止回环请求，完整检查在服务器Linux隔离副本完成。

实现为 `gif_output.py` 与 `patch_gif_output.py`；部署时保留最新的参考图、错误分类和好友绘图改动，只重启 `qq-image-generation`。备份 `.private/backup-gif-20261121-164125/`，实测记录 `.private/gif-delivery-verification.json`。

2026-11-20：小c（1000000002）和大肥鱼（1000000003）可在本人1000000001的QQ私聊中接收：

```text
生图：一个可爱的小猪
生图: 一片星空下的鱼塘，水彩插画
/生图 一个可爱的小猪
/生图状态
```

支持在提示词中指定输出数量，例如「生成三张长沙夜景，分别画湘江、橘子洲和街巷」。每张单独生成并由原账号逐张回图；「多张」默认三张，数量范围 1–32。明确要求一张九宫格时仍按单图处理，原账号回图；明确前缀触发，不经过普通聊天模型判断。当前只做文字生图，群聊、参考图编辑不在本次范围内。描述1–4000字，共用串行队列，最多4条等待/进行中的任务。两个角色的QQ收件人都固定为1000000001，不接收请求提供的目标、路径或命令。

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
