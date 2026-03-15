$projectDir = "D:\DrTew\SecureWatch by QingYing JinXuan\SecureWatch"
$restartSec = 3600   # change later to 7200 if needed

Set-Location $projectDir

$lostProc = $null

function Start-BackendWindow {
    param(
        [string]$Title,
        [string]$Command
    )

    Start-Process powershell `
        -ArgumentList @(
            "-NoExit",
            "-ExecutionPolicy", "Bypass",
            "-Command", @"
`$Host.UI.RawUI.WindowTitle = '$Title'
cd '$projectDir'
& '.\venv\Scripts\Activate.ps1'
$Command
"@
        ) `
        -PassThru
}

function Stop-BackendProcessTree {
    param(
        [System.Diagnostics.Process]$Proc
    )

    if ($Proc -and -not $Proc.HasExited) {
        try {
            taskkill /PID $Proc.Id /T /F | Out-Null
        } catch {}
    }
}

try {
    while ($true) {
        Write-Host "=========================================="
        Write-Host "Starting SecureWatch backends..."
        Write-Host (Get-Date)
        Write-Host "=========================================="

        # Lost & Found backend window
        $lostProc = Start-BackendWindow `
            -Title "Lost & Found Backend :8000" `
            -Command "uvicorn backend.backend:app --host 0.0.0.0 --port $PORT"

 
        Write-Host "Lost & Found backend window PID: $($lostProc.Id)"
        Write-Host "Waiting $restartSec seconds before restart..."
        Write-Host "Press CTRL+C once to stop everything."

        $startTime = Get-Date

        while ($true) {
            Start-Sleep -Seconds 1

            $lostExited = $true

            try {
                if ($lostProc) { $lostExited = $lostProc.HasExited }
            } catch {
                $lostExited = $true
            }

            if ($lostExited) {
                Write-Host "One backend exited by itself."
                break
            }

            $elapsed = (Get-Date) - $startTime
            if ($elapsed.TotalSeconds -ge $restartSec) {
                Write-Host "Restart interval reached. Stopping both backends..."
                Stop-BackendProcessTree -Proc $lostProc
                break
            }
        }

        Write-Host "Restarting in 3 seconds..."
        Start-Sleep -Seconds 3
    }
}
catch {
    Write-Host "`nCTRL+C detected. Stopping launcher..."
}
finally {
    Stop-BackendProcessTree -Proc $lostProc
    Write-Host "Launcher stopped."
}