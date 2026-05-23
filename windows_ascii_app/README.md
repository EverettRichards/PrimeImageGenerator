# Windows ASCII Generator

Build the executable on Windows with:

```bat
build_windows.bat
```

Or run PyInstaller manually from this folder:

```bat
pyinstaller --noconfirm --clean --onefile --windowed --name VADIM_ASCII_Generator main.py
```

The generated executable can run on a Windows machine without Python installed, assuming the bundled dependencies build successfully.

Notes on "Access is denied" when running the exe

- If you see a PermissionError (WinError 5) pointing at `dist\VADIM_ASCII_Generator.exe`, it usually means the file is locked by a running process or your user account doesn't have permission to overwrite it.
- Make sure any previous runs of the exe are closed. You can check Task Manager for `VADIM_ASCII_Generator.exe` and end the process.
- If the file is locked, delete it or restart Explorer to release the lock, or reboot if needed.
- To rebuild with elevated privileges, open PowerShell as Administrator and run `build_windows.bat` from the folder.
