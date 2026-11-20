# 还原 36 角色存档（创角进旧存档路线的前置）
# 用法：powershell -ExecutionPolicy Bypass -File scripts\restore-save-36char.ps1
# 说明：二进制不进仓，这里只做本地还原 + 校验；默认路径为发布端根。

$ErrorActionPreference = 'Stop'
$Root     = if ($PSBoundParameters.ContainsKey('Root')) { $Root } else { Split-Path -Parent $PSScriptRoot }
$SaveDir  = Join-Path $Root 'data\launcher\saves\04f2858b03d3e1f379515d84ba575f03'
$Target   = Join-Path $SaveDir 'characters.sqlite3'
$Source   = Join-Path $SaveDir 'characters.sqlite3.bak-36char'
$Expect   = 'AA5ACB84F46460BCB1530ED9FA9D1943F82C1C84FE6C1EC680846267E605F245'

if (-not (Test-Path -LiteralPath $Source)) {
  throw "找不到 36 角色备份：$Source"
}

# 关掉仍占用存档的进程
$procs = Get-Process -Name 'M1-Win64-Shipping', 'TFDLauncher' -ErrorAction SilentlyContinue
if ($procs) {
  throw "还有游戏/启动器进程在跑，先关闭再还原（当前 $($procs.Count) 个）"
}

if (Test-Path -LiteralPath $Target) {
  $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
  Copy-Item -LiteralPath $Target -Destination "$Target.bak-before-restore-$stamp" -Force
  Write-Host "已备份当前库 -> characters.sqlite3.bak-before-restore-$stamp"
}

foreach ($suffix in '-wal', '-shm') {
  $p = "$Target$suffix"
  if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force }
}

Copy-Item -LiteralPath $Source -Destination $Target -Force
$hash = (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash
if ($hash -ne $Expect) {
  throw "还原后校验失败：$hash（期望 $Expect）"
}
Write-Host "已还原 36 角色库，sha256 校验通过：$hash"
