"""游戏客户端目录：校验 / 自动检测 / 应用 / 启动引导（v1.9）。

有效游戏目录 = 目录存在 + 含 ``GrilsFrontLine.exe``（大小写不敏感）+
``*_Data/StreamingAssets/Res/Pc/stc``（stc 表目录）。

- :func:`validate` → ``(valid, missing_codes)``，missing 代码见 :data:`MISSING_MESSAGES`
- :func:`detect` → 候选列表 ``[{path, source, valid, missing}]``（运行中进程 → Steam → 常见路径）
- :func:`apply` → 写仓库根 ``local_paths.json``（gitignore）+ 设 ``GF1_GAME_ROOT`` + 清
  ``unit_model.core`` 相关 ``lru_cache``
- :func:`bootstrap` → 启动时按 settings.game_root → env → local_paths → 自动检测顺序解析
  （检测到的路径不自动保存，等用户在设置里确认）
- :func:`pick_folder` → Windows 原生文件夹选择框（PowerShell FolderBrowserDialog，STA），
  取消/超时/无桌面分别抛 :class:`GamePathError`

published repo 布局：``targetforge`` 与 ``unit_model``、``project_paths.py`` 同级，
``datapaths.ROOT`` 就是仓库根（local_paths.json 写在这里）。
"""
from __future__ import annotations

import base64
import importlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Iterable

from targetforge.datapaths import ROOT

#: 游戏主程序（大小写不敏感比较）
GAME_EXE_NAME = "GrilsFrontLine.exe"
GAME_EXE_LOWER = GAME_EXE_NAME.lower()
#: 游戏目录环境变量（unit_model/project_paths 读取）
ENV_GAME_ROOT = "GF1_GAME_ROOT"
#: local_paths.json（仓库根，gitignore）
LOCAL_PATHS_FILE = ROOT / "local_paths.json"
LOCAL_PATHS_KEY = "gf1_game_root"
#: stc 表目录相对 *_Data 的路径
STC_SUBPATH = ("StreamingAssets", "Res", "Pc", "stc")
#: 检测缓存时间（秒）：避免前端轮询 status 时反复跑 PowerShell/注册表
DETECT_TTL = 20.0
#: 文件夹选择框超时（秒）
PICK_TIMEOUT = 60.0
#: 常见 Steam 安装路径模板（相对盘符根）
COMMON_STEAM_SUBDIRS = (
    "Program Files (x86)/Steam/steamapps/common",
    "Program Files/Steam/steamapps/common",
    "SteamLibrary/steamapps/common",
    "steam/steamapps/common",
    "Games/steamapps/common",
)
#: 扫描 Steam common 目录时优先看名字带这些关键字的子目录
GAME_NAME_KEYWORDS = ("frontline", "girls", "gril")
#: 进程枚举用的 PowerShell（Get-Process 优先，CIM 兜底）
_PROCESS_SCRIPT = (
    "$p = Get-Process -Name 'GrilsFrontLine' -ErrorAction SilentlyContinue | "
    "Where-Object { $_.Path } | Select-Object -First 1; "
    "if ($p) { $p.Path } else { "
    "try { $q = Get-CimInstance Win32_Process "
    "-Filter \"Name='GrilsFrontLine.exe'\" -ErrorAction SilentlyContinue | "
    "Select-Object -First 1; if ($q) { $q.ExecutablePath } } catch {} }"
)
#: 文件夹选择框 PowerShell（STA 由调用方传 -STA）
_PICK_SCRIPT = (
    "Add-Type -AssemblyName System.Windows.Forms; "
    "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
    "$d.Description = '选择少女前线客户端目录（包含 GrilsFrontLine.exe 的那一层）'; "
    "$d.UseDescriptionForTitle = $true; $d.ShowNewFolderButton = $false; "
    "$r = $d.ShowDialog(); "
    "if ($r -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $d.SelectedPath }"
)

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

