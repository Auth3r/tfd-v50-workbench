# Called inside the firewall worker. Raw ETLs stay in the run's local F: directory.
$script:observerDir = $null
$script:observerInstance = $null
$script:observerActive = $false
$script:afdProfile = Join-Path $PSScriptRoot 'afd-connect.wprp'

function Invoke-ObserverWpr ([string[]]$Arguments) {
    $out = & "$env:SystemRoot\System32\wpr.exe" @Arguments -instancename $script:observerInstance 2>&1
    $rc = $LASTEXITCODE
    Add-Content -LiteralPath (Join-Path $script:observerDir 'recorder.log') -Value (@("$($Arguments[0]) exit=$rc") + @($out))
    if ($rc -ne 0) { throw "wpr_$($Arguments[0])_failed_$rc" }
}

function Open-ConnectTrace {
    Invoke-ObserverWpr @('-start', "$script:afdProfile!GpwAfd.Verbose", '-filemode', '-recordtempto', $script:observerDir)
    $script:observerActive = $true
}

function Close-ConnectTrace ([string]$Name) {
    try {
        Invoke-ObserverWpr @('-status','collectors','-details')
        Invoke-ObserverWpr @('-stop', (Join-Path $script:observerDir "$Name.etl"), '-skipPdbGen')
        $script:observerActive = $false
    } finally {
        if ($script:observerActive) {
            Invoke-ObserverWpr @('-cancel')
            $script:observerActive = $false
        }
    }
}

function New-ObservationControl {
    # Deliberately use a private control socket distinct from both GPW endpoints.
    $control = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,0)
    $peer = [Net.Sockets.TcpClient]::new([Net.Sockets.AddressFamily]::InterNetwork)
    try {
        $control.Start()
        $port = $control.LocalEndpoint.Port
        $peer.Connect([Net.IPAddress]::Loopback,$port)
        $control.AcceptTcpClient().Dispose()
        return [ordered]@{at=(Get-Date -Format o);pid=$PID;port=$port}
    } finally { $peer.Dispose(); $control.Stop() }
}

function Read-ConnectMetadata ([string]$File,[int[]]$TargetPids) {
    $owners = @{}
    $sockets = @{}
    $sequence = 0
    Get-WinEvent -Path $File -Oldest -ErrorAction Stop | ForEach-Object {
        $event = $_
        if ($event.ProviderName -ne 'Microsoft-Windows-Winsock-AFD') { return }
        $v = @($event.Properties | ForEach-Object { ,$_.Value })
        $id = $event.Id
        $old = $id -lt 1000
        $i = if ($old) { 0 } else { 2 }
        $key = "$($v[$i])/$($v[$i+1])"
        if ($id -in 1,1000) {
            $n = if ($old) { 5 } else { 7 }
            $owners[$key] = [long]$v[$n]
            # Creation returns often carry zeros. Use the latest creation entry
            # for type information and start a fresh identity on pointer reuse.
            if ($old -or $v[0] -eq 0) {
                $sequence++
                $sockets[$key] = [pscustomobject]@{sequence=$sequence;family=$v[$i+2];type=$v[$i+3];protocol=$v[$i+4]}
            }
        }
        $owner = $owners[$key]
        if ($owner -notin $TargetPids -and $event.ProcessId -notin $TargetPids) { return }
        $address = $null
        $port = $null
        $status = $null
        if ($id -in 1018,1021) {
            $addr = [byte[]]$v[8]
            if ($addr.Length -ge 8 -and $addr[0] -eq 2) { $address = [Net.IPAddress]::new([byte[]]$addr[4..7]) }
            if ($addr.Length -ge 24 -and $addr[0] -eq 23) { $address = [Net.IPAddress]::new([byte[]]$addr[8..23]) }
            if ($null -ne $address) { $port = [int]$addr[2] * 256 + $addr[3] }
            $status = $v[6]
        } elseif ($id -in 4,5) {
            $address = [Net.IPAddress]::new($v[2])
            $port = (([int]$v[3] -band 255) * 256) + (([int]$v[3]) -shr 8)
        } elseif ($id -in 6,1017,1020) {
            $status = if ($old) { $v[2] } else { $v[4] }
        }
        if ($address -and $address.IsIPv4MappedToIPv6) { $address=$address.MapToIPv4() }
        $destination = if ($address) { if ([Net.IPAddress]::IsLoopback($address)) { $address.ToString() } else { 'non-loopback' } }
        $socket = $sockets[$key]
        $phase = if ($old) { 'legacy' } elseif ($v[0] -eq 0) { 'entry' } elseif ($v[0] -eq 1) { 'exit' } else { 'unknown' }
        [pscustomobject]@{at=$event.TimeCreated.ToString('o');id=$id;phase=$phase;owner=$owner;headerPID=$event.ProcessId;thread=$event.ThreadId;socket=$socket.sequence;family=$socket.family;socketType=$socket.type;protocol=$socket.protocol;destination=$destination;port=$port;status=$status}
    }
}

function Start-ConnectObservation ([guid]$Id,[int]$LoginPort) {
    $script:observerInstance = "GPW-$Id"
    $script:observerDir = Join-Path (Split-Path -Parent $script:afdProfile) "../target/m1-connect-observation/observations/$Id"
    $script:observerDir = [IO.Path]::GetFullPath($script:observerDir)
    [IO.Directory]::CreateDirectory($script:observerDir) | Out-Null
    try {
        Open-ConnectTrace
        $control = New-ObservationControl
        Close-ConnectTrace 'calibration'
        $rows = @(Read-ConnectMetadata (Join-Path $script:observerDir 'calibration.etl') @($PID))
        $matchesControl = @($rows | Where-Object { $_.owner -eq $PID -and $_.destination -eq '127.0.0.1' -and $_.port -eq $control.port })
        [ordered]@{control=$control;matched=$matchesControl.Count;events=$rows} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $script:observerDir 'calibration.json')
        if (!$matchesControl.Count) { throw 'AFD calibration did not attribute the control connection' }
        Open-ConnectTrace
        $runControl = New-ObservationControl
        [ordered]@{control=$runControl;login=$LoginPort;client=$LoginPort+1;ready=(Get-Date -Format o)} | ConvertTo-Json -Depth 3 | Set-Content (Join-Path $script:observerDir 'ready.json')
    } catch {
        $_.Exception.Message | Set-Content (Join-Path $script:observerDir 'error.txt')
        throw
    }
}

function Stop-ConnectObservation {
    if ($script:observerActive) { Close-ConnectTrace 'client' }
}
