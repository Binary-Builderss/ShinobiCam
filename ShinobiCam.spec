# PyInstaller spec - onedir build: dist/ShinobiCam/ShinobiCam.exe
# Run via scripts/build.ps1 (or: pyinstaller --noconfirm ShinobiCam.spec)
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

datas = [
    ("models/hand_landmarker.task", "models"),
    ("assets/log.png", "assets"),
    ("assets/icon.ico", "assets"),
]
datas += collect_data_files("mediapipe", excludes=["**/*.tflite", "**/*.binarypb", "**/testdata/**"])

# mediapipe >= 0.10.30 loads libmediapipe.(dll|dylib|so) with ctypes from mediapipe/tasks/c:
# PyInstaller can't see that import, so collect it explicitly (same relative folder).
binaries = collect_dynamic_libs("mediapipe") + collect_dynamic_libs("pyvirtualcam")

hiddenimports = collect_submodules("mediapipe.tasks.python") + ["mediapipe.tasks.c", "pyvirtualcam", "PIL.ImageTk"]
hiddenimports += ["pygrabber.dshow_graph", "comtypes"] if __import__("sys").platform == "win32" else []

a = Analysis(
    ["shinobicam/__main__.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "IPython", "jupyter", "notebook"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ShinobiCam",
    icon="assets/icon.ico",
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ShinobiCam", upx=False)
