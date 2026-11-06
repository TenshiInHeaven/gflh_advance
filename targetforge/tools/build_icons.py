"""导出小怪头像：游戏 ``character<code>.ab`` → ``ICON_DIR/<code>.png``。

数据来源
--------
游戏客户端 ``StreamingAssets/Res/Pc/*.ab`` 里每个角色包 ``character<code>.ab``
（文件名带 32 位哈希前缀，code 里的下划线会在文件名里被去掉，例如
``Aegis_GA`` → ``<hash>characteraegisga.ab``）内含 512×512 透明底角色图
Texture2D，名字形如 ``pic_<Code>_SS`` / ``pic_<Code>_LL``。

本工具：

1. 取「可收藏队伍用到的小怪 code」（默认读 ``catalog.json`` 的 ``types``
   映射；没有 catalog 时退回 STC 现算，也可用 ``--codes-file`` 手工指定）；
2. **只扫一遍** ``Res/Pc/*.ab`` 文件名建 ``character<归一化 code>`` 索引，
   不逐个加载无关包；
3. 只对需要的 code 用 UnityPy 加载 bundle，优先取 ``pic_<Code>_SS``
   （其次 ``pic_<Code>_SS*``，再次 ``pic_<Code>`` 兜底，例如
   ``M4 SOPMOD IIMod`` 没有 ``_SS`` 命名）；
4. PIL 裁 alpha bbox → 最长边缩放到 160px → 存 ``DATA_DIR/icons/<code>.png``
   （文件名 = code 小写、非字母数字转 ``_``；catalog build 会用同一规则
   ``scan ICON_DIR`` 反查，所以**不要手工改名**）;
5. 输出覆盖率报告（导出 X/需要 Y），失败/缺包不报错继续。

运行（**必须用 .sim 的 Python 3.10 venv**，UnityPy 装在那里）::

    .\\.sim\\Scripts\\python.exe targetforge\\tools\\build_icons.py
    .\\.sim\\Scripts\\python.exe targetforge\\tools\\build_icons.py --force
    .\\.sim\\Scripts\\python.exe targetforge\\tools\\build_icons.py --limit 20   # 调试
    .\\.sim\\Scripts\\python.exe targetforge\\tools\\build_icons.py --codes-file codes.txt

系统 python 没装 UnityPy 时会给出明确提示并以退出码 2 结束（不影响 catalog）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from targetforge.datapaths import CATALOG_FILE, DATA_DIR, ICON_DIR  # noqa: E402

#: 导出图标最长边（前端 <img> 用，160 够清晰也不占体积）
ICON_MAX_PX = 160

#: 报告的简短上限
MISSING_PRINT_LIMIT = 40

_BUNDLE_CHARACTER_RE = re.compile(r"character([a-z0-9]+)\.ab$")
_ICON_UNSAFE_RE = re.compile(r"[^a-z0-9]+")


# ---------------------------------------------------------------------------
# 小工具（与 catalog._icon_filename / _bundle_code_key 保持一致）
# ---------------------------------------------------------------------------
def icon_filename(code: str) -> str:
    stem = _ICON_UNSAFE_RE.sub("_", str(code or "").lower()).strip("_")
    return f"{stem}.png"


def bundle_code_key(code: str) -> str:
    """code → ``character<key>.ab`` 里的归一化 key（去掉所有非字母数字）。"""
    return re.sub(r"[^a-z0-9]+", "", str(code or "").lower())


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# 游戏资源目录
# ---------------------------------------------------------------------------
def res_pc_dir() -> Path:
    """``<GIRLS' FRONTLINE>/<xxx>_Data/StreamingAssets/Res/Pc``。"""
    try:
        from project_paths import require_gf1_game_root

        root = require_gf1_game_root()
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            f"无法定位游戏目录：{exc}\n"
            "请复制 local_paths.example.json 为 local_paths.json 并填写 gf1_game_root，"
            "或设置环境变量 GF1_GAME_ROOT。" ) from exc
    data_dirs = [path for path in root.iterdir()
                 if path.is_dir() and path.name.endswith("_Data")]
    if not data_dirs:
        raise SystemExit(f"游戏根目录下找不到 *_Data 目录：{root}")
    res = data_dirs[0] / "StreamingAssets" / "Res" / "Pc"
    if not res.is_dir():
        raise SystemExit(f"找不到资源目录：{res}")
    return res


# ---------------------------------------------------------------------------
# code 清单
# ---------------------------------------------------------------------------
def codes_from_catalog() -> list[str]:
    """catalog.json 的 ``types`` 映射里所有 code（= 可收藏队伍用到的类型）。"""
    if not CATALOG_FILE.is_file():
        return []
    try:
        payload = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    codes = {
        str(info.get("code") or "").strip()
        for info in (payload.get("types") or {}).values()
        if str(info.get("code") or "").strip()
    }
    return sorted(codes)


