#!/usr/bin/env python3
"""
115 QR-code login helper.

Uses only the Python standard library to generate a local QR image, wait for the
user to scan it with the 115 app, and save cookies to ~/.115-cookies.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


TOKEN_URL = "https://qrcodeapi.115.com/api/1.0/web/1.0/token/"
STATUS_URL = "https://qrcodeapi.115.com/get/status/"
QR_URL = "https://qrcodeapi.115.com/api/1.0/mac/1.0/qrcode?uid={uid}"
VALID_APPS = {
    "web",
    "android",
    "ios",
    "linux",
    "mac",
    "windows",
    "tv",
    "alipaymini",
    "wechatmini",
    "qandroid",
}
PREFERRED_COOKIE_KEYS = ("UID", "CID", "SEID", "KID")
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
VENV_PYTHON = SKILL_DIR / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")


@dataclass
class LoginResult:
    cookies: str
    cookie_path: Path
    qr_path: Path
    raw_login_data: Dict[str, Any]


def fail(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def print_flush(message: str) -> None:
    print(message, flush=True)


def print_qr_instructions(qr_file: Path, qr_url: str) -> None:
    markdown = f"![115 登录二维码]({qr_file.as_posix()})"
    agent_instruction = (
        "show this QR image to the user immediately, then keep the login process "
        "running until scan confirmation completes"
    )
    payload = {
        "type": "115-login-qr",
        "action": "show-image-immediately",
        "image_path": str(qr_file),
        "image_uri": qr_file.as_uri(),
        "remote_url": qr_url,
        "markdown": markdown,
        "instruction": "请用 115 App 扫码，并在手机上确认登录。",
        "agent_instruction": agent_instruction,
    }
    print_flush("请用 115 App 扫码确认登录：")
    print_flush(f"AGENT_ACTION_REQUIRED: {agent_instruction}")
    print_flush(f"QR_IMAGE_PATH: {qr_file}")
    print_flush(f"QR_FILE_URI: {qr_file.as_uri()}")
    print_flush(f"QR_REMOTE_URL: {qr_url}")
    print_flush(f"QR_MARKDOWN: {markdown}")
    print_flush(f"LOGIN_QR_JSON: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}")
    print_flush(f"如果 agent 没有成功展示图片，请手动打开该文件扫码：{qr_file}")


def resolve_user_path(path: Any) -> Path:
    return Path(path).expanduser().resolve()


def request_json(url: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    body = None
    headers = {"User-Agent": "115-netdisk-skill/1.0"}
    if data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {raw}") from exc
    response = json.loads(raw)
    state = response.get("state")
    if state is False or state == 0 or state == "0" or state == "false":
        message = response.get("error") or response.get("msg") or raw
        raise RuntimeError(message)
    return response


def response_data(response: Dict[str, Any], action: str) -> Dict[str, Any]:
    data = response.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"{action} failed: response has no object data field: {response}")
    return data


def download_qr_image(qr_url: str, qr_path: Path) -> None:
    request = urllib.request.Request(qr_url, headers={"User-Agent": "115-netdisk-skill/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        image = response.read()
    qr_path.parent.mkdir(parents=True, exist_ok=True)
    qr_path.write_bytes(image)
    try:
        os.chmod(qr_path, 0o600)
    except OSError:
        pass


def format_cookies(cookies: Dict[str, Any]) -> str:
    parts: List[str] = []
    used: Set[str] = set()
    for key in PREFERRED_COOKIE_KEYS:
        value = cookies.get(key)
        if value:
            parts.append(f"{key}={value}")
            used.add(key)
    for key in sorted(cookies):
        if key not in used and cookies[key]:
            parts.append(f"{key}={cookies[key]}")
    return "; ".join(parts)


def save_cookies(cookie_path: Path, cookies: str) -> None:
    cookie_path.parent.mkdir(parents=True, exist_ok=True)
    cookie_path.write_text(cookies.strip(), encoding="utf-8")
    try:
        os.chmod(cookie_path, 0o600)
    except OSError:
        pass


def wait_for_scan(token: Dict[str, Any], poll_interval: int, timeout: int) -> None:
    started = time.monotonic()
    payload = urllib.parse.urlencode(
        {
            "uid": token["uid"],
            "time": token["time"],
            "sign": token["sign"],
        }
    )
    status_url = f"{STATUS_URL}?{payload}"
    while True:
        if timeout > 0 and time.monotonic() - started > timeout:
            raise RuntimeError("二维码等待超时，请重新运行登录脚本。")
        time.sleep(poll_interval)
        try:
            status_data = response_data(request_json(status_url), "获取二维码状态")
        except (TimeoutError, socket.timeout, urllib.error.URLError) as exc:
            print_flush(f"[status=?] 状态接口暂时无响应，继续等待扫码确认... ({exc})")
            continue
        status = int(status_data.get("status", 0))
        if status == 0:
            print_flush("[status=0] 等待扫码...")
        elif status == 1:
            print_flush("[status=1] 已扫码，请在手机上确认登录...")
        elif status == 2:
            print_flush("[status=2] 已确认登录。")
            return
        elif status == -1:
            raise RuntimeError("二维码已过期，请重新运行登录脚本。")
        elif status == -2:
            raise RuntimeError("用户已取消扫码登录。")
        else:
            raise RuntimeError(f"二维码状态异常: {status_data}")


def perform_login(
    app: str = "tv",
    cookie_path: Any = "~/.115-cookies",
    qr_path: Optional[Any] = None,
    no_open: bool = False,
    print_cookie: bool = False,
    poll_interval: int = 2,
    timeout: int = 300,
) -> LoginResult:
    if app not in VALID_APPS:
        raise RuntimeError(f"不支持的 app 类型: {app}")

    cookie_file = resolve_user_path(cookie_path)
    token = response_data(request_json(TOKEN_URL), "获取二维码 token")
    uid = str(token.get("uid") or "")
    if not uid or not token.get("time") or not token.get("sign"):
        raise RuntimeError(f"二维码 token 响应异常: {token}")

    if qr_path:
        qr_file = resolve_user_path(qr_path)
    else:
        qr_file = Path(tempfile.gettempdir()).resolve() / f"115-login-qrcode-{uid}.png"
    qr_url = QR_URL.format(uid=urllib.parse.quote(uid))
    download_qr_image(qr_url, qr_file)

    print_qr_instructions(qr_file, qr_url)
    if not no_open:
        webbrowser.open(qr_file.as_uri())

    wait_for_scan(token, poll_interval=poll_interval, timeout=timeout)

    login_url = f"https://passportapi.115.com/app/1.0/{app}/1.0/login/qrcode/"
    login_data = response_data(
        request_json(login_url, {"app": app, "account": uid}),
        "获取登录结果",
    )
    cookie_map = login_data.get("cookie")
    if not isinstance(cookie_map, dict) or not cookie_map:
        raise RuntimeError(f"登录结果中没有 cookie 字段，可能是 app 类型不可用: {login_data}")
    cookie_text = format_cookies(cookie_map)
    save_cookies(cookie_file, cookie_text)
    print(f"Cookies 已保存到：{cookie_file}")

    if print_cookie:
        print(cookie_text)
    return LoginResult(cookie_text, cookie_file, qr_file, login_data)


def print_capabilities() -> None:
    print("\n本 skill 当前可以执行：")
    print("  - 115 App 扫码登录并保存 cookies")
    print("  - 测试连接，输出账户信息、空间用量和根目录预览")
    print("  - 浏览 115 网盘目录")
    print("  - 搜索文件")
    print("  - 添加磁力、ed2k、HTTP/HTTPS 离线下载任务")
    print("  - 查看离线任务、离线配额和离线下载目录")


def try_print_account_info_with_venv(cookies: str) -> bool:
    if not VENV_PYTHON.exists():
        return False
    try:
        if Path(sys.executable).resolve() == VENV_PYTHON.resolve():
            return False
    except OSError:
        return False

    code = f"""
