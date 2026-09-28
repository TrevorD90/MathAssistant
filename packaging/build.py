"""Build the downloadable app for THIS computer's OS (spec §12.1).

    .venv/Scripts/python packaging/build.py        (Windows)
    .venv/bin/python packaging/build.py            (macOS)

Steps: build the web app -> draw the icon -> PyInstaller -> self-test the
built app -> zip it into release/. GitHub Actions runs this same script on
Windows and macOS runners (.github/workflows/release.yml).

Needs the dev install plus the packaging extras:
    pip install -e "backend[dev,package]"
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "backend/mathassistant/__init__.py").read_text()).group(1)


def run(cmd: list[str], cwd: Path = ROOT, env: dict | None = None) -> None:
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True, env=env)


def platform_tag() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos-" + ("apple-silicon" if platform.machine() == "arm64" else "intel")
    return sys.platform


def build_web() -> None:
    npm = shutil.which("npm")
    if not npm:
        sys.exit("npm not found: install Node.js 20+")
    web = ROOT / "web"
    run([npm, "ci"], cwd=web)
    run([npm, "run", "build"], cwd=web)


def self_test(app_dir: Path) -> None:
    """Run the built app's --self-test in an isolated data folder."""
    exe = app_dir / ("MathAssistant.exe" if sys.platform == "win32" else "MathAssistant")
    if sys.platform == "darwin":
        exe = ROOT / "dist" / "MathAssistant.app" / "Contents" / "MacOS" / "MathAssistant"
    env = dict(os.environ, MATHASSISTANT_DATA_DIR=str(ROOT / "build" / "selftest-data"),
               MATHASSISTANT_NO_BROWSER="1")
    env.pop("DEV_MODE", None)
    result = subprocess.run([str(exe), "--self-test"], env=env, timeout=180)
    if result.returncode != 0:
        sys.exit(f"built app failed its self-test (exit {result.returncode})")
    print("built app self-test: OK", flush=True)


def zip_output() -> Path:
    out_dir = ROOT / "release"
    out_dir.mkdir(exist_ok=True)
    target = out_dir / f"MathAssistant-{VERSION}-{platform_tag()}.zip"
    if target.exists():
        target.unlink()
    if sys.platform == "darwin":
        # ditto keeps the .app's symlinks, permissions and extended attributes intact.
        run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", "dist/MathAssistant.app", str(target)])
    else:
        src = ROOT / "dist" / "MathAssistant"
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for f in sorted(src.rglob("*")):
                z.write(f, Path("MathAssistant") / f.relative_to(src))
    print(f"release file: {target} ({target.stat().st_size / 1e6:.1f} MB)", flush=True)
    return target


def main() -> None:
    if "--skip-web" not in sys.argv:
        build_web()
    run([sys.executable, str(ROOT / "packaging" / "make_icon.py"), str(ROOT / "build" / "icon.png")])
    run([sys.executable, "-m", "PyInstaller", "packaging/mathassistant.spec", "--noconfirm", "--clean"])
    self_test(ROOT / "dist" / "MathAssistant")
    zip_output()


if __name__ == "__main__":
    main()
