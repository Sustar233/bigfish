[CmdletBinding()]
param(
    [ValidateSet('Status','Pull','Push','Save','Init')]
    [string]$Mode = 'Pull',
    [string]$Message,
    [string[]]$Path,
    [string]$InterfaceAlias
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$store = Join-Path $root '.private/project-sync/local.git'
$serverPath = '/home/ubuntu/qq-owner-ops/workspace/bigfish'
$branch = 'project'
function LocalGit {
    & git "--git-dir=$store" "--work-tree=$root" -C $root @args
    if ($LASTEXITCODE) { throw "Git 操作失败（$LASTEXITCODE）。请检查上方提示。" }
}
if ($Mode -eq 'Init') {
    if (Test-Path (Join-Path $store HEAD)) { throw '本机已有同步记录。' }
    New-Item -Force -ItemType Directory (Split-Path $store) | Out-Null
    & git init --bare -b $branch $store
    if ($LASTEXITCODE) { throw '无法初始化本机同步记录。' }
    LocalGit config core.bare false
    LocalGit config core.worktree $root
    LocalGit config user.name 'Bigfish Desktop'
    LocalGit config user.email 'desktop@bigfish.invalid'
    return
}
if (!(Test-Path (Join-Path $store HEAD))) { throw '请先初始化本机项目同步记录。' }
if ($Mode -eq 'Save') {
    if (!$Message -or !$Path) { throw 'Save 需要 -Message 和 -Path，路径相对项目根目录。' }
    # Pass literal paths to both operations; an earlier interrupted save cannot enter this commit.
    LocalGit --literal-pathspecs add -A -- @Path
    LocalGit --literal-pathspecs commit --only -m $Message -- @Path
    return
}
$info = & (Join-Path $PSScriptRoot 'connect-ssh.ps1') -InterfaceAlias $InterfaceAlias -ConnectionInfo
$keyFile = $info.KnownHosts.Replace('\','/').Replace("'","'\''")
$previousSsh = $env:GIT_SSH_COMMAND
try {
    $env:GIT_SSH_COMMAND = "ssh -b $($info.Source) -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes -o 'UserKnownHostsFile=$keyFile'"
    $url = "ubuntu@$($info.Target):$serverPath"
    if ($Mode -eq 'Push') {
        $pending = @(LocalGit -c core.quotePath=false status --short)
        if ($pending.Count) {
            Write-Warning '以下本机改动尚未提交，本次仅推送已保存的提交。'
            $pending | Write-Host
        }
        LocalGit push $url "HEAD:refs/heads/$branch"
        return
    }
    LocalGit fetch --no-tags $url "refs/heads/$branch"
    if ($Mode -eq 'Status') {
        Write-Host '本机待提交文件'
        LocalGit -c core.quotePath=false status --short
        Write-Host '提交数（仅本机 / 仅服务器）'
        LocalGit rev-list --left-right --count HEAD...FETCH_HEAD
        Write-Host '服务器待提交文件'
        & (Join-Path $PSScriptRoot 'connect-ssh.ps1') -InterfaceAlias $InterfaceAlias -Command "git -C $serverPath -c core.quotePath=false status --short"
        if ($LASTEXITCODE) { throw '无法读取服务器工作区状态。' }
    } else {
        LocalGit merge --ff-only FETCH_HEAD
    }
} finally {
    $env:GIT_SSH_COMMAND = $previousSsh
}
