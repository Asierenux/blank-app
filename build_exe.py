"""Build a standalone executable of the app with PyInstaller.

Usage: python build_exe.py
Output ends up in dist/ (EmparejarImagenes.exe on Windows,
EmparejarImagenes on macOS/Linux).
"""
import os

import PyInstaller.__main__

DATA_SEP = ";" if os.name == "nt" else ":"

PyInstaller.__main__.run(
    [
        "launcher.py",
        "--onefile",
        "--name=EmparejarImagenes",
        "--collect-all=streamlit",
        "--collect-all=pandas",
        "--collect-all=PIL",
        # streamlit_app.py is shipped as plain data (run by Streamlit's
        # CLI, never `import`ed by launcher.py), so PyInstaller's static
        # analysis never sees its `import tkinter`. Force it in
        # explicitly so the folder-picker button actually works in the
        # frozen build, not just when running from source.
        "--collect-all=tkinter",
        f"--add-data=streamlit_app.py{DATA_SEP}.",
        # Not used by this app; pulling it in can crash PyInstaller's
        # static analysis on some environments where a system-level
        # cryptography package conflicts with the pip-installed one.
        "--exclude-module=cryptography",
    ]
)
