# 麦麦聊天风格试用

2026-11-21 用户授权“接入麦麦试试”。已适配麦麦现成的表达与接话配置，沿用小c、大肥鱼现有身份和 QQ 接入。这里没有安装完整 MaiBot 的规划器、记忆学习或自动插话系统。

上游：[Mai-with-u/MaiBot](https://github.com/Mai-with-u/MaiBot/tree/edf42446f123149c57fc79765dd5a8b004b8524c)，固定提交 `edf42446f123149c57fc79765dd5a8b004b8524c`。原配置、回复模板、许可证和 SHA-256 均保存在本目录；`sources.json` 记录出处。改编材料按上游 GPL-3.0 保留许可，修改日期为 2026-11-21。

## 适配范围

- 小c：`personalityPresets.ts` 中 `preset-1` 的简短口语、避免模板附和、一次回应一个话题等规则；身份沿用原人设。
- 大肥鱼：`preset-2` 的温柔、天然呆、简短随意表达；身份沿用原人设，不导入上游角色的年龄、姓名和背景。
- 两者沿用默认预设中的简短表达，保留事实准确、实际任务按需展开、不谎报操作、不虚构现实经历等既有约束。
- 未导入上游攻击性、脏话、故意回答有缺憾、自主工具调用规则。上游私聊/群聊模板保留作参考，不宣称已经安装完整原生回复链路。
- 保留小c线上风格文件中的统一命名、天气/新闻/递报和状态通知约定。大肥鱼批准人设只替换原“QQ 接话方式”段，批准哈希同步更新。
- 不改模型、推理强度、白名单、权限、消息触发频率、记忆内容或聊天历史。QQ 容器没有重启。

## 线上入口

试用目录：`/home/ubuntu/qq-style-trial/maibot-20261121`。

实际修改四个文件：

- `/home/ubuntu/qq-codex/bridge/chat_style.md`：小c私聊、群聊共用表达规则。
- `/home/ubuntu/qq-codex/chat_style.md`：Harness QQ 限定预设读取的风格。
- `/home/ubuntu/qq-dsh/records/persona.md`：大肥鱼私聊附加提示和群聊批准人设。
- `/home/ubuntu/qq-dsh/records/persona-approved.json`：批准哈希及本次授权记录。

Harness 继续使用既有 `qq-natural-v3` 预设 ID；它的限定模块读取了新的麦麦风格文件。没有改动全局网页 standard 预设。

## 构建与回滚

`python adapt.py build` 在本地验证上游哈希并生成两份风格文件。服务器使用 `dry-run` 预检、`apply` 保存备份并写入配置。写入失败自动恢复本次修改。

初始备份：`backup-20261120T180124Z`；v2 增补既有的“接完玩笑就停，不招揽任务”规则。`baseline-backup.txt` 指向试用前原件，`last-backup.txt` 指向最近一次写入前备份。

完整撤回本次试用：

```sh
python3 /home/ubuntu/qq-style-trial/maibot-20261121/adapt.py rollback
sudo systemctl restart qq-chat.service qq-group.service deepseek-harness.service
```

回滚先验证现有文件仍为本次写入版本，若其他维护已改动文件则拒绝覆盖；备份也须通过哈希核验。

## 验证边界

`smoke.py` 使用模拟消息调用模型，不向 QQ 发送消息、不读取私人对话，不改历史。初轮两模型各检查玩笑、随便聊和工作汇报改写；最终只复查受增补规则影响的玩笑样本。

Harness 的模拟生成使用现有 `qq-group` headless profile，因此不能单独作为真实私聊会话已使用新提示词的证据。私聊接线另核对了 `dmPromptFile`、限定预设和模块加载结果。真实 QQ 体验仍应由用户新发言确认。
