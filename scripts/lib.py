#!/usr/bin/env python3
"""
115 网盘共享工具库
提供客户端初始化、格式化等公共函数。
"""

import os
import sys
from pathlib import Path
from typing import Optional, Union

MIN_PYTHON = (3, 12)
COOKIES_PATH = Path("~/.115-cookies").expanduser()
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
VENV_DIR = SKILL_DIR / ".venv"
VENV_PYTHON = VENV_DIR / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
REEXEC_ENV = "P115_SKILL_VENV_REEXEC"

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")


def fail(message: str, code: int = 1):
    """Print a user-facing error and exit with a non-zero status."""
    print(message, file=sys.stderr)
    sys.exit(code)


def maybe_reexec_in_skill_venv():
    """Run feature scripts with the skill-managed Python environment when present."""
    if os.environ.get(REEXEC_ENV):
        return
    if not VENV_PYTHON.exists():
        return
    try:
        current = Path(sys.executable).resolve()
        managed = VENV_PYTHON.resolve()
    except OSError:
        return
    if current == managed:
        return
    os.environ[REEXEC_ENV] = "1"
    os.execv(str(managed), [str(managed), *sys.argv])


def ensure_supported_python():
    """p115client currently publishes wheels for Python 3.12+ only."""
    if sys.version_info < MIN_PYTHON:
        version = ".".join(map(str, MIN_PYTHON))
        current = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        fail(
            "❌ 当前 Python 版本不满足 p115client 要求\n"
            f"   当前版本: Python {current}\n"
            f"   需要版本: Python {version}+\n"
            "   请使用 Python 3.12+ 后再运行: python -m pip install p115client"
        )


def import_p115client():
    """Import p115client with a clear remediation message for agents."""
    maybe_reexec_in_skill_venv()
    ensure_supported_python()
    try:
        from p115client import P115Client
    except ModuleNotFoundError as exc:
        if exc.name != "p115client":
            raise
        fail(
            "❌ 缺少依赖: p115client\n"
            "   请重新运行 skill 安装器，它会创建 .venv 并安装 p115client。\n"
            "   如果需要手工修复: python install.py --source-dir ."
        )
    return P115Client


def resolve_cookies_path(cookies_path: Optional[Union[str, Path]] = None) -> Path:
    """Resolve the cookies file path used by all helper scripts."""
    return Path(cookies_path).expanduser() if cookies_path else COOKIES_PATH


def load_cookies(cookies_path: Optional[Union[str, Path]] = None) -> str:
    """从标准路径读取 cookies，不存在则报错退出。"""
    path = resolve_cookies_path(cookies_path)
    if not path.exists():
        fail(
            f"❌ Cookies 文件不存在: {path}\n"
            "   请先运行: python3 scripts/login.py --no-open"
        )
    with path.open(encoding="utf-8") as f:
        cookies = f.read().strip()
    if not cookies:
        fail(
            f"❌ Cookies 文件为空: {path}\n"
            "   请先运行: python3 scripts/login.py --no-open"
        )
    return cookies


def cookies_file_ready(path: Path) -> bool:
    """Return True when the cookies file exists and contains text."""
    if not path.exists():
        return False
    try:
        return bool(path.read_text(encoding="utf-8").strip())
    except OSError:
        return False


def ensure_cookies_or_login(path: Path) -> bool:
    """Start QR login automatically when the standard cookies file is empty."""
    if cookies_file_ready(path):
        return False

    print("首次使用或 cookies 文件为空，需要先完成 115 扫码登录。")
    print("我会生成 115 登录二维码图片；请用 115 App 扫码并在手机上确认。")
    try:
        from login import perform_login

        perform_login(cookie_path=path, no_open=True)
    except Exception as exc:
        fail(f"❌ 115 扫码登录失败: {exc}")
    return True


def get_client(cookies_path: Optional[Union[str, Path]] = None):
    """初始化 P115Client，并用路径传入 cookies 以便续期后写回文件。"""
    maybe_reexec_in_skill_venv()
    path = resolve_cookies_path(cookies_path)
    logged_in = ensure_cookies_or_login(path)
    P115Client = import_p115client()
    load_cookies(path)
    client = P115Client(path, check_for_relogin=True)
    if logged_in:
        print_client_summary(client)
        print_capabilities()
    return client


def require_success(response: dict, action: str) -> dict:
    """Validate common p115client response shape."""
    if not isinstance(response, dict):
        fail(f"❌ {action}失败: 接口返回非字典结构 {type(response).__name__}")
    if response.get("state") is False:
        message = (
            response.get("error")
            or response.get("message")
            or response.get("msg")
            or response.get("errno")
            or "unknown"
        )
        fail(f"❌ {action}失败: {message}\n   原始响应: {response}")
    return response


def get_list_data(response: dict, action: str, key: str = "data") -> list:
    """Return a list payload and fail loudly on unexpected API shapes."""
    require_success(response, action)
    data = response.get(key, [])
    if data is None:
        return []
    if not isinstance(data, list):
        fail(f"❌ {action}失败: 响应字段 {key!r} 不是列表\n   原始响应: {response}")
    return data


def format_size(size_bytes: float) -> str:
    """将字节数格式化为人类可读格式。"""
    try:
        size_bytes = float(size_bytes or 0)
    except (TypeError, ValueError):
        size_bytes = 0
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"


def print_capabilities():
    """Print the user-facing feature list after login."""
    print("\n本 skill 当前可以执行：")
    print("  - 115 App 扫码登录并保存 cookies")
    print("  - 测试连接，输出账户信息、空间用量和根目录预览")
    print("  - 浏览 115 网盘目录")
    print("  - 搜索文件")
    print("  - 添加磁力、ed2k、HTTP/HTTPS 离线下载任务")
    print("  - 查看离线任务、离线配额和离线下载目录")


def print_client_summary(client):
    """Print basic account information after a fresh QR login."""
    try:
        info = require_success(client.user_info(), "读取账户信息")
        user = info.get('data', {})
        print("\n═══ 账户信息 ═══")
        print(f"  用户名: {user.get('user_name')}")
        print(f"  用户ID: {user.get('user_id')}")
        print(f"  VIP:    {user.get('is_vip')}")

        print("\n═══ 存储空间 ═══")
        space = client.fs_storage_info()
        type_names = {'1': '主存储', '4': '备份存储'}
        for type_id, sinfo in space.items():
            name = type_names.get(type_id, f'类型{type_id}')
            total = format_size(sinfo.get('total', 0))
            used = format_size(sinfo.get('used', 0))
            pct = sinfo.get('used', 0) / sinfo.get('total', 1) * 100 if sinfo.get('total') else 0
            print(f"  {name}: {used} / {total} ({pct:.1f}%)")
    except Exception as exc:
        print(f"\n⚠️ 扫码登录已完成，但读取账户信息失败: {exc}")


def print_item(item: dict):
    """格式化打印一个文件/文件夹条目。"""
    name = item.get('n') or item.get('name') or item.get('file_name') or '?'
    if item.get('cid'):  # 文件夹
        print(f"  📁 {name}/ ({item.get('fc', 0)} 项)")
    else:  # 文件
        size = format_size(item.get('s', 0))
        print(f"  📄 {name} ({size})")