def codes_from_stc() -> list[str]:
    """没有 catalog.json 时直接从 STC 现算（可收藏且有编制的队伍用到的 code）。"""
    try:
        from unit_model.core import stc
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            f"读不到 catalog.json，也导入不了 unit_model.core.stc：{exc}\n"
            "先在仓库根目录跑 `python -c \"from targetforge import catalog; catalog.build()\"`，"
            "或用 --codes-file 指定 code 清单。") from exc
    from collections import defaultdict

    teams = {int(row["id"]): row for row in stc.table("enemy_team")}
    slots: dict[int, int] = defaultdict(int)
    for row in stc.table("enemy_in_team"):
        team_id = int(row.get("enemy_team_id") or 0)
        if team_id:
            slots[team_id] += 1
    collectable = {
        team_id for team_id, row in teams.items()
        if str(row.get("targettrain_cancollect")).strip() == "1" and slots.get(team_id)
    }
    type_ids = {
        int(row.get("enemy_character_type_id") or 0)
        for row in stc.table("enemy_in_team")
        if int(row.get("enemy_team_id") or 0) in collectable
    }
    codes = set()
    for row in stc.table("enemy_character_type"):
        if int(row.get("id") or 0) in type_ids:
            code = str(row.get("code") or "").strip()
            if code:
                codes.add(code)
    return sorted(codes)


def load_codes(codes_file: str | None) -> list[str]:
    if codes_file:
        path = Path(codes_file)
        if not path.is_file():
            raise SystemExit(f"--codes-file 不存在：{path}")
        codes = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.strip().startswith("#")]
        return sorted(set(codes))
    codes = codes_from_catalog()
    if not codes:
        print("[info] catalog.json 不存在或没有 types 映射，改从 STC 现算 code 清单")
        codes = codes_from_stc()
    return codes


# ---------------------------------------------------------------------------
# bundle 索引 + 导出
# ---------------------------------------------------------------------------
def index_character_bundles(res: Path) -> dict[str, list[Path]]:
    """``Res/Pc/*.ab`` 文件名 → character<归一化 code>.ab 索引（只扫文件名）。"""
    index: dict[str, list[Path]] = {}
    total = 0
    for path in res.glob("*.ab"):
        total += 1
        match = _BUNDLE_CHARACTER_RE.search(path.name.lower())
        if match:
            index.setdefault(match.group(1), []).append(path)
    for paths in index.values():
        paths.sort(key=lambda item: (len(item.name), item.name))
    print(f"[info] 扫描 {res}：{total} 个 .ab，其中 character 包 {len(index)} 个")
    return index


def _pick_texture(textures: list, code: str):
    """从 Texture2D 列表里挑角色立绘：优先 ``pic_<Code>_SS``，其次 ``*_SS*``。"""
    wanted = f"pic_{code.lower()}_ss"
    ranked: list[tuple[int, object]] = []
    for data in textures:
        name = str(getattr(data, "m_Name", "") or getattr(data, "name", "") or "")
        lowered = name.lower()
        if lowered == wanted:
            rank = 0
        elif lowered == f"pic_{code.lower()}":
            rank = 1  # 没有 _SS（如 M4 SOPMOD IIMod）
        elif lowered.startswith(wanted):
            rank = 2  # pic_<Code>_SS_1 变体
        elif lowered.startswith(f"pic_{code.lower()}") and "_ss" in lowered:
            rank = 3
        elif lowered.startswith(f"pic_{code.lower()}"):
            rank = 4
        elif "pic_" in lowered and "_ss" in lowered:
            rank = 5
        else:
            continue
        ranked.append((rank, data))
    if not ranked:
        return None
    ranked.sort(key=lambda pair: pair[0])
    return ranked[0][1]


