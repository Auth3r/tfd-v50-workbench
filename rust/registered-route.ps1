$ErrorActionPreference = 'Stop'
$env:PSModulePath = Join-Path $PSHOME 'Modules'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$shortcuts = @(foreach ($place in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
    foreach ($relative in @('The First Descendant.url', 'Steam\The First Descendant.url')) {
        $file = Join-Path $place $relative
        if ((Test-Path -LiteralPath $file -PathType Leaf) -and
            ((Get-Content -LiteralPath $file) -contains 'URL=steam://rungameid/2074920')) { $file }
    }
})
$handler = (Get-Item 'Registry::HKEY_CLASSES_ROOT\steam\shell\open\command').GetValue('')
$client = (Get-ItemProperty 'HKCU:\Software\Valve\Steam').SteamPath
$libraries = Get-Content -LiteralPath (Join-Path $client 'steamapps/libraryfolders.vdf')
$installs = @(foreach ($line in $libraries) {
    if ($line -notmatch '^\s*"path"\s+"([^"]+)"\s*$') { continue }
    $library = $Matches[1].Replace('\\','\')
    $manifest = Join-Path $library 'steamapps/appmanifest_2074920.acf'
    if (!(Test-Path -LiteralPath $manifest -PathType Leaf)) { continue }
    $fields = @{}
    foreach ($field in (Get-Content -LiteralPath $manifest)) {
        if ($field -match '^\s*"(appid|buildid|installdir)"\s+"([^"]+)"\s*$') {
            if ($fields.ContainsKey($Matches[1])) { throw 'ambiguous_manifest_field' }
            $fields[$Matches[1]] = $Matches[2]
        }
    }
    if ($fields.appid -ne '2074920' -or $fields.buildid -notmatch '^\d+$' -or
        $fields.installdir -ne 'The First Descendant') { throw 'unexpected_manifest' }
    $root = Join-Path $library ('steamapps/common/' + $fields.installdir)
    $image = Join-Path $root 'TheFirstDescendant.exe'
    [ordered]@{manifest=$manifest; root=$root; build=$fields.buildid; entrySHA256=(Get-FileHash -LiteralPath $image).Hash}
})
$registeredSteam = ($handler -match '^"([^"]+)"\s+--\s+"%1"$') -and
    ([IO.Path]::GetFullPath($Matches[1]) -eq [IO.Path]::GetFullPath((Join-Path $client 'steam.exe')))
$resolved = $shortcuts.Count -gt 0 -and $registeredSteam -and $installs.Count -eq 1
$reason = if (!$resolved) { 'registered_route_unresolved' } elseif ($installs[0].build -ne '26263743') {
    'registered_route_requires_steam_and_targets_another_build'
} else { 'registered_route_requires_steam' }
[ordered]@{resolved=$resolved; reason=$reason; shortcuts=$shortcuts; handler=$handler; installs=$installs; invoked=$false} | ConvertTo-Json -Depth 5
if (!$resolved) { exit 2 }
