# VADIM ASCII Images

This project turns input images into ASCII-art style output and can optionally search for a numeric result that is probable prime. The project now has two GUI apps built on the same shared engine:

- A Linux desktop app that runs directly from Python.
- A Windows app that is designed to be packaged into a standalone executable with PyInstaller.

The original notebook is still in the repository, but the GUI apps are the easiest way to use the algorithm interactively.

## What the project does

The engine:

- Loads a `.png`, `.jpg`, or `.jpeg` image.
- Resizes it to the requested output width.
- Converts the image to grayscale using either `standard` or `pca` grayscale mode.
- Applies a brightness modifier before ASCII conversion.
- Maps brightness values to characters.
- Optionally enforces a prime-style numeric output search when primality is requested.
- Produces JPG, PDF, and TXT outputs in the project `outputs/` directory.

The GUI adds:

- Image selection from disk.
- Output width control.
- Background color and text color controls.
- Grayscale method selection.
- Brightness modifier control.
- Auto-generate on image selection.
- Separate buttons for prime and non-prime generation.
- Checkboxes for JPG, PDF, and TXT output.
- A fixed preview pane.
- A scrolling progress log that shows the algorithm output.

## Project Layout

- `shared_ascii_app/` - shared engine and Tkinter GUI code.
- `linux_ascii_app/` - Linux launcher and local setup files.
- `windows_ascii_app/` - Windows launcher and PyInstaller packaging files.
- `inputs/` - source images.
- `outputs/` - generated artifacts.
- `prime_image_generator_vadim.ipynb` - notebook version of the project.

## Requirements

The shared engine and GUI use:

- Python 3.10+ recommended.
- `numpy`
- `Pillow`
- `reportlab`
- `tkinter` on Linux, which is usually provided by the OS package manager.

The Windows packaging workflow also uses:

- `pyinstaller`

## Linux Setup

1. Create and activate a virtual environment from the project root.

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install the Linux app dependencies.

```bash
pip install -r linux_ascii_app/requirements.txt
```

If `tkinter` is missing on your system, install it with your package manager. On Ubuntu/Debian, that is typically:

```bash
sudo apt-get install python3-tk
```

## Run the Linux GUI

From the project root:

```bash
python linux_ascii_app/main.py
```

## Windows Setup

On Windows, install the dependencies inside a Python environment first:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r windows_ascii_app\requirements.txt
```

## Build the Windows Executable

From the `windows_ascii_app/` folder, run:

```bat
build_windows.bat
```

That uses PyInstaller to create a standalone executable. The resulting `.exe` can run on a Windows machine without Python installed, provided the build completed successfully.

If you want to run PyInstaller manually, use:

```bat
pyinstaller --noconfirm --clean --onefile --windowed --name VADIM_ASCII_Generator main.py
```

## How to Use the GUI

1. Click `Select Image` and choose a `.png`, `.jpg`, or `.jpeg` file.
2. Set the `Output Width` you want.
3. Choose the `Background Color` and `Text Color` as hex colors.
4. Pick the `Grayscale Method`:
   - `standard` uses regular grayscale conversion.
   - `pca` uses a PCA-based grayscale projection.
5. Adjust the `Brightness Modifier` if you want the input image brighter or darker before conversion.
6. Leave `Auto generate` on if you want the app to refresh automatically after image selection.
7. Use `Generate Non-prime` or `Generate Prime` to choose whether the numeric output should stay non-prime or run the primality search.
8. Enable or disable `Save JPG`, `Save PDF`, and `Save TXT` as needed.

Generated files are written to the root `outputs/` directory.

## Output Notes

- JPG output is scaled up to zoom more cleanly.
- PDF output is generated using ReportLab.
- TXT output writes the ASCII matrix as plain text.
- The saved filename includes a suffix that distinguishes prime and non-prime generation mode.

## Troubleshooting

- If the GUI does not start on Linux, make sure `tkinter` is installed.
- If the preview seems slow, lower `Output Width`.
- If the app cannot find your image, verify that you selected a valid file from disk.
- The Windows executable is built on Windows only; do not expect the Linux machine to produce a working `.exe` directly.

## Notebook vs GUI

The notebook remains useful for experimentation and debugging, but the GUI is the preferred interface for day-to-day use because it exposes the algorithm controls directly and separates the platform-specific packaging concerns.