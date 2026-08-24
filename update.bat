@echo off
cd /d C:\Users\user\easycuttingvideo
git add .
git commit -m "auto update"
git push origin main
echo.
echo [완료] 깃허브 전송 완료! 10초 뒤 웹사이트가 자동 반영됩니다.
pause