param([string]$Root=".")
$Log = Join-Path $Root "engineering_log"
New-Item -ItemType Directory -Force -Path $Log | Out-Null
$R = Join-Path $Log "README.md"
$T = Join-Path $Log "TROUBLESHOOTING.md"
$D = Join-Path $Log "DAILY_TEMPLATE.md"
$S = Join-Path $Log "TASK_TEMPLATE.md"

if(!(Test-Path $R)){ @"
# Agent Engineering Log System (AELS)
Правило: каждый день — файл YYYY-MM-DD.md
Баги/разборы — TROUBLESHOOTING.md
"@ | Out-File $R -Encoding utf8 }

if(!(Test-Path $T)){ @"
# Troubleshooting Log
Формат: Symptom / Repro / Hypothesis / Result
"@ | Out-File $T -Encoding utf8 }

if(!(Test-Path $D)){ @"
# Daily Engineering Log — {{DATE}}
## Focus
- 
## Work done
- 
## Next
- 
```text
"@ | Out-File $D -Encoding utf8 }

if(!(Test-Path $S)){ "Task Log Template`nGoal:`nScope:" | Out-File $S -Encoding utf8 }

$today = Get-Date -Format "yyyy-MM-dd"
$todayFile = Join-Path $Log "$today.md"
if(!(Test-Path $todayFile)){
    (Get-Content $D -Raw).Replace("{{DATE}}",$today) | Out-File $todayFile -Encoding utf8
}
Write-Host "AELS Ready. Today: $todayFile" -ForegroundColor Green
