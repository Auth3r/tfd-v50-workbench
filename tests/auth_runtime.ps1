# Independent GPW.auth/1 client. All private keys are ephemeral and stay in this process.
param([Parameter(Mandatory)][string]$Binary, [string]$CharacterRoot, [string]$ReferenceRoot)
$ErrorActionPreference = 'Stop'
$Binary = (Resolve-Path -LiteralPath $Binary).Path
$root = Join-Path $PSScriptRoot '../target/auth-session-runtime/probes'
$dir = [IO.Directory]::CreateDirectory((Join-Path $root ([guid]::NewGuid().ToString('N')))).FullName
$accounts = Join-Path $dir 'accounts.txt'
$sockets = [Collections.Generic.List[Net.Sockets.TcpClient]]::new()
$signers = @{}
$passed = 0
$serviceOptions = @()
$PSNativeCommandUseErrorActionPreference = $false

function Check([bool]$ok, [string]$case) {
    if (!$ok) { throw "FAILED $case" }
    $script:passed++
    Write-Output "PASS $case" | Out-Host
}
function Start-Core([string]$file) {
    $opts = [Diagnostics.ProcessStartInfo]::new($Binary)
    $opts.UseShellExecute = $false
    $opts.CreateNoWindow = $true
    $opts.RedirectStandardOutput = $true
    $opts.RedirectStandardError = $true
    $null = $opts.Environment.Remove('GPW_FRAME_PARAMETER_HEX')
    foreach ($arg in (@('serve-game','0','120','--gpw-accounts',$file) + $serviceOptions)) {
        $opts.ArgumentList.Add($arg)
    }
    return [Diagnostics.Process]::Start($opts)
}
function Start-Valid {
    $script:server = Start-Core $accounts
    $line = $server.StandardOutput.ReadLineAsync().WaitAsync([TimeSpan]::FromSeconds(5)).GetAwaiter().GetResult()
    if ($line -notmatch '^login_endpoint=(127\.0\.0\.1:\d+) server_pid=(\d+) client_endpoint=(127\.0\.0\.1:\d+)$' -or
        [int]$Matches[2] -ne $server.Id) { throw 'GPW endpoints unavailable' }
    $script:login = $Matches[1]
    $script:client = $Matches[3]
    Write-Output "GPW service PID $($server.Id), test client PID $PID, login $login, client $client" | Out-Host
}
function Stop-Core {
    foreach ($s in $sockets) { $s.Dispose() }
    $sockets.Clear()
    if ($script:server) {
        if (!$server.HasExited) { $server.Kill() }
        $server.WaitForExit()
        $script:serverLog += $server.StandardError.ReadToEnd()
        $server.Dispose()
        $script:server = $null
    }
}
function Connect([string]$endpoint) {
    $address = [Net.IPEndPoint]::Parse($endpoint)
    $s = [Net.Sockets.TcpClient]::new()
    $sockets.Add($s)
    $s.Connect($address)
    $s.ReceiveTimeout = 4000
    $s.SendTimeout = 4000
    $s.NoDelay = $true
    return $s
}
function Send-Request($socket, [int]$rid, [string[]]$fields) {
    $body = [Text.Encoding]::UTF8.GetBytes((@('GPW.auth/1',$rid) + $fields -join "`t"))
    $stream = $socket.GetStream()
    $stream.Write([byte[]](71,80,87,82))
    $stream.Write([BitConverter]::GetBytes([uint32]$body.Length))
    $stream.Write($body)
}
function Receive-Reply($socket, [int]$rid) {
    $stream = $socket.GetStream()
    $header = [byte[]]::new(8)
    $stream.ReadExactly($header,0,8)
    $n = [BitConverter]::ToUInt32($header,4)
    if ([Text.Encoding]::ASCII.GetString($header,0,4) -cne 'GPWR' -or $n -gt 65536 -or $n -lt 1) {
        throw 'invalid reply frame'
    }
    $body = [byte[]]::new($n)
    $stream.ReadExactly($body,0,$body.Length)
    $parts = [Text.Encoding]::UTF8.GetString($body).Split("`t")
    if ($parts.Length -lt 3 -or $parts[0] -cne 'GPW.auth/1' -or $parts[1] -cne "$rid") {
        throw 'invalid reply correlation'
    }
    return ,$parts[2..($parts.Length-1)]
}
function Query($socket, [int]$rid, [string[]]$fields) {
    Send-Request $socket $rid $fields
    return ,(Receive-Reply $socket $rid)
}
function Expect($socket, [int]$rid, [string[]]$fields, [string]$expected, [string]$case) {
    $body = Query $socket $rid $fields
    if ($fields[0] -in @('character','select-character')) {
        Write-Output "GPW ClientService rid=$rid op=$($fields -join ' ') reply=$($body -join ' ')" | Out-Host
    }
    Check (($body -join ' ') -ceq $expected) $case
}
function Challenge($s, [int]$rid, [string]$name) {
    $body = Query $s $rid @('challenge',$name)
    if ($body.Count -ne 2 -or $body[0] -cne 'challenge' -or $body[1] -cnotmatch '^[0-9a-f]{64}$') {
        throw 'challenge unavailable'
    }
    return $body[1]
}
function Proof([string]$signer, [string]$account, [string]$nonce) {
    $msg = [Text.Encoding]::UTF8.GetBytes("GPW.auth/1`nLoginService.1`n$account`n$nonce")
    $sig = $signers[$signer].SignData($msg,[Security.Cryptography.HashAlgorithmName]::SHA256,
        [Security.Cryptography.DSASignatureFormat]::IeeeP1363FixedFieldConcatenation)
    return [Convert]::ToHexString($sig)
}
function Login-As([string]$name) {
    $s = Connect $login
    try {
        $nonce = Challenge $s 1 $name
        $signature = Proof $name $name $nonce
        $body = Query $s 2 @('1',$signature)
        if ($body.Count -ne 4 -or $body[0] -cne 'login' -or $body[1] -cne $name -or
            $body[2] -cne $client -or $body[3] -cnotmatch '^gpwh1-[0-9a-f]{64}$') { throw 'signed login failed' }
        return $body[3]
    } finally { $s.Dispose() }
}

