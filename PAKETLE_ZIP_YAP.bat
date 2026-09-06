@echo off
title Gamblit Auto-Redeemer Pro - Zip Paketleyici
color 0b
echo ========================================================
echo    Gamblit Auto-Redeemer Pro - Musteri Paketi Olusturucu
echo ========================================================
echo.

if exist .venv\Scripts\python.exe (
    set PYTHON_EXEC=.venv\Scripts\python.exe
) else (
    set PYTHON_EXEC=python
)

echo [*] Temiz ZIP paketi hazirlaniyor...
%PYTHON_EXEC% scripts/make_release_zip.py

echo.
echo ========================================================
echo   ISLEM TAMAMLANDI!
echo   Musteriye gondereceginiz dosya: Gamblit_AutoRedeemer_Pro.zip
echo ========================================================
echo.
pause
