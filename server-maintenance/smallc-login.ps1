[CmdletBinding()]
param(
    [ValidateSet('Prepare', 'Verify')][string]$Mode = 'Prepare',
    [ValidateRange(0, 45)][int]$WaitSeconds = 15,
    [string]$InterfaceAlias
)
$ErrorActionPreference = 'Stop'
$helper = Join-Path $PSScriptRoot 'smallc_login.py'
$encoded = [Convert]::ToBase64String([IO.File]::ReadAllBytes($helper))
$remoteCommand = 'python3 -c ''import base64,sys;sys.argv=["smallc_login.py","--mode","{0}","--wait","{1}"];exec(base64.b64decode("{2}"))''' -f $Mode.ToLowerInvariant(), $WaitSeconds, $encoded
$connection = @{ Command = $remoteCommand }
if ($InterfaceAlias) { $connection.InterfaceAlias = $InterfaceAlias }
$raw = @(& (Join-Path $PSScriptRoot 'connect-ssh.ps1') @connection)
if ($LASTEXITCODE -ne 0) { throw 'Smallc login SSH request failed.' }
$result = ($raw -join "`n") | ConvertFrom-Json
if ($result.status -eq 'scan_qr') {
    $bytes = [Convert]::FromBase64String($result.png_base64)
    if ($bytes.Length -lt 8 -or [Convert]::ToHexString($bytes[0..7]) -ne '89504E470D0A1A0A') {
        throw 'Invalid login QR image.'
    }
    $folder = Join-Path (Split-Path -Parent $PSScriptRoot) '.private/smallc-login'
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
    $path = Join-Path $folder ('smallc-' + [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() + '.png')
    [IO.File]::WriteAllBytes($path, $bytes)
    $result.PSObject.Properties.Remove('png_base64')
    $result | Add-Member -NotePropertyName image_path -NotePropertyValue $path
}
$result | ConvertTo-Json -Compress