function Expect-StartFailure([string]$code) {
    $bad = Start-Core $accounts
    try {
        if (!$bad.WaitForExit(5000)) { throw "unexpected readiness, expected $code" }
        Check ($bad.ExitCode -eq 2 -and $bad.StandardOutput.ReadToEnd() -ceq '' -and
            $bad.StandardError.ReadToEnd().Contains($code)) "startup rejected before readiness ($code)"
    } finally {
        if (!$bad.HasExited) { $bad.Kill(); $bad.WaitForExit() }
        $bad.Dispose()
    }
}

function Test-Characters {
    $journal = "$accounts.characters.gpw"
    $snapshot = Join-Path $PSScriptRoot '../target/gpw-v15-minimal-handoff-20261118/gpw-level2.sqlite3'
    $expectedDigest = '6CD5FA37795D55FBA24F10AB7801B58547B622DDD58F5478BAABD6A1A6962F84'
    Check ((Get-FileHash -LiteralPath $snapshot).Hash -ceq $expectedDigest) 'approved GPW roster snapshot matches sealed hash'
    $script:serviceOptions = @('--characters','nobody',$CharacterRoot)
    Expect-StartFailure 'character_owner_unregistered'
    if ($ReferenceRoot) {
        $reference = & $Binary identify-build $ReferenceRoot
        Check ($LASTEXITCODE -eq 0 -and $reference -ceq 'build=26431286 character_mapping=unmapped') 'reference executable pair identified as 26431286'
        $script:serviceOptions = @('--characters','alice',$ReferenceRoot)
        Expect-StartFailure 'character_content_unavailable_for_build'
    }
    $target = & $Binary identify-build $CharacterRoot
    Check ($LASTEXITCODE -eq 0 -and $target -ceq 'build=26263743 character_mapping=known') 'target executable pair identified as 26263743'
    $script:serviceOptions = @('--saved-characters','alice',$CharacterRoot)
    Expect-StartFailure 'owned_roster_missing'
    Check (![IO.File]::Exists($journal)) 'opening an absent owned roster creates no character journal'
    $script:serviceOptions = @('--characters','alice',$CharacterRoot)
    Start-Valid
    Expect-StartFailure 'workspace_locked'
    $s = Connect $client
    Expect $s 1 @('character') 'error session_invalid' 'unauthenticated connection cannot read characters'
    Expect $s 2 @('1003','alice',(Login-As 'alice')) 'initialized alice' 'owner attached to actual ClientService'
    $rows = Query $s 3 @('characters')
    $entries = $rows[-1].Split(',')
    Write-Output "GPW ClientService rid=3 roster=$($entries.Count) revision=$($rows[1]) selected=$($rows[2])" | Out-Host
    Check ($rows.Count -eq 4 -and $rows[0] -ceq 'characters' -and $rows[1] -ceq '0' -and $rows[2] -ceq '23' -and
        $entries.Length -eq 36 -and ($entries | Sort-Object -Unique).Count -eq 36 -and $entries -ccontains '23:101000023:2') '36 owned character summaries with UID 23 selected'
    Expect $s 4 @('character') 'character 0 23 101000023 2 0 40 5 10' 'selected Ultimate Freyna Lv2 and stored progress'
    Expect $s 5 @('select-character','0','999') 'error character_not_owned' 'non-roster character rejected'
    $bob = Connect $client
    Expect $bob 1 @('1003','bob',(Login-As 'bob')) 'initialized bob' 'second registered account initialized'
    Expect $bob 2 @('characters') 'error character_profile_unassigned' 'unassigned account cannot enumerate the roster'
    Expect $bob 3 @('select-character','0','1') 'error character_profile_unassigned' 'second account cannot change selection'
    Expect $bob 4 @('character','23') 'error character_profile_unassigned' 'details by UID also enforce account ownership'
    Expect $s 6 @('select-character','0','1') 'selection 1 1' 'owner commits character selection'
    Expect $s 7 @('select-character','0','1') 'selection 1 1' 'retry of committed choice keeps revision'
    Expect $s 8 @('select-character','0','23') 'error revision_conflict' 'stale selection cannot overwrite committed choice'
    Expect $s 9 @('character') 'character 1 1 101000003 40 0 40 0 19' 'reads different selected character and its own progress'
    $replacement = Login-As 'alice'
    Expect $s 10 @('select-character','1','23') 'error session_invalid' 'replaced connection loses selection rights'
    Stop-Core
    $backupJournal = [IO.File]::ReadAllBytes($journal)
    # Exercise the previous selection-only disk format using the real committed selection frame.
    $seedBytes = 16 + [BitConverter]::ToUInt32($backupJournal,4)
    $previous = [byte[]]$backupJournal[$seedBytes..($backupJournal.Length-1)]
    Check ([Text.Encoding]::UTF8.GetString($previous).Contains('GPW.selection/1')) 'preserved previous-format selection record'
    [IO.File]::WriteAllBytes($journal,$previous)
    $legacyInit = & $Binary init-character-profile $accounts alice $CharacterRoot 2>&1
    Check ($LASTEXITCODE -eq 2 -and ($legacyInit -join ' ').Contains('existing_selection_requires_import')) 'fresh initialization preserves the previous-format selection'
    $script:serviceOptions = @('--saved-characters','alice',$CharacterRoot)
    Expect-StartFailure 'owned_roster_missing'
    $script:serviceOptions = @('--characters','alice',$CharacterRoot)
    Start-Valid
    Stop-Core
    $migrated = (Get-FileHash -LiteralPath $journal).Hash
    $script:serviceOptions = @('--saved-characters','bob',$CharacterRoot)
    Expect-StartFailure 'owned_roster_missing'
    $script:serviceOptions = @('--saved-characters','alice',$CharacterRoot)
    # Deny all readers only on the approved GPW test copy and release it even on failure.
    $exclusive = [IO.File]::Open($snapshot,'Open','Read','None')
    try {
        $sourceRead = & $Binary selected-level GPW 2>&1
        Check ($LASTEXITCODE -eq 2 -and ($sourceRead -join ' ').Contains('snapshot_not_quiescent')) 'independent process confirms the historical SQLite input is unreadable'
        Start-Valid
        $offline = Connect $client
        Expect $offline 1 @('1003','alice',(Login-As 'alice')) 'initialized alice' 'owner session works with SQLite input unavailable'
        Expect $offline 2 @('character','23') 'character 1 23 101000023 2 0 40 5 10' 'stored Freyna progress remains readable with SQLite input unavailable'
        Stop-Core
        Check ((Get-FileHash -LiteralPath $journal).Hash -ceq $migrated) 'reopening a migrated roster leaves the journal byte-identical'
        # Existing callers also prefer owned state once migration has completed.
        $script:serviceOptions = @('--characters','alice',$CharacterRoot)
        Start-Valid
    } finally { $exclusive.Dispose() }
    $s = Connect $client
    Expect $s 1 @('1003','alice',$replacement) 'error session_invalid' 'restart drops handoff while retaining character state'
    Expect $s 2 @('1003','alice',(Login-As 'alice')) 'initialized alice' 'owner reauthenticates after restart'
    Expect $s 3 @('character') 'character 1 1 101000003 40 0 40 0 19' 'selected UID and revision survive process restart'
    Expect $s 4 @('select-character','1','23') 'selection 2 23' 'owner selects Ultimate Freyna again'
    Expect $s 5 @('character') 'character 2 23 101000023 2 0 40 5 10' 'new selection returns original Lv2 progress'
    Expect $s 6 @('logout') 'closed' 'character owner logs out'
    Expect $s 7 @('characters') 'error session_invalid' 'logout removes access to roster'
    Stop-Core
    $db = [IO.File]::ReadAllBytes($journal)
    $db[-1] = $db[-1] -bxor 1
    [IO.File]::WriteAllBytes($journal,$db)
    Expect-StartFailure 'corrupt_journal'
    [IO.File]::WriteAllBytes($journal,$backupJournal)
    Start-Valid
    $s = Connect $client
    Expect $s 1 @('1003','alice',(Login-As 'alice')) 'initialized alice' 'restored journal opens and owner logs in again'
    Expect $s 2 @('character') 'character 1 1 101000003 40 0 40 0 19' 'operator backup restores earlier saved choice'
    Expect $s 3 @('character','23') 'character 1 23 101000023 2 0 40 5 10' 'owner reads progress for another roster UID'
    Expect $s 4 @('character','999') 'error character_not_owned' 'unknown UID has no details'
    Expect $s 5 @('character') 'character 1 1 101000003 40 0 40 0 19' 'detail lookup preserves saved selection and revision'
    Stop-Core
    Check ((Get-FileHash -LiteralPath $snapshot).Hash -ceq $expectedDigest) 'source snapshot unchanged after selections, restart and restore'
    $beforeInit = (Get-FileHash -LiteralPath $journal).Hash
    $existing = & $Binary init-character-profile $accounts alice $CharacterRoot 2>&1
    Check ($LASTEXITCODE -eq 2 -and ($existing -join ' ').Contains('character_profile_exists') -and
        (Get-FileHash -LiteralPath $journal).Hash -ceq $beforeInit) 'fresh initialization preserves an imported full roster'
    $priorRegistry = $accounts
    $accounts = Join-Path $dir 'fresh.txt'
    $freshJournal = "$accounts.characters.gpw"
    $exclusive = [IO.File]::Open($snapshot,'Open','Read','None')
    try {
        $enrolled = & $Binary register-account $accounts alice $publicKeys['alice']
        Check ($LASTEXITCODE -eq 0 -and $enrolled -ceq "account_registered`talice") 'fresh registry created while research SQLite is unavailable'
        $result = & $Binary init-character-profile $accounts alice $CharacterRoot
        Check ($LASTEXITCODE -eq 0 -and $result -ceq "character_profile_ready`talice") 'first GPW character created from empty storage'
        $initial = (Get-FileHash -LiteralPath $freshJournal).Hash
        $null = & $Binary init-character-profile $accounts alice $CharacterRoot
        Check ($LASTEXITCODE -eq 0 -and (Get-FileHash -LiteralPath $freshJournal).Hash -ceq $initial) 'repeated local initialization preserves the original journal'
        $script:serviceOptions = @('--saved-characters','alice',$CharacterRoot)
        Start-Valid
        $fresh = Connect $client
        Expect $fresh 1 @('1003','alice',(Login-As 'alice')) 'initialized alice' 'new account opens its owned character profile'
        Expect $fresh 2 @('characters') 'characters 0 1 1:101000023:2' 'fresh profile contains exactly its own starter character'
        Expect $fresh 3 @('character') 'character 0 1 101000023 2 0 40 0 0' 'GPW-created Freyna Lv2 has fresh progress and a local instance ID'
        Stop-Core
        Start-Valid
        $fresh = Connect $client
        Expect $fresh 1 @('1003','alice',(Login-As 'alice')) 'initialized alice' 'fresh profile reopens after service restart'
        Expect $fresh 2 @('character') 'character 0 1 101000023 2 0 40 0 0' 'restart preserves independently created character'
    } finally {
        Stop-Core
        $exclusive.Dispose()
        foreach ($file in @($accounts,"$accounts.lock",$freshJournal)) {
            if ([IO.File]::Exists($file)) { [IO.File]::Delete($file) }
        }
        $accounts = $priorRegistry
    }
}

