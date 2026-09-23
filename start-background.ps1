$ErrorActionPreference = 'Stop'

$projectPath = 'D:\chatgpt\investment-ai'
$pythonPath = 'C:\Users\admin\.codex\.chatgpt-projects\g-p-6aaf84be34dc8191ba8b77e668647931\.venv\Scripts\python.exe'
$healthUrl = 'http://127.0.0.1:8501/_stcore/health'
$logPath = Join-Path $projectPath 'reports'
$startupLog = Join-Path $logPath 'startup.log'

New-Item -ItemType Directory -Path $logPath -Force | Out-Null

try {
    $health = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 2
    if ($health.StatusCode -eq 200) { exit 0 }
} catch {
    # The service is not running yet; continue with startup.
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    "$(Get-Date -Format s) Python runtime not found: $pythonPath" |
        Out-File (Join-Path $logPath 'startup-error.log') -Append -Encoding utf8
    exit 1
}

# Windows 登录后网络组件可能仍在初始化。稍等片刻，并在启动失败时自动重试。
Start-Sleep -Seconds 5

for ($attempt = 1; $attempt -le 3; $attempt++) {
    "$(Get-Date -Format s) Starting Streamlit (attempt $attempt/3)" |
        Out-File $startupLog -Append -Encoding utf8

    $process = Start-Process -FilePath $pythonPath `
        -ArgumentList '-m streamlit run app.py --server.headless true --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false' `
        -WorkingDirectory $projectPath `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logPath 'streamlit.stdout.log') `
        -RedirectStandardError (Join-Path $logPath 'streamlit.stderr.log') `
        -PassThru

    for ($check = 1; $check -le 15; $check++) {
        Start-Sleep -Seconds 1
        try {
            $health = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 2
            if ($health.StatusCode -eq 200) {
                "$(Get-Date -Format s) Streamlit is healthy (PID $($process.Id))" |
                    Out-File $startupLog -Append -Encoding utf8
                exit 0
            }
        } catch {
            # Continue waiting while Streamlit imports the application.
        }

        if ($process.HasExited) { break }
    }

    "$(Get-Date -Format s) Attempt $attempt failed; retrying." |
        Out-File $startupLog -Append -Encoding utf8
    if (-not $process.HasExited) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 5
}

"$(Get-Date -Format s) Streamlit failed after 3 attempts. See streamlit.stderr.log." |
    Out-File (Join-Path $logPath 'startup-error.log') -Append -Encoding utf8
exit 1
