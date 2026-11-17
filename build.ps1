$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not $PSScriptRoot.StartsWith('F:\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Desktop project must stay on F:' }
$env:DOTNET_CLI_HOME = Join-Path $PSScriptRoot '.dotnet'
$env:NUGET_PACKAGES = Join-Path $PSScriptRoot '.nuget\packages'
$env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE = '1'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_GENERATE_ASPNET_CERTIFICATE = 'false'
$env:DOTNET_ADD_GLOBAL_TOOLS_TO_PATH = 'false'
dotnet build GpwOffline.Core.csproj -c Release --configfile NuGet.Config -p:NuGetAudit=false
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Output "Project: $PSScriptRoot; dependencies: $env:NUGET_PACKAGES (zero package references)"
