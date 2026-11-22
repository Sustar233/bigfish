[CmdletBinding()]
param(
    [string]$InterfaceAlias,
    [string]$Command,
    [switch]$ConnectionInfo
)

$ErrorActionPreference = 'Stop'
$knownHosts = Join-Path (Split-Path -Parent $PSScriptRoot) 'tencent_known_hosts'
$targets = @(Get-Content -LiteralPath $knownHosts | Where-Object {
    $_ -match '^\s*\d+\.\d+\.\d+\.\d+\s+'
} | ForEach-Object {
    ($_.Trim() -split '\s+', 2)[0]
} | Sort-Object -Unique)
if ($targets.Count -ne 1) {
    throw 'Expected one IPv4 target in tencent_known_hosts.'
}

$sources = @(foreach ($adapter in [Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces()) {
    if ($adapter.OperationalStatus -ne 'Up' -or $adapter.NetworkInterfaceType -notin ('Wireless80211', 'Ethernet')) {
        continue
    }
    if ($InterfaceAlias -and $adapter.Name -ne $InterfaceAlias) {
        continue
    }
    $properties = $adapter.GetIPProperties()
    $gateway = $properties.GatewayAddresses | Where-Object { $_.Address.AddressFamily -eq 'InterNetwork' }
    if ($gateway) {
        foreach ($address in $properties.UnicastAddresses) {
            if ($address.Address.AddressFamily -eq 'InterNetwork' -and $address.Address.IPAddressToString -notlike '169.254.*') {
                [pscustomobject]@{ Adapter = $adapter.Name; Address = $address.Address.IPAddressToString }
            }
        }
    }
})
if ($sources.Count -eq 0) {
    throw 'No active Wi-Fi or Ethernet adapter with an IPv4 gateway was found.'
}
if ($sources.Count -gt 1) {
    $choices = ($sources | ForEach-Object { $_.Adapter } | Sort-Object -Unique) -join ', '
    throw "Several LAN addresses were found. Specify the adapter with -InterfaceAlias ($choices)."
}

if ($ConnectionInfo) {
    return [pscustomobject]@{ Target = $targets[0]; Source = $sources[0].Address; KnownHosts = $knownHosts }
}

$sshArguments = @('-b', $sources[0].Address, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
    '-o', 'StrictHostKeyChecking=yes', '-o', "UserKnownHostsFile=$knownHosts", "ubuntu@$($targets[0])")
if ($Command) {
    $sshArguments += $Command
}
& ssh @sshArguments
exit $LASTEXITCODE