$server = $null
$serverLog = ''
try {
    Write-Output "GPW release $Binary, SHA256 $((Get-FileHash -LiteralPath $Binary -Algorithm SHA256).Hash)"
    $publicKeys = @{}
    foreach ($name in @('alice','bob')) {
        $key = [Security.Cryptography.ECDsa]::Create([Security.Cryptography.ECCurve+NamedCurves]::nistP256)
        $signers[$name] = $key
        $q = $key.ExportParameters($false).Q
        $publicKeys[$name] = [Convert]::ToHexString([byte[]]($q.X + $q.Y))
        $registered = & $Binary register-account $accounts $name $publicKeys[$name]
        Check ($LASTEXITCODE -eq 0 -and $registered -ceq "account_registered`t$name") "local operator registered $name with public key"
    }
    $backup = [IO.File]::ReadAllBytes($accounts)
    $null = & $Binary register-account $accounts 'alice' $publicKeys['alice']
    Check ($LASTEXITCODE -eq 0 -and [Convert]::ToHexString([IO.File]::ReadAllBytes($accounts)) -ceq
        [Convert]::ToHexString($backup)) 'repeated enrollment is idempotent on disk'
    $null = & $Binary register-account $accounts 'alice' $publicKeys['bob'] 2>&1
    Check ($LASTEXITCODE -eq 2) 'registration cannot replace an existing account key'
    $null = & $Binary register-account $accounts 'other' $publicKeys['bob'] 2>&1
    Check ($LASTEXITCODE -eq 2) 'one public key cannot register a second account'
    $null = & $Binary register-account $accounts 'badpoint' ('00' * 64) 2>&1
    Check ($LASTEXITCODE -eq 2 -and [Convert]::ToHexString([IO.File]::ReadAllBytes($accounts)) -ceq
        [Convert]::ToHexString($backup)) 'invalid point and conflicting registrations leave registry intact'
    Start-Valid
    $l = Connect $login
    $c = Connect $client
    Expect $l 1 @('challenge','unknown') 'error authentication_failed' 'unregistered local identity rejected'
    Expect $l 2 @('1','00') 'error challenge_required' 'login requires a fresh challenge'
    Expect $c 1 @('identity') 'error session_invalid' 'client business requires initialization'
    Expect $c 2 @('challenge','alice') 'error unsupported_operation' 'login operations are scoped to LoginService'
    $nonce = Challenge $l 3 'alice'
    $bad = Proof 'bob' 'alice' $nonce
    $good = Proof 'alice' 'alice' $nonce
    Expect $l 4 @('1',$bad) 'error authentication_failed' 'wrong signing key rejected'
    Expect $l 5 @('1',$good) 'error challenge_required' 'failed proof consumes challenge'
    $nonce = Challenge $l 6 'alice'
    $sig = Proof 'alice' 'alice' $nonce
    $other = Connect $login
    $null = Challenge $other 1 'alice'
    Expect $other 2 @('1',$sig) 'error authentication_failed' 'signature bound to issuing connection and challenge'
    $other.Dispose()
    Expect $l 6 @('1',$sig) 'error request_id_reused' 'duplicate request cannot issue or consume a session'
    $body = Query $l 7 @('1',$sig)
    Check ($body.Count -eq 4 -and $body[0] -ceq 'login' -and $body[1] -ceq 'alice' -and
        $body[2] -ceq $client -and $body[3] -cmatch '^gpwh1-[0-9a-f]{64}$') 'verified login returns identity and actual ClientService endpoint'
    $ticket = $body[3]
    Expect $l 8 @('1',$sig) 'error challenge_required' 'successful signature cannot be reused'
    $l.Dispose()
    Expect $c 3 @('1003','bob',$ticket) 'error session_invalid' 'handoff cannot change account'
    $rival = Connect $client
    Send-Request $c 4 @('1003','alice',$ticket)
    Send-Request $rival 1 @('1003','alice',$ticket)
    $one = (Receive-Reply $c 4) -join ' '
    $two = (Receive-Reply $rival 1) -join ' '
    Check ((@($one,$two) -ceq 'initialized alice').Count -eq 1 -and
        (@($one,$two) -ceq 'error session_invalid').Count -eq 1) 'two connections contend for one handoff; exactly one initializes'
    if ($one -ceq 'initialized alice') { $active=$c; $unused=$rival } else { $active=$rival; $unused=$c }
    Expect $unused 10 @('identity') 'error session_invalid' 'losing connection has no identity'
    Expect $active 10 @('identity') 'identity alice' 'subsequent business reads verified identity on attached connection'
    Expect $active 10 @('logout') 'error request_id_reused' 'duplicate request cannot revoke a session'
    Expect $active 11 @('1003','alice',$ticket) 'error already_initialized' 'initialized connection cannot attach a second session'
    $failedLogin = Connect $login
    $wrongNonce = Challenge $failedLogin 1 'alice'
    Expect $failedLogin 2 @('1',(Proof 'bob' 'alice' $wrongNonce)) 'error authentication_failed' 'failed relogin cannot replace the current owner'
    $failedLogin.Dispose()
    Expect $active 12 @('identity') 'identity alice' 'prior session survives failed relogin'

    # A game-format Missing response still comes from the existing empty game-session namespace.
    $legacy = Connect $client
    $legacy.GetStream().Write([byte[]](5,0,0,0,251,255,255,255,0,128,8,214,15,0,0))
    $reply = [byte[]]::new(14)
    $legacy.GetStream().ReadExactly($reply,0,14)
    Check ([Convert]::ToHexString($reply) -ceq '04000000FCFFFFFF008008D60F10') 'active GPW identity does not authorize a game-format request'
    $legacy.Dispose()
    $bobTicket = Login-As 'bob'
    $bob = Connect $client
    Expect $bob 1 @('1003','bob',$bobTicket) 'initialized bob' 'second account has independent session'
    $replacement = Login-As 'alice'
    Expect $active 13 @('identity') 'error session_invalid' 'fresh authentication invalidates earlier active session'
    Expect $active 14 @('1003','alice',$replacement) 'initialized alice' 'revoked connection can initialize again with fresh proof'
    $replacement = Login-As 'alice'
    $fresh = Connect $client
    Expect $fresh 1 @('1003','alice',$replacement) 'initialized alice' 'new owner initializes replacement'
    $active.Dispose()
    Expect $fresh 2 @('identity') 'identity alice' 'disconnect of previous owner preserves replacement'
    Expect $fresh 3 @('logout') 'closed' 'logout revokes live session'
    Expect $fresh 4 @('identity') 'error session_invalid' 'business rejected after logout'
    Expect $unused 11 @('1003','alice',$replacement) 'error session_invalid' 'closed handoff cannot be replayed'
    Expect $bob 2 @('identity') 'identity bob' 'lifecycle mutations are scoped to account'
    $orphan = Login-As 'alice'
    $last = Login-As 'alice'
    Expect $unused 12 @('1003','alice',$orphan) 'error session_invalid' 'new login cancels unclaimed earlier handoff'
    Stop-Core
    # Break and restore only the fixture registry, then exercise the restored account over TCP.
    [IO.File]::AppendAllText($accounts,"alice`t" + $publicKeys['alice'] + "`n")
    $badServer = Start-Core $accounts
    try {
        if (!$badServer.WaitForExit(4000)) { throw 'invalid account registry accepted' }
        Check ($badServer.ExitCode -eq 2 -and $badServer.StandardOutput.ReadToEnd() -ceq '' -and
            $badServer.StandardError.ReadToEnd().Contains('duplicate_or_excess_accounts')) 'ambiguous public identity registry rejected before readiness'
    } finally {
        if (!$badServer.HasExited) { $badServer.Kill(); $badServer.WaitForExit() }
        $badServer.Dispose()
    }
    [IO.File]::WriteAllBytes($accounts,$backup)
    Start-Valid
    $after = Connect $client
    Expect $after 1 @('1003','alice',$last) 'error session_invalid' 'process restart invalidates outstanding handoff'
    $new = Login-As 'alice'
    Expect $after 2 @('1003','alice',$new) 'initialized alice' 'restored on-disk account authenticates after restart'
    Expect $after 3 @('identity') 'identity alice' 'restarted service completes follow-up'
    $expiringTicket = Login-As 'bob'
    $expiryLogin = Connect $login
    $expiringChallenge = Challenge $expiryLogin 1 'alice'
    $lateProof = Proof 'alice' 'alice' $expiringChallenge
    # Keep the login TCP connection open while the challenge itself expires.
    Start-Sleep -Seconds 16
    Expect $expiryLogin 2 @('identity') 'error unsupported_operation' 'unrelated traffic does not renew challenge'
    Start-Sleep -Seconds 15
    Expect $expiryLogin 3 @('1',$lateProof) 'error challenge_expired' 'valid signature rejected after 30 seconds of elapsed time'
    $lateClient = Connect $client
    Expect $lateClient 1 @('1003','bob',$expiringTicket) 'error session_invalid' 'unclaimed handoff expires on the running service'
    Stop-Core
    Check ($serverLog.Contains('gpw_auth_accept') -and $serverLog.Contains('client_session_missing') -and
        !($serverLog.Contains($sig) -or $serverLog.Contains($ticket) -or $serverLog.Contains($nonce))) 'service logs exclude signature, challenge and handoff'
    if ($CharacterRoot) { Test-Characters }
    Write-Output "GPW independent client: $passed checks passed; real_game_client=false"
} finally {
    Stop-Core
    foreach ($key in $signers.Values) { $key.Dispose() }
    if ([IO.File]::Exists($accounts)) { [IO.File]::Delete($accounts) }
    if ([IO.File]::Exists("$accounts.lock")) { [IO.File]::Delete("$accounts.lock") }
    if ([IO.File]::Exists("$accounts.characters.gpw")) { [IO.File]::Delete("$accounts.characters.gpw") }
    [IO.Directory]::Delete($dir)
}
