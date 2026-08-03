#!/usr/bin/env python3
"""
测试 115 网盘连接状态，显示完整账户信息。

用法:
    python3 test_connection.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import (
    FILE_LOGIN_HINT,
    client_method,
    concise_error,
    get_client,
    get_list_data,
    load_basic_info,
    looks_like_login_error,
    print_basic_summary,
    print_item,
    require_success,
)


def main():
    print("🔌 正在连接 115 网盘...\n")
    client = get_client()

    # 用户信息和存储空间：SDK 失败时自动降级到直接 JSON 接口。
    summary = load_basic_info(client=client)
    print_basic_summary(summary)

    # 根目录预览
    print("\n═══ 根目录预览 ═══")
    try:
        response = client.fs_files_aps({"cid": 0, "limit": 10})
        if isinstance(response, dict) and response.get("state") is False:
            print(f"  ⚠️ 获取根目录预览失败: {response.get('error') or response.get('message') or response.get('errno')}")
            if looks_like_login_error(response):
                print(f"  {FILE_LOGIN_HINT}")
        else:
            items = get_list_data(response, "获取根目录预览")
            for item in items:
                print_item(item)
    except Exception as exc:
        print(f"  ⚠️ 获取根目录预览失败: {concise_error(exc)}")
        if looks_like_login_error(exc):
            print(f"  {FILE_LOGIN_HINT}")

    # 离线配额
    print("\n═══ 离线下载 ═══")
    try:
        try:
            quota = require_success(client_method(client, "offline_quota_info")(), "获取离线配额")
        except Exception:
            quota = require_success(client_method(client, "offline_list")(), "获取离线配额")
        if isinstance(quota.get('data'), dict):
            quota = quota['data']
        print(f"  配额: {quota.get('quota', '?')} / {quota.get('total', '?')}")
    except Exception as e:
        print(f"  ⚠️ 获取离线配额失败: {concise_error(e)}")

    print("\n✅ 115 网盘基础信息读取完成!")


if __name__ == '__main__':
    main()