def export_icon(code: str, bundle: Path):
    """导出单个 code 的图标（返回 PIL.Image；失败返回 None 并抛错误信息）。"""
    import UnityPy
    from PIL import Image

    env = UnityPy.load(str(bundle))
    textures = []
    try:
        for obj in env.objects:
            if obj.type.name != "Texture2D":
                continue
            data = obj.read()
            textures.append(data)
    finally:
        # 有些版本 env 持有大对象；读完纹理统一释放
        pass
    picked = _pick_texture(textures, code)
    if picked is None:
        return None
    image = picked.image
    if image is None:
        return None
    image = image.convert("RGBA")
    alpha = image.split()[-1]
    try:
        bbox = alpha.getbbox()
    except ValueError:  # pragma: no cover - 异常 alpha
        bbox = None
    if bbox:
        image = image.crop(bbox)
    image.thumbnail((ICON_MAX_PX, ICON_MAX_PX), Image.LANCZOS)
    return image


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导出少前1小怪头像到 TargetForge 数据目录")
    parser.add_argument("--codes-file", default=None,
                        help="code 清单文件（每行一个）；默认读 catalog.json")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 个 code（调试）")
    parser.add_argument("--force", action="store_true", help="已存在的 png 也重新导出")
    parser.add_argument("--quiet", action="store_true", help="减少进度输出")
    args = parser.parse_args(argv)

    try:
        import UnityPy  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError as exc:
        print(f"[error] 缺少依赖：{exc}", file=sys.stderr)
        print("        请用 .sim 的 Python 运行（UnityPy/Pillow 装在该 venv）："
              r" .\.sim\Scripts\python.exe targetforge\tools\build_icons.py",
              file=sys.stderr)
        return 2

    codes = load_codes(args.codes_file)
    if args.limit and args.limit > 0:
        codes = codes[:args.limit]
    if not codes:
        print("[error] 没有可导出的 code（catalog.json 与 STC 都没取到）", file=sys.stderr)
        return 2
    try:
        res = res_pc_dir()
    except SystemExit as exc:  # 保留原有提示
        print(f"[error] {exc}", file=sys.stderr)
        return 2

    ICON_DIR.mkdir(parents=True, exist_ok=True)
    bundle_index = index_character_bundles(res)

    started = time.time()
    exported: list[str] = []
    skipped: list[str] = []
    no_bundle: list[str] = []
    no_texture: list[str] = []
    errors: dict[str, str] = {}
    filename_owner: dict[str, str] = {}

    total = len(codes)
    for position, code in enumerate(codes, 1):
        filename = icon_filename(code)
        target = ICON_DIR / filename
        if target.is_file() and not args.force:
            skipped.append(code)
            filename_owner.setdefault(filename, code)
            continue
        owner = filename_owner.get(filename)
        if owner and owner != code:
            print(f"[warn] {code} 与 {owner} 的图标文件名冲突（{filename}），跳过 {code}")
            errors[code] = "filename-collision"
            continue
        filename_owner[filename] = code
        candidates = bundle_index.get(bundle_code_key(code)) or []
        if not candidates:
            no_bundle.append(code)
            if not args.quiet and (position % 25 == 0 or position == total):
                print(f"[{position}/{total}] {code}: 无 character bundle")
            continue
        image = None
        last_error = ""
        for bundle in candidates:
            try:
                image = export_icon(code, bundle)
            except Exception as exc:  # noqa: BLE001 - 单包失败不影响整体
                last_error = f"{type(exc).__name__}: {exc}"
                image = None
                continue
            if image is not None:
                break
        if image is None:
            no_texture.append(code)
            if last_error:
                errors[code] = last_error
        else:
            try:
                image.save(target, "PNG", optimize=True)
                exported.append(code)
            except OSError as exc:  # pragma: no cover - 磁盘错误
                errors[code] = f"save {type(exc).__name__}: {exc}"
        if not args.quiet and (position % 25 == 0 or position == total):
            elapsed = time.time() - started
            print(f"[{position}/{total}] 已导出 {len(exported)}，"
                  f"跳过 {len(skipped)}，缺图 {len(no_bundle) + len(no_texture)}，"
                  f"{elapsed:.1f}s")
        if position % 50 == 0:  # 控制内存峰值
            import gc

            gc.collect()

    elapsed = time.time() - started
    covered = set(exported) | set(skipped)
    missing = [code for code in codes if code not in covered]
    report = {
        "generated_at": _now_iso(),
        "elapsed_s": round(elapsed, 2),
        "icon_dir": str(ICON_DIR),
        "codes_needed": len(codes),
        "codes_exported": len(exported),
        "codes_skipped_existing": len(skipped),
        "codes_covered": len(covered),
        "coverage": round(len(covered) / len(codes), 3) if codes else 0.0,
        "missing": missing,
        "missing_no_bundle": no_bundle,
        "missing_no_texture": no_texture,
        "errors": errors,
        "res_pc": str(res),
    }
    try:
        (ICON_DIR / "_manifest.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:  # pragma: no cover
        pass

    print()
    print("== 小怪头像导出报告 ==")
    print(f"  需要 code：{len(codes)}；导出 {len(exported)}；已有跳过 {len(skipped)}；"
          f"覆盖 {len(covered)}/{len(codes)} ({report['coverage']:.0%})")
    print(f"  缺 bundle：{len(no_bundle)}；bundle 内无可用贴图：{len(no_texture)}；"
          f"报错：{len(errors)}")
    print(f"  输出目录：{ICON_DIR}")
    print(f"  耗时：{elapsed:.1f}s（{elapsed / max(1, len(codes)):.2f}s/code）")
    if missing:
        print(f"  未覆盖（前 {MISSING_PRINT_LIMIT}）：{', '.join(missing[:MISSING_PRINT_LIMIT])}")
    print("  提示：导出后重建 catalog 才能把 icon 字段写进数据："
          " python -c \"from targetforge import catalog; catalog.build(force=True)\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
