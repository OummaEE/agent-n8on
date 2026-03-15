@echo off
echo ============================================
echo  Jane's AI Agent v2 - Installing packages
echo ============================================
echo.

echo [1/7] Installing python-docx (Word documents)...
pip install python-docx

echo [2/7] Installing reportlab (PDF documents)...
pip install reportlab

echo [3/7] Installing openpyxl (Excel files)...
pip install openpyxl

echo [4/7] Installing python-pptx (Presentations)...
pip install python-pptx

echo [5/7] Installing psutil (System info)...
pip install psutil

echo [6/7] Installing requests (Web requests)...
pip install requests

echo [7/7] Installing playwright (Web scraping)...
pip install playwright
playwright install chromium

echo.
echo ============================================
echo  All done! Now run: python agent_v2.py
echo ============================================
pause
