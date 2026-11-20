param([string]$Samples = 'E:\第二后裔\TFD发布端V50\TFD发布端V50\handoff\03-考卷样本.json')
$ErrorActionPreference = 'Stop'
$project = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
Set-Location -LiteralPath $project
$output = Join-Path $project 'target/m01-evidence'
[IO.Directory]::CreateDirectory($output) | Out-Null
$samplesObject = Get-Content -LiteralPath $Samples -Raw -Encoding utf8 | ConvertFrom-Json
$rows = foreach ($sample in $samplesObject.samples) {
    "{0}`t{1}`t{2}`t{3}" -f $sample.proc, $sample.req_len, $sample.req_hex, ([bool]$sample.res_err).ToString().ToLowerInvariant()
}
$inputPath = Join-Path $output 'requests.tsv'
[IO.File]::WriteAllLines($inputPath, [string[]]$rows, [Text.UTF8Encoding]::new($false))
$executable = Join-Path $output 'probe.exe'
# Match the existing .cargo/config.toml; standalone rustc does not read Cargo config.
$env:LIB = Join-Path $project '.build-tools/lib'
& rustc --edition=2024 -C linker=rust-lld -C target-feature=+crt-static (Join-Path $PSScriptRoot 'probe.rs') --extern gpw_offline_core=target/release/libgpw_offline_core.rlib -L dependency=target/release/deps -o $executable
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $executable $inputPath
exit $LASTEXITCODE
