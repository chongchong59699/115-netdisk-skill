#!/usr/bin/env python3
"""
浏览 115 网盘目录。

用法:
    python3 browse.py                  # 浏览根目录
    python3 browse.py <目录ID>         # 浏览指定目录
    python3 browse.py --search <关键词>  # 搜索文件
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import FILE_LOGIN_HINT, concise_error, fail, get_client, get_list_data, looks_like_login_error, print_item


def browse_dir(client, cid: int = 0, page: int = 1, limit: int = 50):
    """浏览指定目录。"""
    try:
        result = client.fs_files_aps({"cid": cid, "limit": limit, "offset": (page - 1) * limit})
    except Exception as exc:
        hint = f"\n   {FILE_LOGIN_HINT}" if looks_like_login_error(exc) else ""
        fail(f"❌ 浏览目录失败: {concise_error(exc)}{hint}")
    items = get_list_data(result, "浏览目录")

    if not items:
        print("  (空目录)")
        return items

    for item in items:
        print_item(item)
    return items


def search_files(client, keyword: str, limit: int = 30):
    """搜索文件。"""
    try:
        result = client.fs_search({"search_value": keyword, "limit": limit})
    except Exception as exc:
        hint = f"\n   {FILE_LOGIN_HINT}" if looks_like_login_error(exc) else ""
        fail(f"❌ 搜索文件失败: {concise_error(exc)}{hint}")
    items = get_list_data(result, "搜索文件")

    if not items:
        print(f"  未找到包含「{keyword}」的文件")
        return items

    for item in items:
        print_item(item)
    return items


def main():
    client = get_client()

    if '--search' in sys.argv:
        idx = sys.argv.index('--search')
        if idx + 1 >= len(sys.argv):
            print("用法: python3 browse.py --search <关键词>")
            sys.exit(1)
        keyword = sys.argv[idx + 1]
        print(f"🔍 搜索: {keyword}\n")
        search_files(client, keyword)
    else:
        try:
            cid = int(sys.argv[1]) if len(sys.argv) > 1 else 0
        except ValueError:
            fail("❌ 目录ID必须是数字")
        print(f"📂 目录 {cid}:\n")
        browse_dir(client, cid)


if __name__ == '__main__':
    main()
