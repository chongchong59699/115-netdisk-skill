#!/usr/bin/env python3
"""
115 网盘共享工具库
提供客户端初始化、格式化等公共函数。
"""

import os
import sys
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional, Union

MIN_PYTHON = (3, 12)
COOKIES_PATH = Path("~/.115-cookies").expanduser()
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
VENV_DIR = SKILL_DIR / ".venv"
VENV_PYTHON = VENV_DIR / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
REEXEC_ENV = "P115_SKILL_VENV_REEXEC"
BASE_INFO_URL = "https://qrcodeapi.115.com/app/1.0/web/1.0/user/base_info"
USER_INFO_URL = "https://my.115.com/proapi/3.0/index.php?method=user_info"
STORAGE_INFO_URL = "https://115.com/index.php?ct=ajax&ac=get_storage_info"
FILE_LOGIN_HINT = "提示：当前 cookies 可能不适用于文件接口，请重新运行: python scripts/login.py --app web --no-open"
HTTP_JSON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Encoding": "identity",
}

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
    patch_p115client_default_parse()
    return P115Client


def patch_p115client_default_parse() -> None:
    """Patch p115client 0.0.8.4.9 JSON detection until upstream fixes it."""
    try:
        import p115client.client as client_mod
    except Exception:
        return
    if getattr(client_mod.default_parse, "_p115_skill_patched", False):
        return

    def fixed_default_parse(_, content):
        if not isinstance(content, (bytes, bytearray, memoryview)):
            content = memoryview(content)
        view = memoryview(content)
        if view and bytes(view[:1]) + bytes(view[-1:]) not in (b"{}", b"[]", b'""'):
            try:
                content = client_mod.ecdh_aes_decrypt(view)
            except Exception:
                content = view
        return client_mod.json_loads(memoryview(content))

    fixed_default_parse._p115_skill_patched = True
    client_mod.default_parse = fixed_default_parse


def configure_client(client: Any, cookies: str) -> Any:
    """Make p115client use stable browser-like headers and the raw Cookie header."""
    client.headers["cookie"] = cookies
    client.headers["user-agent"] = HTTP_JSON_HEADERS["User-Agent"]
    client.headers["accept"] = HTTP_JSON_HEADERS["Accept"]
    client.headers["accept-encoding"] = HTTP_JSON_HEADERS["Accept-Encoding"]
    return client


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
    cookies = load_cookies(path)
    client = P115Client(path, check_for_relogin=True)
    configure_client(client, cookies)
    if logged_in:
        print_client_summary(client)
        print_capabilities()
    return client


def get_client_from_cookies(cookies: str):
    """Create a configured client from an in-memory cookie string."""
    P115Client = import_p115client()
    return configure_client(P115Client(cookies, check_for_relogin=True), cookies)


def concise_error(exc: BaseException, limit: int = 300) -> str:
    """Return a short error string safe for CLI output."""
    text = str(exc).replace("\r", " ").replace("\n", " ")
    if len(text) > limit:
        return text[:limit].rstrip() + "..."
    return text


def looks_like_login_error(value: Any) -> bool:
    """Detect common 115 login-expired responses."""
    text = str(value)
    return any(token in text for token in ("请先登录", "登录超时", "重新登录", "40101032", "990001"))


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
        hint = f"\n   {FILE_LOGIN_HINT}" if looks_like_login_error(response) else ""
        fail(f"❌ {action}失败: {message}\n   原始响应: {response}{hint}")
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


def request_115_json(url: str, cookies: str) -> dict:
    """Fetch a 115 JSON endpoint without p115client's parser."""
    headers = {**HTTP_JSON_HEADERS, "Cookie": cookies}
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {raw}") from exc
    return json.loads(raw)


def response_is_success(response: Any) -> bool:
    if not isinstance(response, dict):
        return False
    state = response.get("state")
    return not (state is False or state == 0 or state == "0" or state == "false")


