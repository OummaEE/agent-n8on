; Custom NSIS script for Agent n8On
; Tauri !include's this at compile time (customNsisScript in tauri.conf.json).
;
; un.onInit runs BEFORE Tauri's uninstall section deletes any files,
; so cleanup.ps1 is still accessible in %APPDATA%\Agent n8On\.

!macro customInstall
!macroend

!macro customUnInstall
!macroend

Function un.onInit
    ; Run the pre-uninstall PowerShell script written during installation.
    ; It shows a dialog asking about Ollama/models, then cleans up accordingly.
    ; If the file is absent (old install / first run after update), we fall through silently.
    ExecWait 'powershell.exe -NonInteractive -ExecutionPolicy Bypass -File "$APPDATA\Agent n8On\cleanup.ps1"'
FunctionEnd
