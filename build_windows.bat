@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo  아보카도 티켓 매크로 - Windows 빌드
echo ========================================
echo.

:: Python 확인
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python이 설치되어 있지 않습니다.
    echo https://www.python.org/downloads/ 에서 Python 3.10+ 설치하세요.
    pause
    exit /b 1
)

:: 가상환경 생성
if not exist venv (
    echo [1/4] 가상환경 생성 중...
    python -m venv venv
)

:: 가상환경 활성화
call venv\Scripts\activate.bat

:: 패키지 설치
echo [2/4] 패키지 설치 중...
pip install -r requirements.txt --quiet

:: 빌드
echo [3/4] exe 빌드 중... (2-3분 소요)
pyinstaller build.spec --clean --noconfirm

echo.
echo [4/4] 빌드 완료!
echo.
echo  exe 파일 위치: dist\AvocadoTicketMacro.exe
echo.
pause
