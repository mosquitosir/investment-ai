$ErrorActionPreference = 'Stop'

$projectPath = 'D:\chatgpt\investment-ai'
$pythonPath = 'C:\Users\admin\.codex\.chatgpt-projects\g-p-6aaf84be34dc8191ba8b77e668647931\.venv\Scripts\python.exe'
$healthUrl = 'http://127.0.0.1:8501/_stcore/health'
$logPath = Join-Path $projectPath 'reports'

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

Start-Process -FilePath $pythonPath `
    -ArgumentList '-m streamlit run app.py --server.headless true --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false' `
    -WorkingDirectory $projectPath `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logPath 'streamlit.stdout.log') `
    -RedirectStandardError (Join-Path $logPath 'streamlit.stderr.log')
