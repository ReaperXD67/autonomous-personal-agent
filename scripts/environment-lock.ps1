# Shared by interactive setup scripts. Keep this file free of an entrypoint.
function Invoke-HermesEnvironmentLock {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][scriptblock]$Action
    )
    $hermesLockPath = [IO.Path]::GetFullPath($Path)
    if ($env:OS -eq 'Windows_NT') { $hermesLockPath = $hermesLockPath.ToUpperInvariant() }
    $hermesHasher = [Security.Cryptography.SHA256]::Create()
    try {
        $hermesLockHash = [BitConverter]::ToString(
            $hermesHasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($hermesLockPath))
        ).Replace('-', '')
    }
    finally { $hermesHasher.Dispose() }
    $hermesMutex = [Threading.Mutex]::new($false, "Hermes.Environment.$hermesLockHash")
    $hermesOwned = $false
    try {
        try { $hermesOwned = $hermesMutex.WaitOne(15000) }
        catch [Threading.AbandonedMutexException] { $hermesOwned = $true }
        if (-not $hermesOwned) { throw 'Another Hermes setup is saving configuration. Retry when it finishes.' }
        & $Action
    }
    finally {
        if ($hermesOwned) { $hermesMutex.ReleaseMutex() }
        $hermesMutex.Dispose()
    }
}
