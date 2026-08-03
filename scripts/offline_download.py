#!/usr/bin/env python3
"""
115 网盘离线下载管理。

用法:
    python3 offline_download.py 'magnet:?xt=urn:btih:xxx'     # 添加磁力下载
    python3 offline_download.py 'ed2k://|file|xxx|...'        # 添加 ed2k 下载
    python3 offline_download.py 'https://example.com/file.zip' # 添加 HTTP 下载
    python3 offline_download.py --list                         # 查看离线任务
    python3 offline_download.py --quota                        # 查看配额
    python3 offline_download.py --path                         # 查看下载目录
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import client_method, fail, format_size, get_client, require_success


def response_payload(response: dict, action: str) -> dict:
    """Return the nested data object when an API wraps its payload."""
    response = require_success(response, action)
    data = response.get('data')
    return data if isinstance(data, dict) else response


def add_download(client, url: str, save_path: str = None):
    """添加离线下载任务。"""
    params = {"url": url}
    if save_path:
        params["savepath"] = save_path

    result = client_method(client, "offline_add_url")(params)
    require_success(result, "添加离线下载")
    print("✅ 下载任务已添加!")
    task = result.get('result') or result.get('data') or {}
    if isinstance(task, dict):
        print(f"   文件: {task.get('name', task.get('file_name', '?'))}")
        print(f"   大小: {format_size(task.get('size', task.get('file_size', 0)))}")
    return result


def list_tasks(client):
    """列出离线下载任务。"""
    tasks = response_payload(client_method(client, "offline_list")(), "获取离线任务")
    count = tasks.get('count', tasks.get('total_count', tasks.get('total', 0)))
    quota = tasks.get('quota', '?')
    total = tasks.get('total', tasks.get('quota_total', '?'))

    print(f"📊 离线配额: {quota} / {total}")
    print(f"📋 任务数量: {count}")

    task_list = tasks.get('tasks') or tasks.get('list') or []
    if not isinstance(task_list, list):
        fail(f"❌ 获取离线任务失败: 任务列表字段不是列表\n   原始响应: {tasks}")
    if not task_list:
        print("  (无任务)")
        return

    print()
    for t in task_list:
        name = t.get('name', t.get('file_name', '?'))
        size = format_size(t.get('size', t.get('file_size', 0)))
        status = t.get('status', '?')
        pct = t.get('percentDone', t.get('progress', '?'))

        status_icon = '✅' if status == 2 else '⏳' if status == 1 else '❌'
        print(f"  {status_icon} {name} ({size}) - {pct}%")


def read_quota(client) -> dict:
    """Read offline quota, falling back to the task list on newer SDKs."""
    try:
        return response_payload(client_method(client, "offline_quota_info")(), "获取离线配额")
    except SystemExit:
        raise
    except Exception:
        return response_payload(client_method(client, "offline_list")(), "获取离线配额")


def show_quota(client):
    """显示离线配额。"""
    quota = read_quota(client)
    print(f"📊 离线下载配额: {quota.get('quota', '?')} / {quota.get('total', '?')}")


def show_paths(client):
    """显示离线下载目录配置。"""
    paths = require_success(client_method(client, "offline_download_path")(), "获取离线下载目录")
    dirs = paths.get('data', [])
    if isinstance(dirs, dict):
        dirs = dirs.get('list') or dirs.get('paths') or []
    if not isinstance(dirs, list):
        fail(f"❌ 获取离线下载目录失败: 目录字段不是列表\n   原始响应: {paths}")
    if not dirs:
        print("  (未配置下载目录)")
        return
    for d in dirs:
        selected = '⭐' if d.get('is_selected') == '1' else '  '
        print(f"  {selected} {d.get('file_name', '?')} (ID: {d.get('file_id', '?')})")


def main():
    client = get_client()

    if '--list' in sys.argv:
        list_tasks(client)
    elif '--quota' in sys.argv:
        show_quota(client)
    elif '--path' in sys.argv:
        print("📂 离线下载目录:")
        show_paths(client)
    elif len(sys.argv) > 1:
        url = sys.argv[1]
        save_path = sys.argv[2] if len(sys.argv) > 2 else None
        print(f"⬇️ 添加离线下载: {url[:80]}{'...' if len(url) > 80 else ''}")
        add_download(client, url, save_path)
    else:
        print("用法:")
        print("  python3 offline_download.py <URL> [保存目录]")
        print("  python3 offline_download.py --list")
        print("  python3 offline_download.py --quota")
        print("  python3 offline_download.py --path")


if __name__ == '__main__':
    main()
