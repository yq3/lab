# PulsePet opencode 插件安装/卸载（Windows PowerShell，TC-EV-03）。
#
# 用法：
#   .\install.ps1              # 安装（幂等）
#   .\install.ps1 -Uninstall   # 卸载（只移除 --pulse-pet-managed 项）
#
# 依赖：node（仅用于 JSONC 感知的配置合并）。
param(
  [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$HookSrc = Join-Path $ScriptDir "pulse-pet-hook.js"
$ConfigTool = Join-Path $ScriptDir "opencode-config.mjs"

# opencode 配置目录：优先 %APPDATA%\opencode，回退 ~/.config/opencode
$AppData = [Environment]::GetFolderPath("ApplicationData")
$OpenCodeDir = if (Test-Path (Join-Path $AppData "opencode")) {
  Join-Path $AppData "opencode"
} else {
  Join-Path $HOME ".config\opencode"
}
$PluginsDir = Join-Path $OpenCodeDir "plugins"
$PluginFile = Join-Path $PluginsDir "pulse-pet-hook.js"

function Find-Config {
  $json = Join-Path $OpenCodeDir "opencode.json"
  $jsonc = Join-Path $OpenCodeDir "opencode.jsonc"
  if (Test-Path $json) { return $json }
  if (Test-Path $jsonc) { return $jsonc }
  return $json
}

if ($Uninstall) {
  $cfg = Find-Config
  if (Test-Path $cfg) {
    node $ConfigTool uninstall $cfg
    Write-Host "[pulse-pet] removed managed plugin entry from $cfg"
  }
  if (Test-Path $PluginFile) { Remove-Item $PluginFile -Force }
  Write-Host "[pulse-pet] removed $PluginFile"
} else {
  New-Item -ItemType Directory -Force -Path $PluginsDir | Out-Null
  Copy-Item $HookSrc $PluginFile -Force

  $cfg = Find-Config
  if (-not (Test-Path $cfg)) {
    # A6（M2 P3-④ 清偿）：无 BOM UTF-8 写入——Windows PowerShell 5.1 的
    # `Out-File -Encoding utf8` 会带 BOM（M2 时 tokenizer 已兼容 BOM，
    # 此处仍改为 [System.IO.File]::WriteAllText + UTF8Encoding($false)
    # 消除之，新装/旧装产物字节一致）。
    $EmptyConfig = '{
  "plugin": []
}
'
    [System.IO.File]::WriteAllText(
      $cfg,
      $EmptyConfig,
      (New-Object System.Text.UTF8Encoding($false))
    )
  }
  node $ConfigTool install $cfg

  Write-Host "[pulse-pet] installed: hook -> $PluginFile"
  Write-Host "[pulse-pet] merged plugin entry into $cfg (idempotent, JSONC-safe)"
}
