param([string]$Samples = 'E:\第二后裔\TFD发布端V50\TFD发布端V50\handoff\06-帧样本-整帧.json')
$ErrorActionPreference = 'Stop'
$project = 'F:\Codex\tfd-offline-2\app'
Set-Location -LiteralPath $project
$expected = '04940ecae8be39e84decf83afcd5bf14650ed2f34100f36a2accd705a3052d97'
$raw = [IO.File]::ReadAllBytes($Samples)
$lf = [Text.Encoding]::UTF8.GetBytes([Text.Encoding]::UTF8.GetString($raw).Replace("`r`n", "`n"))
$actual = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($lf)).ToLowerInvariant()
if ($actual -ne $expected) { throw "Sample version mismatch: $actual" }
Write-Output "SAMPLE_SHA256_LF=$actual"
$protocol = Join-Path $project 'rust/protocol.rs'
$protocolRaw = [IO.File]::ReadAllBytes($protocol)
$protocolLf = [Text.Encoding]::UTF8.GetBytes([Text.Encoding]::UTF8.GetString($protocolRaw).Replace("`r`n", "`n"))
$protocolHash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($protocolLf)).ToLowerInvariant()
if ($protocolHash -ne '6ca922ef014e09c08b2488ad3a5d032b5636eb27556ec3f03db613fef3d9216c') { throw "Protocol source version mismatch: $protocolHash" }
Write-Output "PROTOCOL_SHA256_LF=$protocolHash"
$sampleObject = Get-Content -LiteralPath $Samples -Raw -Encoding utf8 | ConvertFrom-Json
$rows = foreach ($stream in $sampleObject.streams) {
    $boundaries = @($stream.frames | ForEach-Object { "{0},{1},{2}" -f $_.off,$_.plen,$_.total }) -join ';'
    "{0}`t{1}`t{2}`t{3}`t{4}" -f $stream.id,$stream.bytes,$stream.frame_count,$stream.hex,$boundaries
}
$output = Join-Path $project 'target/m01b-evidence'
[IO.Directory]::CreateDirectory($output) | Out-Null
$inputPath = Join-Path $output 'streams.tsv'
[IO.File]::WriteAllLines($inputPath,[string[]]$rows,[Text.UTF8Encoding]::new($false))
$env:M01B_INPUT_TSV = $inputPath
$env:LIB = Join-Path $project '.build-tools/lib'
$executable = Join-Path $output 'verify.exe'
& rustc --test --edition=2024 -C linker=rust-lld -C target-feature=+crt-static (Join-Path $PSScriptRoot 'verify.rs') --extern gpw_offline_core=target/release/libgpw_offline_core.rlib -L dependency=target/release/deps -o $executable
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $executable --nocapture --test-threads=1
exit $LASTEXITCODE
