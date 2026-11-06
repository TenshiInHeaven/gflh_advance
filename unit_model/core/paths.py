"""模拟作战模块的数据源路径。

数据来源分三类：

1. **本机游戏客户端**（首选，离线、权威、与当前版本一致）
   - ``StreamingAssets/Res/Pc/stc/catchdata.dat``：XOR + gzip 的 JSONL，**自带字段名**，
     覆盖 51 张表（枪种基础值、等级曲线、装备强化增量、全局配置等）。
   - ``StreamingAssets/Res/Pc/stc/*.stc``：251 张二进制表，**不自描述**，需列名映射
     （见 ``stc_mapping``）。
2. **本模块自己的缓存**（``cache/``，不入 Git）：把解出的明文落到本地，避免重复解码。
3. **外部公开仓库**（可选，仅在缺表时使用）：如 ``randomqwerty/GFLData``。

游戏目录取自 ``project_paths.gf1_game_root()``（``local_paths.json`` 或 ``GF1_GAME_ROOT``）。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

BATTLE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BATTLE_DIR / "cache"
TABLES_DIR = CACHE_DIR / "tables"
STC_MAPPING_DIR = CACHE_DIR / "stc-mapping"
EXTERNAL_DIR = CACHE_DIR / "external"

#: 解析后的 ``catchdata`` JSONL（每行一个 ``{表名: [...]}``）
CATCHDATA_JSONL = CACHE_DIR / "catchdata.jsonl"


def game_root() -> Path:
    """少前 1 游戏安装根目录。"""
    from project_paths import require_gf1_game_root

    return require_gf1_game_root()


@lru_cache(maxsize=1)
def res_pc_dir() -> Path:
    """``StreamingAssets/Res/Pc`` 资源目录（哈希命名的 .ab 与 stc 表都在这里）。"""
    root = game_root()
    candidates = [p for p in root.iterdir() if p.is_dir() and p.name.endswith("_Data")]
    if not candidates:
        raise FileNotFoundError(f"未找到 Unity Data 目录：{root}")
    res = candidates[0] / "StreamingAssets" / "Res" / "Pc"
    if not res.is_dir():
        raise FileNotFoundError(f"未找到资源目录：{res}")
    return res


def stc_dir() -> Path:
    """``stc`` 表目录。"""
    directory = res_pc_dir() / "stc"
    if not directory.is_dir():
        raise FileNotFoundError(f"未找到 STC 目录：{directory}")
    return directory


def catchdata_dat() -> Path:
    """客户端落地在本机的 ``catchdata.dat``。"""
    path = stc_dir() / "catchdata.dat"
    if not path.is_file():
        raise FileNotFoundError(f"未找到 catchdata.dat：{path}")
    return path


def external_json(name: str) -> Path:
    """外部公开仓库下载的 JSON（例如 ``gun.json``）。"""
    return EXTERNAL_DIR / name


def ensure_dirs() -> None:
    for directory in (CACHE_DIR, TABLES_DIR, STC_MAPPING_DIR, EXTERNAL_DIR):
        directory.mkdir(parents=True, exist_ok=True)
