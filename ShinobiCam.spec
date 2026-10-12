# PyInstaller spec - onedir build.
#   Windows: dist/ShinobiCam/ShinobiCam.exe   (scripts/build.ps1)
#   macOS:   dist/ShinobiCam.app               (scripts/build.sh)
#            SHINOBICAM_SIGN_ID="Developer ID Application: ..." -> signed with hardened runtime (notarizable);
#            unset -> ad-hoc signature, runs only on this Mac without Gatekeeper warnings.
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

from shinobicam import __version__

SIGN_ID = os.environ.get("SHINOBICAM_SIGN_ID") or None

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
hiddenimports += ["pygrabber.dshow_graph", "comtypes"] if sys.platform == "win32" else []

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
    icon="assets/icon.ico" if sys.platform == "win32" else "assets/icon.icns",
    console=False,
    upx=False,
    codesign_identity=SIGN_ID,
    entitlements_file="installer/entitlements.plist" if SIGN_ID else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ShinobiCam", upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="ShinobiCam.app",
        icon="assets/icon.icns",
        bundle_identifier="com.binarybuilders.shinobicam",
        info_plist={
            # Without this key macOS terminates the app on first webcam access.
            "NSCameraUsageDescription": "ShinobiCam usa la webcam per riconoscere il sigillo e applicare l'effetto.",
            "NSHighResolutionCapable": True,
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "LSMinimumSystemVersion": "13.0",
        },
    )
