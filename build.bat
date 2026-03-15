@echo off
echo Building Agent n8On...

echo [1/3] Creating icons...
python create_icons.py

echo [2/3] Building Tauri app...
npm run tauri build

echo [3/3] Done!
echo.
echo Installer: src-tauri\target\release\bundle\nsis\Agent_n8On_1.0.0_x64-setup.exe
echo MSI: src-tauri\target\release\bundle\msi\Agent_n8On_1.0.0_x64_en-US.msi
pause
