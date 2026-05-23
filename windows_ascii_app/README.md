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
