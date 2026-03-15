$ErrorActionPreference = "Stop"

# Put your real python.exe path here:
$PY = "C:\Users\Dator\AppData\Local\Programs\Python\Python312\python.exe"

chcp 65001 > $null
$env:PYTHONIOENCODING = "utf-8"

& $PY .\test_n8n_create.py
& $PY .\test_n8n_debug.py

Write-Host "ALL TESTS DONE"
'@ | Set-Content -Encoding UTF8 .\run_tests.ps1