#: missing 代码 → 中文提示（validate 只返回代码，展示时映射）
MISSING_MESSAGES: dict[str, str] = {
    "missing_path": "缺少游戏目录路径",
    "missing_dir": "目录不存在",
    "not_dir": "路径不是文件夹",
    "missing_exe": f"未找到 {GAME_EXE_NAME}",
    "missing_data": "未找到 *_Data 目录",
    "missing_stc": ("缺少 StreamingAssets/Res/Pc/stc 目录，"
                    "不是有效的少女前线客户端目录"),
}
#: missing 代码的展示优先级（error 字段取第一条）
_MISSING_PRIORITY = ("missing_path", "missing_dir", "not_dir",
                     "missing_exe", "missing_data", "missing_stc")
#: apply 时清理缓存的 unit_model 模块
_CACHE_MODULES = (
    "unit_model.core.paths",
    "unit_model.core.stc",
    "unit_model.core.catchdata",
    "unit_model.core.attributes",
    "unit_model.core.enemy",
    "unit_model.core.equipment",
    "unit_model.core.external",
    "unit_model.core.gundata",
)

_DETECT_CACHE: dict[str, Any] = {"at": 0.0, "items": []}


class GamePathError(Exception):
    """游戏目录相关可展示错误（app.py 转成 400 + error/hint）。"""

    def __init__(self, message: str, *, hint: str = "", code: str = "game_path_error"):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.code = code


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------
def _normalized(path: str | Path) -> Path:
    return Path(str(path).strip()).expanduser()


def find_exe(root: str | Path) -> Path | None:
    """游戏根目录下的 ``GrilsFrontLine.exe``（大小写不敏感）。"""
    folder = _normalized(root)
    if not folder.is_dir():
        return None
    try:
        for child in folder.iterdir():
            if child.is_file() and child.name.lower() == GAME_EXE_LOWER:
                return child
    except OSError:
        return None
    return None


def find_data_dir(root: str | Path) -> Path | None:
    """游戏根目录下的 ``*_Data`` 目录（第一个）。"""
    folder = _normalized(root)
    if not folder.is_dir():
        return None
    try:
        for child in folder.iterdir():
            if child.is_dir() and child.name.lower().endswith("_data"):
                return child
    except OSError:
        return None
    return None


def find_stc_dir(root: str | Path) -> Path | None:
    """``*_Data/StreamingAssets/Res/Pc/stc``（任一个 *_Data 下命中即可）。"""
    folder = _normalized(root)
    if not folder.is_dir():
        return None
    try:
        for child in folder.iterdir():
            if not (child.is_dir() and child.name.lower().endswith("_data")):
                continue
            stc = child.joinpath(*STC_SUBPATH)
            if stc.is_dir():
                return stc
    except OSError:
        return None
    return None


def validate(path: str | Path) -> tuple[bool, list[str]]:
    """校验游戏目录：返回 ``(valid, missing_codes)``。

    missing_codes 取值：``missing_path`` / ``missing_dir`` / ``not_dir`` /
    ``missing_exe`` / ``missing_data`` / ``missing_stc``。
    """
    raw = str(path or "").strip()
    if not raw:
        return False, ["missing_path"]
    folder = _normalized(raw)
    if not folder.exists():
        return False, ["missing_dir"]
    if not folder.is_dir():
        return False, ["not_dir"]
    missing: list[str] = []
    if find_exe(folder) is None:
        missing.append("missing_exe")
    data_dir = find_data_dir(folder)
    if data_dir is None:
        missing.append("missing_data")
    elif find_stc_dir(folder) is None:
        missing.append("missing_stc")
    return (not missing), missing


def missing_messages(missing: Iterable[str]) -> list[str]:
    """missing 代码 → 中文提示列表（按优先级排序）。"""
    codes = set(missing)
    ordered = [code for code in _MISSING_PRIORITY if code in codes]
    ordered += sorted(codes - set(ordered))
    return [MISSING_MESSAGES.get(code, code) for code in ordered]


def describe_missing(missing: Iterable[str]) -> str:
    messages = missing_messages(missing)
    return "；".join(messages) if messages else ""


