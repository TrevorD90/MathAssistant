# PyInstaller spec for MathAssistant (spec §12.1). Build with packaging/build.py,
# or from the repo root:  pyinstaller packaging/mathassistant.spec --noconfirm
#
# Output: dist/MathAssistant/ (Windows folder with MathAssistant.exe) or
#         dist/MathAssistant.app (macOS). One build per OS; PyInstaller does
#         not cross-compile.
# ruff: noqa  (PyInstaller injects Analysis/PYZ/EXE/COLLECT/BUNDLE/SPECPATH)

import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "backend/mathassistant/__init__.py").read_text()).group(1)
ICON = ROOT / "build" / "icon.png"
if not (ROOT / "web" / "dist" / "index.html").exists():
    raise SystemExit("web/dist is missing: run `npm run build` in web/ first (packaging/build.py does this).")

datas = [(str(ROOT / "web" / "dist"), "web_dist")]   # the built frontend (paths.web_dist_dir)
datas += collect_data_files("sympy")                  # incl. the LaTeX parser's .lark grammars
datas += collect_data_files("lark")                   # lark's own common grammars
datas += copy_metadata("keyring")                     # keyring finds OS backends via entry points
datas += copy_metadata("anthropic")

hiddenimports = (
    collect_submodules("uvicorn")                     # uvicorn loads protocols/loops by name
    + collect_submodules("keyring.backends")
    + ["mathassistant.providers.demo_provider"]
)
if sys.platform == "win32":
    hiddenimports += ["win32ctypes.core", "win32ctypes.pywin32.win32cred"]

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "backend")],
    datas=datas,
    hiddenimports=hiddenimports,
    # Dev/test-only packages that must never ship.
    excludes=["pytest", "_pytest", "httpx", "dotenv", "IPython", "matplotlib", "numpy", "PIL"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MathAssistant",
    console=False,              # windowed: the small control window is the UI anchor
    icon=str(ICON) if ICON.exists() else None,
    upx=False,                  # UPX-packed exes trigger more antivirus false positives
)
coll = COLLECT(exe, a.binaries, a.datas, name="MathAssistant", upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="MathAssistant.app",
        icon=str(ICON) if ICON.exists() else None,
        bundle_identifier="io.github.trevord90.mathassistant",
        version=VERSION,
        info_plist={
            "CFBundleName": "MathAssistant",
            "CFBundleDisplayName": "MathAssistant",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
