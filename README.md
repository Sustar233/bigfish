# bigfish

服务器项目的代码与部署记录。仓库地址：<https://github.com/Sustar233/bigfish>。

## 目录

- `server-deploy/qq-codex/`：Codex QQ 私聊、群聊、档案、记忆与运维脚本。
- `server-deploy/qq-dsh/`：Harness / DeepSeek QQ 部署与聊天风格配置。
- `server-deploy/dailyZhihu/`：知乎日报、邮件交付与 systemd 定时任务。
- `server-deploy/personal-page/`：个人主页与部署脚本。
- `server-deploy/research/`：聊天风格研究与上线记录。
- `server-deploy/README-codex-proxy.md`：服务器 Codex 代理运行说明。
- `gold-monitor/`：Au99.99 金价监控、固定收件人提醒与定时器。
- `server-maintenance/`：服务索引、新闻、天气、用量计量、网络保护与图片服务。
- `server-media/`：QQ 语音、表情包模块和桥接补丁。

仓库保存本机已有代码快照，不代表已重新读取服务器的实时文件。登录状态、密钥、私密备份、二维码截图、运行产物和下载的安装包不纳入 Git。部署说明中的状态与日期属于当时记录。

## 2026-11-20 本地合并

以远程 `main` 的原有提交为基础，保留 `server-deploy/`，将本机 `qq-bridge-upgrade/` 的代码更新合并到 `server-deploy/qq-codex/`。原始升级目录只保留在本机，避免维护两套可提交副本。新增金价、运维和媒体工具目录；媒体、生图接线仍由各自补丁脚本完成，本次 Git 同步没有运行部署脚本或修改线上服务。

提交版本中的账号、群号、邮箱、服务器地址及固定 MAC 均为示例：`1000000001` 为本人，`1000000002` 为小c，`1000000003` 为大肥鱼，`1000000004` 为群号；`owner@example.com`、`192.0.2.10`、`192.0.2.20` 和 `02:00:00:00:00:01/02` 也不是实际配置。部署前需在受控副本中统一配置这些值及私密凭据，不能把示例当作生产白名单。历史部署记录中的实时状态不因本次合并而重新得到验证。

原始本地文件及脱敏前副本保存于本机忽略目录 `.private/sync-backup-2026-11-20/`。登录截图、压缩包、生成图片、真实用量报表和运行偏好不提交；新闻偏好仅提供 `server-maintenance/news/interest_preferences.example.json`，程序缺少实际偏好文件时会使用默认值。提交前应检查 `git diff --cached`，不要用 `git add -f` 绕过这些规则。

本次清理针对当前文件；已有远程提交的历史保持原样，旧提交中曾有的标识不会因此被移除。

## 两台电脑协作

本次首个版本使用 `main` 分支。另一台电脑如果还没有本仓库，先克隆到新目录，再把已经修改的文件复制到对应目录；保留服务器上的私密配置：

```sh
git clone https://github.com/Sustar233/bigfish.git
cd bigfish
git switch -c codex/other-computer-changes
# 将另一台电脑或服务器上的改动复制到对应目录，然后检查差异
git status
git diff
git add <本次修改的文件路径>
git commit -m "Update server changes from other computer"
git push -u origin codex/other-computer-changes
```

随后在 GitHub 创建合并到 `main` 的 Pull Request。分支名可按工作内容修改。若另一台电脑已有独立 Git 历史，建议保留原目录，另行克隆本仓库并复制改动，避免直接推送互不相关的历史。

后续每次开始修改前，先同步主分支，再创建工作分支：

```sh
git switch main
git pull --ff-only origin main
git switch -c codex/describe-this-change
```

已有工作分支需要吸收最新主分支时，先提交本地修改，然后执行：

```sh
git fetch origin
git merge origin/main
# 若出现冲突，逐个核对双方修改，解决并提交后再推送
git push
```

不要强制推送共享的 `main`。合并代码不会自动部署到服务器；部署前应核对服务器现有文件及私密配置。

## 本地检查

Python 测试使用标准库 `unittest`。完整测试应在 Linux 上运行；日报服务器模块依赖 Linux 的 `fcntl`，不能直接在 Windows 导入：

```sh
cd server-deploy/qq-codex
python -m unittest discover -s . -p "test_*.py"
cd ../dailyZhihu
python -m unittest discover -s tests -p "test_*.py"
```

QQ 测试包含一次约 31 秒的本地 SSE 空闲连接检查。

2026-11-20 合并检查：170 项现有 Python 测试和 7 项 JavaScript 命令检查通过；47 个 Python 文件、5 个 JavaScript 文件、7 个 JSON 文件及 PowerShell 脚本通过语法/格式检查。Python 测试在 Windows 的隔离入口中适配文件锁和临时 SQLite 清理，禁止真实外网与模型子进程；SSE 和图片接口测试只访问本机回环。媒体测试在临时副本中应用原有补丁。以上不替代 Linux 权限、线上网络和实际投递验收。
