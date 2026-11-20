param(
    [string]$Handoff = 'E:\第二后裔\TFD发布端V50\TFD发布端V50\handoff',
    [string]$Python = 'C:\Program Files\WindowsApps\OpenAI.CodexPrimaryRuntime.v26-1119-907-0_26.1119.907.0_x64__3k8sg7r9htsxt\dependencies\python\python.exe'
)
$ErrorActionPreference = 'Stop'
$project = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
Set-Location -LiteralPath $project
$env:CARGO_HOME = Join-Path $project '.cargo-home'
$env:CARGO_TARGET_DIR = Join-Path $project 'target'
$env:RUSTUP_AUTO_INSTALL = '0'
& cargo build --release --offline --locked --lib
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$output = Join-Path $project 'target/m03-evidence'
[IO.Directory]::CreateDirectory($output) | Out-Null
$env:LIB = Join-Path $project '.build-tools/lib'
$tool = Join-Path $output 'v50_save_map.exe'
& rustc --edition=2024 -C linker=rust-lld -C target-feature=+crt-static tools/v50_save_map.rs --extern gpw_offline_core=target/release/libgpw_offline_core.rlib -L dependency=target/release/deps -o $tool
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python -X utf8 -B tools/v50_save_bridge.py --handoff $Handoff --tool $tool --evidence $PSScriptRoot
exit $LASTEXITCODE
