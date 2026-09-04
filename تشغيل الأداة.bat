@echo off
chcp 65001 >nul
echo ============================================
echo   أداة تحويل فواتير PDF إلى Excel
echo ============================================
echo.
echo جاري تشغيل الخادم...
echo.
echo افتح المتصفح على العنوان:
echo http://localhost:5000
echo.
echo اضغط Ctrl+C لإيقاف الخادم
echo ============================================
echo.
python "%~dp0server.py"
pause