def normalize_basic_info(user_info: Optional[dict], base_info: Optional[dict], storage: Optional[dict]) -> dict:
    """Normalize 115 account and storage responses for display."""
    user_data = (user_info or {}).get("data") if isinstance(user_info, dict) else {}
    base_data = (base_info or {}).get("data") if isinstance(base_info, dict) else {}
    user_data = user_data if isinstance(user_data, dict) else {}
    base_data = base_data if isinstance(base_data, dict) else {}
    vip_info = base_data.get("vip_info") if isinstance(base_data.get("vip_info"), dict) else {}
    if not storage and base_data.get("size_total_raw") is not None:
        storage = {
            "1": {
                "total": base_data.get("size_total_raw"),
                "used": base_data.get("size_used_raw"),
            }
        }
    return {
        "user_name": base_data.get("user_name") or user_data.get("user_name"),
        "user_id": base_data.get("display_uid") or base_data.get("user_id") or user_data.get("display_uid") or user_data.get("user_id"),
        "vip": base_data.get("vip") or vip_info.get("level_name") or user_data.get("is_vip"),
        "vip_expire": vip_info.get("expire_date") or base_data.get("expire"),
        "storage": storage or {},
    }


def load_basic_info(
    client: Any = None,
    cookies_path: Optional[Union[str, Path]] = None,
    cookies: Optional[str] = None,
) -> dict:
    """Load account and storage info, falling back to direct JSON endpoints."""
    cookie_text = cookies or load_cookies(cookies_path)
    user_info = None
    base_info = None
    storage = None
    errors = []

    if client is None:
        if sys.version_info < MIN_PYTHON:
            errors.append("SDK 初始化失败: 当前 Python 环境低于 3.12，已改用直接 JSON 接口")
        else:
            try:
                client = get_client_from_cookies(cookie_text)
            except SystemExit as exc:
                errors.append(f"SDK 初始化失败: 当前 Python 环境不可用，退出码 {exc.code}")
            except Exception as exc:
                errors.append(f"SDK 初始化失败: {concise_error(exc)}")

    if client is not None:
        try:
            candidate = client.user_info()
            if response_is_success(candidate):
                user_info = candidate
            else:
                raise RuntimeError(candidate)
        except Exception as exc:
            errors.append(f"SDK 账户信息失败: {concise_error(exc)}")
        try:
            storage = client.fs_storage_info()
            if not isinstance(storage, dict) or "1" not in storage:
                raise RuntimeError(storage)
        except Exception as exc:
            errors.append(f"SDK 存储信息失败: {concise_error(exc)}")

    if user_info is None:
        try:
            user_info = request_115_json(USER_INFO_URL, cookie_text)
        except Exception as exc:
            errors.append(f"HTTP 账户信息失败: {concise_error(exc)}")
    try:
        base_info = request_115_json(BASE_INFO_URL, cookie_text)
        if not response_is_success(base_info):
            errors.append(f"HTTP 基本信息失败: {base_info}")
    except Exception as exc:
        errors.append(f"HTTP 基本信息失败: {concise_error(exc)}")
    if storage is None:
        try:
            storage = request_115_json(STORAGE_INFO_URL, cookie_text)
        except Exception as exc:
            errors.append(f"HTTP 存储信息失败: {concise_error(exc)}")

    summary = normalize_basic_info(user_info, base_info, storage)
    summary["errors"] = errors
    return summary


def print_basic_summary(summary: dict) -> None:
    """Print normalized account and storage information."""
    print("\n═══ 账户信息 ═══")
    print(f"  用户名: {summary.get('user_name')}")
    print(f"  用户ID: {summary.get('user_id')}")
    print(f"  VIP:    {summary.get('vip')}")
    if summary.get("vip_expire"):
        print(f"  到期:   {summary.get('vip_expire')}")

    print("\n═══ 存储空间 ═══")
    storage = summary.get("storage") if isinstance(summary.get("storage"), dict) else {}
    type_names = {'1': '主存储', '4': '备份存储'}
    if not storage:
        print("  (未获取到存储信息)")
        if any(looks_like_login_error(error) for error in summary.get("errors", [])):
            print(f"  {FILE_LOGIN_HINT}")
        return
    for type_id, sinfo in storage.items():
        if not isinstance(sinfo, dict):
            continue
        name = type_names.get(str(type_id), f'类型{type_id}')
        total = format_size(sinfo.get('total', 0))
        used = format_size(sinfo.get('used', 0))
        pct = sinfo.get('used', 0) / sinfo.get('total', 1) * 100 if sinfo.get('total') else 0
        print(f"  {name}: {used} / {total} ({pct:.1f}%)")


def print_basic_summary_from_cookies(cookies: str) -> None:
    """Print account summary from an in-memory cookie string."""
    print_basic_summary(load_basic_info(cookies=cookies))


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
        print_basic_summary(load_basic_info(client=client))
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
