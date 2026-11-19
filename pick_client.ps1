param([string]$Value)

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$store = Join-Path $here 'client.txt'
$exeName = 'M1-Win64-Shipping.exe'

function Resolve-Client([string]$p) {
    if ([string]::IsNullOrWhiteSpace($p)) { return $null }
    $p = $p.Trim().Trim('"')
    if (Test-Path -LiteralPath $p -PathType Leaf) { return (Resolve-Path -LiteralPath $p).Path }
    if (Test-Path -LiteralPath $p -PathType Container) {
        $std = Join-Path $p "M1\Binaries\Win64\$exeName"
        if (Test-Path -LiteralPath $std -PathType Leaf) { return (Resolve-Path -LiteralPath $std).Path }
        $bin = Join-Path $p "Binaries\Win64\$exeName"
        if (Test-Path -LiteralPath $bin -PathType Leaf) { return (Resolve-Path -LiteralPath $bin).Path }
        try {
            $hit = Get-ChildItem -LiteralPath $p -Filter $exeName -Recurse -Depth 4 -ErrorAction SilentlyContinue |
                   Select-Object -First 1
            if ($hit) { return $hit.FullName }
        } catch { }
    }
    return $null
}

$path = Resolve-Client $Value

if (-not $path) {
    Add-Type -AssemblyName System.Windows.Forms
    $dlg = New-Object System.Windows.Forms.OpenFileDialog
    $dlg.Title = '选择本机客户端 M1-Win64-Shipping.exe（可直接把完整路径粘贴到文件名框）'
    $dlg.Filter = "M1-Win64-Shipping.exe|$exeName|可执行文件 (*.exe)|*.exe"
    $dlg.CheckFileExists = $true
    foreach ($guess in @('F:\Codex', 'E:\第二后裔')) {
        if (Test-Path -LiteralPath $guess -PathType Container) { $dlg.InitialDirectory = $guess; break }
    }
    if ($dlg.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { exit 2 }
    $path = Resolve-Client $dlg.FileName
    if (-not $path) {
        $path = $dlg.FileName
    }
}

if (-not $path -or -not (Test-Path -LiteralPath $path -PathType Leaf)) {
    Write-Output 'INVALID'
    exit 3
}

[IO.File]::WriteAllText($store, $path, (New-Object System.Text.UTF8Encoding $false))
Write-Output $path
exit 0
