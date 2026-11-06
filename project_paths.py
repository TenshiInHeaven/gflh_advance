"""项目根路径与公共资源目录（其它模块勿写盘符绝对路径）。

``REPO_ROOT`` 为仓库根目录（随 ``project_paths.py`` 位置自动解析）。

**来源**：原 ``E:\\python\\qqbot\\project_paths.py`` 的精简迁移版 —— 只保留与
本工作区（少前 1 号离线模拟作战）相关的路径与游戏目录解析；原仓库里属于
剧情/语料/QQ 机器人业务的目录常量（``document`` 各子目录、``plugins`` 等）已删除。

机器相关路径（Steam 游戏目录）写在 ``local_paths.json``（不入 Git，见
``local_paths.example.json``），或用环境变量 ``GF1_GAME_ROOT`` 覆盖。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

#: 模拟作战引擎（``unit_model/core``）与其它包共用的缓存根
CACHE_ROOT = REPO_ROOT / ".cache"

#: 统一目录
UNIT_MODEL_DIR = REPO_ROOT / "unit_model"
DOCUMENT_DIR = REPO_ROOT / "document"
DATAMINER_DIR = REPO_ROOT / "dataMiner"
DATAMINER_RESOURCES = DATAMINER_DIR / "resources"
TEST_DIR = REPO_ROOT / "test"

#: 离线工具与解包（jiebao）输出根
JIEBAO_DIR = DATAMINER_RESOURCES / "jiebao"

LOCAL_PATHS_FILE = REPO_ROOT / "local_paths.json"
LOCAL_PATHS_EXAMPLE = REPO_ROOT / "local_paths.example.json"
ENV_FILE = REPO_ROOT / ".env"


def insert_repo_root(caller_file: str | Path, *, depth: int = 1) -> Path:
    """将仓库根加入 ``sys.path``（子目录脚本直跑时用）。

    ``depth=1``：调用文件位于仓库根下一级目录，例如 ``jiebao/foo.py``。
    ``depth=2``：再深一层，例如 ``unit_model/core/foo.py`` 用 ``depth=2``。
    """
    import sys

    root = Path(caller_file).resolve().parents[depth]
    text = str(root)
    if text not in sys.path:
        sys.path.insert(0, text)
    return root


def load_local_paths() -> dict:
    """读 ``local_paths.json``；不存在或不是对象时返回空字典。"""
    if not LOCAL_PATHS_FILE.is_file():
        return {}
    data = json.loads(LOCAL_PATHS_FILE.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def gf1_game_root() -> Path | None:
    """少前 1（GIRLS' FRONTLINE）Steam 安装根目录；未配置返回 ``None``。"""
    paths = load_local_paths()
    raw = str(
        paths.get("gf1_game_root")
        or os.environ.get("GF1_GAME_ROOT")
        or ""
    ).strip()
    if not raw:
        return None
    return Path(raw)


def require_gf1_game_root() -> Path:
    """同 :func:`gf1_game_root`，但未配置或目录无效时抛 ``FileNotFoundError``。"""
    root = gf1_game_root()
    if root is None:
        raise FileNotFoundError(
            "未配置少前1游戏目录。请复制 local_paths.example.json 为 local_paths.json "
            "并填写 gf1_game_root，或设置环境变量 GF1_GAME_ROOT。"
        )
    if not root.is_dir():
        raise FileNotFoundError(f"gf1_game_root 不是有效目录：{root}")
    return root
