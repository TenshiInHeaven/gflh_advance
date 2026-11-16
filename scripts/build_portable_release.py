#!/usr/bin/env python3
"""Build a self-contained Windows portable TargetForge release.

Uses the official python.org Windows embeddable distribution and installs the
runtime dependencies into its Lib/site-packages. The result can be unzipped and
started without any system Python.

Usage (from the repository root, with a normal Python/pip available):

    python scripts/build_portable_release.py
    python scripts/build_portable_release.py --skip-deps   # reuse cached deps

Output:
    dist/TargetForge-<version>-portable-x64.zip
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"
CACHE_DIR = BUILD_DIR / "cache"


def _app_version() -> str:
    for line in (ROOT / "targetforge" / "app.py").read_text(encoding="utf-8").splitlines():
        if line.startswith("VERSION = "):
            return line.split("=", 1)[1].strip().strip('"')
    return "dev"


def _download(url: str, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and target.stat().st_size > 0:
        print(f"[cache] {target.name}")
        return target
    print(f"[download] {url}")
    tmp = target.with_suffix(target.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as response, tmp.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    tmp.replace(target)
    return target


def _extract_python(python_zip: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    with zipfile.ZipFile(python_zip) as archive:
        archive.extractall(dest)
    # Embeddable Python ships a ._pth that intentionally disables site.
    pth_files = list(dest.glob("python*._pth"))
    if not pth_files:
        raise RuntimeError("embeddable Python 中没有找到 python*._pth")
    pth = pth_files[0]
    lines = pth.read_text(encoding="utf-8").splitlines()
    wanted = ["Lib\\site-packages", "..\\app"]
    changed = False
    for item in wanted:
        if item not in lines:
            lines.append(item)
            changed = True
    # Site is needed for packages that register namespace/package metadata.
    normalized = []
    for line in lines:
        if line.strip() == "#import site":
            normalized.append("import site")
        else:
            normalized.append(line)
    pth.write_text("\n".join(normalized) + "\n", encoding="utf-8")


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    print(">", " ".join(cmd))
    subprocess.run(cmd, cwd=str(cwd or ROOT), check=True)


def _install_deps(python_dir: Path, skip_deps: bool) -> None:
    site_packages = python_dir / "Lib" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)
    if skip_deps:
        print("[cache] 跳过依赖安装；请确保 python/Lib/site-packages 已有依赖")
        return
    pip = [sys.executable, "-m", "pip", "install", "--target", str(site_packages),
           "--upgrade", "--no-warn-script-location", "--disable-pip-version-check"]
    # Core runtime. requirements.lock includes hashes and optional deps only in
    # requirements-emulator.txt, so install both explicitly.
    _run(pip + ["gflzirc==0.4.4", "requests"])
    # Bridge / emulator features are optional, but a portable build should be
    # feature-complete. Missing network here is a hard error so the release is
    # never silently shipped without its advertised functionality.
    _run(pip + ["mitmproxy>=11.0", "cryptography>=42.0"])


def _copy_runtime(app_dir: Path) -> None:
    app_dir.mkdir(parents=True, exist_ok=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".pytest_cache")
    shutil.copytree(ROOT / "targetforge", app_dir / "targetforge", ignore=ignore)
    # Remove developer-only tests/tools from the shipped app image.
    for name in ("tests", "tools"):
        target = app_dir / "targetforge" / name
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
    for name in ("project_paths.py", "local_paths.example.json", "README.md",
                 "LICENSE", "ACKNOWLEDGEMENTS.md"):
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, app_dir / name)
    docs = ROOT / "docs"
    if docs.is_dir():
        shutil.copytree(docs, app_dir / "docs", ignore=ignore)
    # Only runtime data: never copy creds, tokens, logs, capture events, CA or
    # settings from the developer's local data directory.
    data_src = ROOT / "dataMiner" / "derived" / "targetforge"
    data_dst = app_dir / "dataMiner" / "derived" / "targetforge"
    data_dst.mkdir(parents=True, exist_ok=True)
    for name in ("catalog.json", "reserve_audit.json"):
        source = data_src / name
        if source.is_file():
            shutil.copy2(source, data_dst / name)
    icons = data_src / "icons"
    if icons.is_dir():
        shutil.copytree(icons, data_dst / "icons", ignore=ignore)


def _write_launcher(app_dir: Path, version: str) -> None:
    launcher = app_dir.parent / "Start TargetForge.bat"
    launcher.write_text(
        "@echo off\r\n"
        "setlocal\r\n"
        "cd /d \"%~dp0app\"\r\n"
        "set PYTHONUTF8=1\r\n"
        "\"%~dp0python\\python.exe\" -m targetforge --open\r\n"
        "echo.\r\n"
        "echo TargetForge 已退出。按任意键关闭窗口。\r\n"
        "pause >nul\r\n",
        encoding="utf-8",
    )
    readme = app_dir.parent / "README-PORTABLE.txt"
    readme.write_text(
        f"TargetForge {version} Portable\r\n"
        "===============================\r\n\r\n"
        "1. 解压整个文件夹到任意位置（路径不要含特殊符号）。\r\n"
        "2. 双击 Start TargetForge.bat。\r\n"
        "3. 浏览器会自动打开带 token 的本地地址；如果没打开，看黑色窗口里的链接。\r\n"
        "4. 退出：关闭黑色窗口即可；抓包页面要先点“完成并关闭代理”。\r\n\r\n"
        "本包自带 Python 运行时，不需要系统安装 Python。\r\n"
        "首次启动时 Windows 防火墙可能询问是否允许本机回环端口，允许即可。\r\n",
        encoding="utf-8",
    )


def _make_zip(portable_dir: Path, version: str) -> Path:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    archive = DIST_DIR / f"TargetForge-{version}-portable-x64"
    result = shutil.make_archive(str(archive), "zip", root_dir=portable_dir.parent,
                                 base_dir=portable_dir.name)
    return Path(result)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build self-contained TargetForge portable release")
    parser.add_argument("--python-version", default=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    parser.add_argument("--skip-deps", action="store_true", help="reuse existing extracted python/site-packages")
    parser.add_argument("--keep-build", action="store_true", help="keep build/TargetForge-portable directory")
    args = parser.parse_args()

    version = _app_version()
    tag = f"python-{args.python_version}-embed-amd64"
    python_zip = _download(
        f"https://www.python.org/ftp/python/{args.python_version}/"
        f"python-{args.python_version}-embed-amd64.zip",
        CACHE_DIR / f"{tag}.zip",
    )

    portable = BUILD_DIR / "TargetForge-portable"
    if portable.exists():
        shutil.rmtree(portable)
    python_dir = portable / "python"
    _extract_python(python_zip, python_dir)
    print("[deps] installing into portable Python...")
    _install_deps(python_dir, args.skip_deps)

    app_dir = portable / "app"
    print("[runtime] copying app...")
    _copy_runtime(app_dir)
    _write_launcher(app_dir, version)

    # Smoke test: embedded interpreter can import the app and all dependencies.
    check = subprocess.run(
        [str(python_dir / "python.exe"), "-c",
         "import sys; sys.path.insert(0, r'%s'); import targetforge, gflzirc, requests, mitmproxy; print('portable-import-ok')" % app_dir],
        cwd=str(app_dir), capture_output=True, text=True, timeout=120,
    )
    print(check.stdout.strip())
    if check.returncode != 0:
        print(check.stderr[-4000:], file=sys.stderr)
        raise SystemExit("portable smoke test failed")

    target = _make_zip(portable, version)
    print(f"[done] {target}")
    print(f"[size] {target.stat().st_size / 1024 / 1024:.1f} MB")
    if not args.keep_build:
        # Keep the python/deps cache but drop the expanded portable tree.
        shutil.rmtree(portable, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
