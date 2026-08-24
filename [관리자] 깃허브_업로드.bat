@echo off
chcp 65001 > nul
title EasyCut 관리자 - 깃허브 원클릭 배포
cd /d "%~dp0"

echo [1/3] 변경된 모든 파일 추가 중...
git add .

set /p commit_msg="업데이트 내용을 입력하세요 (엔터 시 기본값): "
if "%commit_msg%"=="" set "commit_msg=update code"

echo [2/3] 커밋 생성 중: "%commit_msg%"
git commit -m "%commit_msg%"

echo [3/3] 깃허브 저장소로 전송 중...
git push origin main

echo ========================================================
echo  업로드가 완료되었습니다! 이제 사용자들이 바로 최신 버전을 씁니다.
echo ========================================================
pause