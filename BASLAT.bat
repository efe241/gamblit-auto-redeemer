@echo off
chcp 65001 >nul
title Gamblit Auto-Redeemer Pro
color 0b

echo ========================================================
echo    [***] GAMBLIT AUTO-REDEEMER PRO BASLATILIYOR [***]
echo ========================================================
echo.

:: 1. Python Kontrolu
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [HATA] Bilgisayarinda Python yuklu degil!
    echo Lutfen https://www.python.org/ adresinden Python 3.10+ yukle ve
    echo kurulumda 'Add Python to PATH' secenegini isaretle.
    echo.
    pause
    exit /b
)

:: 2. .env Dosyasi Kontrolu
if not exist .env (
    echo [*] Ayar dosyasi olusturuluyor...
    copy .env.example .env >nul
)

:: 3. Sanal Ortam ve Kutuphane Kontrolu
if not exist .venv (
    echo [*] Ilk calistirma algilandi. Otomatik kurulum yapiliyor...
    python -m venv .venv
    echo [*] Gerekli moduller yukleniyor, lutfen bekleyin...
    .\.venv\Scripts\python.exe -m pip install --upgrade pip >nul 2>&1
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    echo [OK] Kurulum basariyla tamamlandi!
    echo.
)

:: 4. Tarayicida Paneli Otomatik Ac
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:5050"

echo [OK] Web Kontrol Paneli Baslatildi!
echo [!] Tarayicin otomatik acilacak: http://localhost:5050
echo [*] Bot arkada canli calisiyor. Durdurmak icin pencereyi kapatabilirsin.
echo.
echo ========================================================
echo.

:: 5. Ana Uygulamayi Calistir
.\.venv\Scripts\python.exe main.py

if %errorlevel% neq 0 (
    echo.
    echo [!] Bir hata olustu veya bot durduruldu.
    pause
)
