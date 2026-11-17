# bigfish

服务器项目的代码与部署记录。仓库地址：<https://github.com/Sustar233/bigfish>。

## 目录

- `server-deploy/qq-codex/`：Codex QQ 私聊、群聊、档案、记忆与运维脚本。
- `server-deploy/qq-dsh/`：Harness / DeepSeek QQ 部署与聊天风格配置。
- `server-deploy/dailyZhihu/`：知乎日报、邮件交付与 systemd 定时任务。
- `server-deploy/personal-page/`：个人主页与部署脚本。
- `server-deploy/research/`：聊天风格研究与上线记录。
- `server-deploy/README-codex-proxy.md`：服务器 Codex 代理运行说明。

仓库保存本机已有代码快照，不代表已重新读取服务器的实时文件。登录状态、密钥、私密备份、二维码截图、运行产物和下载的安装包不纳入 Git。部署说明中的状态与日期属于当时记录。

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