import sys
sys.path.insert(0, {str(SCRIPT_DIR)!r})
from lib import print_basic_summary_from_cookies

cookies = sys.stdin.read().strip()
print_basic_summary_from_cookies(cookies)
"""
    try:
        completed = subprocess.run(
            [str(VENV_PYTHON), "-c", code],
            input=cookies,
            text=True,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else exc
        print(f"\n扫码登录已完成，但使用 skill 私有 Python 读取账户信息失败：{detail}")
        return False
    print(completed.stdout, end="")
    return True


def try_print_account_info(cookies: str) -> None:
    if try_print_account_info_with_venv(cookies):
        print_capabilities()
        return

    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        from lib import print_basic_summary_from_cookies
    except Exception as exc:
        print("\n已完成扫码登录，但当前 Python 环境暂不能读取账户详情。")
        print(f"原因：{exc}")
        print("请重新运行 skill 安装器，它会创建 .venv 并安装 p115client。")
        print_capabilities()
        return

    try:
        print_basic_summary_from_cookies(cookies)
    except Exception as exc:
        print(f"\n扫码登录已完成，但读取账户信息失败：{exc}")
    print_capabilities()


def main() -> None:
    parser = argparse.ArgumentParser(description="115 App 扫码登录并保存 cookies")
    parser.add_argument("--app", choices=sorted(VALID_APPS), default="tv", help="登录 app 类型，默认 tv")
    parser.add_argument("--cookie-path", default="~/.115-cookies", help="cookies 保存路径")
    parser.add_argument("--qr-path", default="", help="二维码 PNG 保存路径")
    parser.add_argument("--no-open", action="store_true", help="不自动打开二维码图片")
    parser.add_argument("--print-cookie", action="store_true", help="登录成功后打印 cookies")
    parser.add_argument("--poll-interval", type=int, default=2, help="二维码状态轮询间隔秒数")
    parser.add_argument("--timeout", type=int, default=300, help="等待扫码超时秒数；0 表示不超时")
    parser.add_argument("--no-info", action="store_true", help="登录后不尝试输出账户信息")
    args = parser.parse_args()

    try:
        result = perform_login(
            app=args.app,
            cookie_path=args.cookie_path,
            qr_path=args.qr_path or None,
            no_open=args.no_open,
            print_cookie=args.print_cookie,
            poll_interval=args.poll_interval,
            timeout=args.timeout,
        )
    except Exception as exc:
        fail(f"登录失败：{exc}")

    if not args.no_info:
        try_print_account_info(result.cookies)


if __name__ == "__main__":
    main()
