param([int]$Wait = 40)
$root = 'E:\第二后裔\TFD发布端V50\TFD发布端V50'
$py = 'C:\Users\admin\AppData\Local\Programs\Python\Python314\python.exe'
$runs = Join-Path $root 'data\launcher\runs'

Get-Process -Name 'M1-Win64-Shipping','TFDLauncher' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3

$before = @(Get-ChildItem -Path $runs -Recurse -Directory -Depth 1 -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^2026' } | Select-Object -ExpandProperty FullName)
Start-Process -FilePath (Join-Path $root '启动V50（免授权）.cmd') -WorkingDirectory $root -WindowStyle Minimized
Start-Sleep -Seconds $Wait

$after = @(Get-ChildItem -Path $runs -Recurse -Directory -Depth 1 -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^2026' } | Sort-Object LastWriteTime -Descending)
$new = $after | Where-Object { $before -notcontains $_.FullName } | Select-Object -First 1
if (-not $new) { $new = $after | Select-Object -First 1 }
Write-Output ("run: " + $new.FullName)
Write-Output ("procs: " + ((Get-Process -Name 'M1-Win64-Shipping','TFDLauncher' -ErrorAction SilentlyContinue | Measure-Object).Count))
$ev = Join-Path $new.FullName 'events.jsonl'
& $py -c @"
import json,sys
p=sys.argv[1]
ev=[json.loads(l) for l in open(p,encoding='utf-8') if l.strip()] if __import__('os').path.exists(p) else []
print('events',len(ev))
for e in ev:
    n=e.get('event')
    if n in ('bridge_ready','bridge_error','native_title_creation_bridge_ready','native_title_login_rearmed','startup_bridge_loaded','game_process_started','native_inventory_bridge_ready','offline_runtime_revision'):
        print(' ',e.get('elapsed'),n,str(e.get('description',''))[:300])
    elif n and (n.startswith('native_') or n.startswith('login') or 'error' in str(n)):
        print(' ',e.get('elapsed'),n,str({k:v for k,v in e.items() if k not in ('elapsed','event','stack')})[:220])
"@ $ev
