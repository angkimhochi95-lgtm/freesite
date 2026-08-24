@echo off
chcp 65001 > nul
title EasyCut AI Shorts Studio - 자동 설치 및 실행기
cd /d "%~dp0"

echo ========================================================
echo  [1/3] 깃허브 최신 버전 확인 중...
echo ========================================================
where git >nul 2>&1
if %errorlevel% == 0 (
    git pull origin main
) else (
    echo [안내] Git 미설치 환경입니다. 기존 로컬 버전으로 진행합니다.
)

echo.
echo ========================================================
echo  [2/3] faster-whisper 및 필수 AI 패키지 자동 설치 중...
echo  (최초 설치 시 1~2분 정도 소요될 수 있습니다)
echo ========================================================
python -m pip install -r requirements.txt

echo.
echo ========================================================
echo  [3/3] EasyCut AI 스튜디오 서버 가동 중...
echo ========================================================
echo.

python -m streamlit run app.py
pause