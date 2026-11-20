param(
    [ValidateSet('Init','Pull','Restore')][string]$Mode='Pull',
    [string]$InputFile,
    [string]$OutputFile
)
$ErrorActionPreference='Stop'
$backupDirectory=Join-Path $PSScriptRoot '.private-backups'
New-Item -ItemType Directory -Force -Path $backupDirectory | Out-Null
$keyFile=Join-Path $backupDirectory 'restore-key.dpapi'
$publicFile=Join-Path $backupDirectory 'backup-public.pem'
Add-Type -AssemblyName System.Security.Cryptography.ProtectedData
if ($Mode -eq 'Init') {
    if (Test-Path -LiteralPath $keyFile) { throw 'Backup key already exists; refusing to replace it.' }
    $backupRsa=[System.Security.Cryptography.RSA]::Create(3072)
    try {
        $privateBytes=[Text.Encoding]::UTF8.GetBytes($backupRsa.ToXmlString($true))
        $protected=[Security.Cryptography.ProtectedData]::Protect($privateBytes,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
        [IO.File]::WriteAllBytes($keyFile,$protected)
        [IO.File]::WriteAllText($publicFile,$backupRsa.ExportSubjectPublicKeyInfoPem())
        [Array]::Clear($privateBytes,0,$privateBytes.Length)
    } finally { $backupRsa.Dispose() }
    Write-Output 'Backup public key and Windows-user-protected restore key created.'
    exit 0
}
if ($Mode -eq 'Restore') {
    if (-not $InputFile -or -not $OutputFile) { throw 'Restore requires InputFile and OutputFile.' }
    $packet=Get-Content -LiteralPath $InputFile -Raw | ConvertFrom-Json
    if ($packet.version -ne 1) { throw 'Unsupported backup format.' }
    $privateBytes=[Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($keyFile),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
    $backupRsa=[Security.Cryptography.RSA]::Create()
    try {
        $backupRsa.FromXmlString([Text.Encoding]::UTF8.GetString($privateBytes))
        $aesKey=$backupRsa.Decrypt([Convert]::FromBase64String($packet.wrapped_key),[Security.Cryptography.RSAEncryptionPadding]::OaepSHA256)
        $packed=[Convert]::FromBase64String($packet.ciphertext)
        $cipher=[byte[]]::new($packed.Length-16)
        $tag=[byte[]]::new(16)
        [Array]::Copy($packed,0,$cipher,0,$cipher.Length)
        [Array]::Copy($packed,$cipher.Length,$tag,0,16)
        $plain=[byte[]]::new($cipher.Length)
        $aes=[Security.Cryptography.AesGcm]::new($aesKey,16)
        try {
            $aes.Decrypt([Convert]::FromBase64String($packet.nonce),$cipher,$tag,$plain,[Text.Encoding]::UTF8.GetBytes('QQ-PRIVATE-BACKUP-v1'))
            [IO.File]::WriteAllBytes($OutputFile,$plain)
        } finally { $aes.Dispose();[Array]::Clear($aesKey,0,$aesKey.Length) }
    } finally { $backupRsa.Dispose();[Array]::Clear($privateBytes,0,$privateBytes.Length) }
    Write-Output 'Authenticated backup restored to the requested file.'
    exit 0
}
$identity='C:/Users/83763/.ssh/id_ed25519'
$knownHosts='C:/Users/83763/Documents/ChatGPT/大肥鱼养殖基地/tencent_known_hosts'
& scp -q -i $identity -o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$knownHosts" 'ubuntu@192.0.2.10:/home/ubuntu/qq-memory/backups/*.qqbak' $backupDirectory
if ($LASTEXITCODE -ne 0) { throw 'Encrypted backup pull failed.' }
[IO.File]::WriteAllText((Join-Path $backupDirectory 'last-pull.txt'),[DateTimeOffset]::Now.ToString('o'))
Write-Output 'Encrypted backups copied locally.'
