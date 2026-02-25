$ErrorActionPreference = 'Stop'
$root = 'F:\coding\we-mp-rss'
$envFile = Join-Path $root 'tools\monitor_feishu_qrcode.env'
$script = Join-Path $root 'tools\monitor_feishu_qrcode.py'

Get-Content $envFile | ForEach-Object {
  $line = $_.Trim()
  if (-not $line -or $line.StartsWith('#')) { return }
  $idx = $line.IndexOf('=')
  if ($idx -lt 1) { return }
  $k = $line.Substring(0, $idx).Trim()
  $v = $line.Substring($idx + 1).Trim()
  [Environment]::SetEnvironmentVariable($k, $v, 'Process')
}

python $script