def normalize_root(path: str | Path) -> Path:
    """绝对化并尽量 resolve（失败时退回 absolute）。"""
    folder = _normalized(path)
    try:
        return folder.resolve()
    except OSError:
        return folder.absolute()


# ---------------------------------------------------------------------------
# 运行中进程 / Steam / 常见路径检测
# ---------------------------------------------------------------------------
def _powershell(script: str, *, timeout: float = 10.0) -> str:
    """执行 PowerShell 脚本并返回 stdout（UTF-8）；非 Windows 或失败返回空串。"""
    if os.name != "nt":
        return ""
    command = [
        "powershell", "-NoProfile", "-NonInteractive",
        "-EncodedCommand", _encode_powershell(script),
    ]
    try:
        proc = subprocess.run(
            command, capture_output=True, timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    output = proc.stdout or b""
    for encoding in ("utf-8", "gbk"):
        try:
            return output.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return output.decode("utf-8", "replace").strip()


def _encode_powershell(script: str) -> str:
    raw = script.encode("utf-16-le")
    return base64.b64encode(raw).decode("ascii")


def running_game_process() -> str:
    """正在运行的 ``GrilsFrontLine.exe`` 完整路径；未运行返回空串。"""
    if os.name != "nt":
        return ""
    text = _powershell(_PROCESS_SCRIPT, timeout=10.0)
    for line in text.splitlines():
        candidate = line.strip().strip('"')
        if candidate.lower().endswith(GAME_EXE_LOWER):
            return candidate
    return ""


def running_game_root() -> tuple[str, str]:
    """``(exe_path, root_dir)``；未运行返回 ``("", "")``。"""
    exe_path = running_game_process()
    if not exe_path:
        return "", ""
    root = Path(exe_path).parent
    return exe_path, str(root)


def _steam_install_dirs() -> list[Path]:
    """Steam 安装目录：注册表 HKCU/HKLM（Windows）。"""
    if os.name != "nt":
        return []
    candidates: list[Path] = []
    try:
        import winreg  # type: ignore[import-not-found]

        def _read(root_key, sub_key: str, value_name: str) -> None:
            try:
                with winreg.OpenKey(root_key, sub_key) as key:
                    raw, _type = winreg.QueryValueEx(key, value_name)
            except OSError:
                return
            if raw:
                candidates.append(Path(str(raw)))

        _read(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath")
        _read(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam",
              "InstallPath")
        _read(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath")
    except Exception:  # noqa: BLE001 - 注册表不可用时静默降级
        return candidates
    return candidates


def _steam_library_paths() -> list[Path]:
    """Steam 库目录（解析 ``steamapps/libraryfolders.vdf`` 的 path 项）。"""
    paths: list[Path] = []
    for install_dir in _steam_install_dirs():
        if install_dir.is_dir():
            paths.append(install_dir)
        vdf = install_dir / "steamapps" / "libraryfolders.vdf"
        if not vdf.is_file():
            continue
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in re.finditer(r'"path"\s+"([^"]+)"', text):
            raw = match.group(1).replace("\\\\", "\\")
            library = Path(raw)
            if library.is_dir():
                paths.append(library)
    return paths


def _candidate_from_process() -> list[dict]:
    exe_path, root = running_game_root()
    if not exe_path:
        return []
    return [{"path": root, "source": "process", "exe": exe_path}]


def _candidate_from_steam() -> list[dict]:
    results: list[dict] = []
    seen: set[str] = set()
    for library in _steam_library_paths():
        common = library / "steamapps" / "common"
        if not common.is_dir():
            continue
        try:
            children = sorted(common.iterdir(), key=lambda item: item.name.lower())
        except OSError:
            continue
        for child in children:
            if not child.is_dir():
                continue
            name = child.name.lower()
            if not any(keyword in name for keyword in GAME_NAME_KEYWORDS):
                continue
            key = str(child.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            results.append({"path": str(child), "source": "steam"})
    return results


def _candidate_from_common_paths() -> list[dict]:
    results: list[dict] = []
    seen: set[str] = set()
    drives = "CDEFGH"
    for letter in drives:
        drive = Path(f"{letter}:\\")
        if not drive.is_dir():
            continue
        for subdir in COMMON_STEAM_SUBDIRS:
            base = drive / Path(subdir)
            if not base.is_dir():
                continue
            try:
                children = sorted(base.iterdir(), key=lambda item: item.name.lower())
            except OSError:
                continue
            for child in children:
                if not child.is_dir():
                    continue
                name = child.name.lower()
                if not any(keyword in name for keyword in GAME_NAME_KEYWORDS):
                    continue
                key = str(child.resolve()).lower()
                if key in seen:
                    continue
                seen.add(key)
                results.append({"path": str(child), "source": "common_paths"})
    # local_paths.json 里已配置的路径也算常见候选（source 单独标记）
    current = str(read_local_paths().get(LOCAL_PATHS_KEY) or "").strip()
    if current and Path(current).expanduser().is_dir():
        key = str(normalize_root(current)).lower()
        if key not in seen:
            seen.add(key)
            results.append({"path": current, "source": "local_paths"})
    return results


def _annotate_candidates(entries: list[dict]) -> list[dict]:
    annotated: list[dict] = []
    seen: set[str] = set()
    for entry in entries:
        folder = _normalized(entry.get("path") or "")
        key = str(normalize_root(folder)).lower() if str(folder) else ""
        if not key or key in seen:
            continue
        seen.add(key)
        valid, missing = validate(folder)
        item = {"path": str(normalize_root(folder)), "source": entry.get("source") or "",
                "valid": valid, "missing": missing}
        if entry.get("exe"):
            item["exe"] = entry["exe"]
        annotated.append(item)
    return annotated


def detect(*, force: bool = False, ttl: float = DETECT_TTL) -> list[dict]:
    """检测候选游戏目录（进程 → Steam → 常见路径），按路径去重。

    返回 ``[{path, source, valid, missing}]``；有效候选排在前面（稳定顺序）。
    结果短时缓存 ``ttl`` 秒，``force=True`` 强制重算。
    """
    now = time.time()
    if not force and _DETECT_CACHE["items"] and now - float(_DETECT_CACHE["at"]) <= ttl:
        return [dict(item) for item in _DETECT_CACHE["items"]]
    entries: list[dict] = []
    try:
        entries.extend(_candidate_from_process())
    except Exception:  # noqa: BLE001 - 检测失败不影响后续来源
        pass
    try:
        entries.extend(_candidate_from_steam())
    except Exception:  # noqa: BLE001
        pass
    try:
        entries.extend(_candidate_from_common_paths())
    except Exception:  # noqa: BLE001
        pass
    annotated = _annotate_candidates(entries)
    annotated.sort(key=lambda item: (not item["valid"],))
    _DETECT_CACHE["at"] = now
    _DETECT_CACHE["items"] = annotated
    return [dict(item) for item in annotated]


def detect_best() -> dict | None:
    """第一个有效候选；没有返回 ``None``。"""
    for item in detect():
        if item.get("valid"):
            return {"path": item["path"], "source": item.get("source") or "",
                    "exe": item.get("exe")}
    return None


# ---------------------------------------------------------------------------
# local_paths.json / 环境变量 / 缓存
# ---------------------------------------------------------------------------
def read_local_paths() -> dict:
    """读 ``local_paths.json``；不存在/损坏时返回空 dict。"""
    if not LOCAL_PATHS_FILE.is_file():
        return {}
    try:
        data = json.loads(LOCAL_PATHS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_local_paths(root: str | Path) -> Path:
    """把 ``gf1_game_root`` 写进 ``local_paths.json``（保留其它键，原子替换）。"""
    data = read_local_paths()
    data[LOCAL_PATHS_KEY] = str(normalize_root(root))
    LOCAL_PATHS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = LOCAL_PATHS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(LOCAL_PATHS_FILE)
    return LOCAL_PATHS_FILE


def clear_game_caches() -> list[str]:
    """清 ``unit_model.core`` 里依赖游戏目录的 ``lru_cache``，返回清理的函数名列表。"""
    cleared: list[str] = []
    for module_name in _CACHE_MODULES:
        try:
            module = importlib.import_module(module_name)
        except Exception:  # noqa: BLE001 - 模块不存在/导入失败时跳过
            continue
        for name, value in list(vars(module).items()):
            cache_clear = getattr(value, "cache_clear", None)
            if callable(cache_clear):
                try:
                    cache_clear()
                except Exception:  # noqa: BLE001
                    continue
                cleared.append(f"{module_name}.{name}")
    return cleared


def apply(path: str | Path, *, persist: bool = True) -> dict:
    """应用游戏目录：校验 → 写 local_paths.json（可选）→ 设 env → 清缓存。

    返回 ``{ok, path, saved, local_paths_file, env, cleared, ...}``；
    校验失败返回 ``{ok: False, error, missing, missing_codes, path}``。
    """
    raw = str(path or "").strip()
    valid, missing = validate(raw)
    if not valid:
        return {
            "ok": False,
            "path": raw,
            "error": describe_missing(missing),
            "missing": missing_messages(missing),
            "missing_codes": missing,
        }
    root = normalize_root(raw)
    saved = False
    local_file = ""
    if persist:
        written = write_local_paths(root)
        saved = True
        local_file = str(written)
    os.environ[ENV_GAME_ROOT] = str(root)
    cleared = clear_game_caches()
    return {
        "ok": True,
        "path": str(root),
        "saved": saved,
        "local_paths_file": local_file,
        "env": ENV_GAME_ROOT,
        "cleared": cleared,
        "missing": [],
        "missing_codes": [],
    }


# ---------------------------------------------------------------------------
# 启动引导 / 状态
# ---------------------------------------------------------------------------
def resolve_current_root(settings: dict | None = None) -> tuple[str, str]:
    """按 settings → env → local_paths 解析当前配置的目录，返回 ``(path, source)``。"""
    configured = str((settings or {}).get("game_root") or "").strip()
    if configured:
        return configured, "settings"
    env_value = str(os.environ.get(ENV_GAME_ROOT) or "").strip()
    if env_value:
        return env_value, "env"
    local_value = str(read_local_paths().get(LOCAL_PATHS_KEY) or "").strip()
    if local_value:
        return local_value, "local_paths"
    return "", ""


def bootstrap(settings: dict | None = None, *, auto_detect: bool = True) -> dict:
    """启动引导：settings.game_root → env → local_paths → 自动检测。

    只设置进程内 ``GF1_GAME_ROOT`` 并清缓存；**不自动保存**未在设置中确认的路径
    （检测到的候选仅本次启动生效，用户需在设置里确认）。
    """
    tried: list[dict] = []
    for source, raw in (
        ("settings", str((settings or {}).get("game_root") or "").strip()),
        ("env", str(os.environ.get(ENV_GAME_ROOT) or "").strip()),
        ("local_paths", str(read_local_paths().get(LOCAL_PATHS_KEY) or "").strip()),
    ):
        if not raw:
            continue
        valid, missing = validate(raw)
        if valid:
            applied = apply(raw, persist=False)
            return {
                "ok": True, "path": applied["path"], "source": source,
                "detected": False, "saved": False, "cleared": applied["cleared"],
                "tried": tried,
            }
        tried.append({"source": source, "path": raw,
                      "error": describe_missing(missing),
                      "missing": missing_messages(missing),
                      "missing_codes": missing})
    if auto_detect:
        best = detect_best()
        if best:
            applied = apply(best["path"], persist=False)
            return {
                "ok": True, "path": applied["path"], "source": "detected",
                "detected": True, "saved": False, "cleared": applied["cleared"],
                "detected_source": best.get("source") or "", "tried": tried,
            }
    return {
        "ok": False, "path": "", "source": None, "detected": False,
        "saved": False, "cleared": [], "tried": tried,
        "error": "未找到有效的少女前线客户端目录",
        "hint": "请在设置中选择游戏客户端目录（包含 GrilsFrontLine.exe 的那一层）。",
    }


def status(settings: dict | None = None, *, catalog_ready: bool = True,
           include_detected: bool = True, include_process: bool = True,
           include_missing_messages: bool = True) -> dict:
    """游戏目录配置状态（供 /api/game/status 与 health 摘要使用）。

    ``include_detected=False / include_process=False`` 时不做 PowerShell/注册表检测
    （health 用轻量模式，避免阻塞）。
    """
    settings = settings or {}
    path, source = resolve_current_root(settings)
    local_paths_configured = False
    try:
        local_paths_configured = bool(
            str((read_local_paths() or {}).get(LOCAL_PATHS_KEY) or "").strip()
        )
    except Exception:  # noqa: BLE001
        local_paths_configured = False
    configured = bool(str(settings.get("game_root") or "").strip()) or local_paths_configured
    exists = bool(path and Path(path).expanduser().exists())
    valid = False
    missing: list[str] = []
    if path:
        valid, missing = validate(path)
    game_running = False
    process_path = ""
    if include_process:
        try:
            process_path, _root = running_game_root()
            game_running = bool(process_path)
        except Exception:  # noqa: BLE001
            game_running, process_path = False, ""
    detected = None
    if include_detected:
        try:
            detected = detect_best()
        except Exception:  # noqa: BLE001
            detected = None
    payload: dict[str, Any] = {
        "configured": configured,
        "path": str(normalize_root(path)) if path else "",
        "source": source or None,
        "exists": exists,
        "valid": valid,
        "missing": missing_messages(missing) if include_missing_messages else missing,
        "missing_codes": missing,
        "game_running": game_running,
        "process_path": process_path,
        "detected": detected,
        "catalog_ready": bool(catalog_ready),
        "needs_setup": (not configured) or (not valid),
        "selected_at": settings.get("game_selected_at"),
        "local_paths_file": str(LOCAL_PATHS_FILE),
    }
    return payload


# ---------------------------------------------------------------------------
# 文件夹选择框
# ---------------------------------------------------------------------------
def pick_folder(*, timeout: float = PICK_TIMEOUT) -> str:
    """打开 Windows 原生文件夹选择框，返回选中路径。

    取消 → :class:`GamePathError`（"已取消"）；超时 / 无桌面 / 无 PowerShell 也会抛
    带 ``hint`` 的 :class:`GamePathError`，由 app.py 转成 400 提示。
    """
    if os.name != "nt":
        raise GamePathError(
            "当前系统不支持文件夹选择框",
            hint="请手动输入游戏目录路径（包含 GrilsFrontLine.exe 的那一层）。",
            code="pick_not_supported",
        )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-STA",
             "-EncodedCommand", _encode_powershell(_PICK_SCRIPT)],
            capture_output=True, timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as exc:
        raise GamePathError(
            "选择目录超时",
            hint=f"文件夹选择框 {int(timeout)} 秒内没有响应，请重试或手动输入路径。",
            code="pick_timeout",
        ) from exc
    except OSError as exc:
        raise GamePathError(
            "无法打开文件夹选择框",
            hint="当前环境没有可用的桌面/PowerShell，请手动输入路径。",
            code="pick_unavailable",
        ) from exc
    output = proc.stdout or b""
    text = ""
    for encoding in ("utf-8", "gbk"):
        try:
            text = output.decode(encoding).strip()
            break
        except UnicodeDecodeError:
            continue
    else:
        text = output.decode("utf-8", "replace").strip()
    lines = [line.strip().strip('"') for line in text.splitlines() if line.strip()]
    selected = lines[-1] if lines else ""
    if not selected:
        raise GamePathError(
            "已取消",
            hint="你取消了文件夹选择，可重试或手动输入游戏目录路径。",
            code="pick_cancelled",
        )
    return selected
