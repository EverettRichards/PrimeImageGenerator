@echo off
setlocal
cd /d %~dp0
pyinstaller --noconfirm --clean --onefile --windowed --name VADIM_ASCII_Generator main.py
