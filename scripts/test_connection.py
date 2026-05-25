#!/usr/bin/env python3
"""
测试 115 网盘连接状态，显示完整账户信息。

用法:
    python3 test_connection.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import format_size, get_client, get_list_data, print_item, require_success


def main():
    print("🔌 正在连接 115 网盘...\n")
    client = get_client()

    # 用户信息
    info = require_success(client.user_info(), "连接 115")

    user = info.get('data', {})
    print("═══ 账户信息 ═══")
    print(f"  用户名: {user.get('user_name')}")
    print(f"  用户ID: {user.get('user_id')}")
    print(f"  VIP:    {user.get('is_vip')}")

    # 存储空间
    print("\n═══ 存储空间 ═══")
    space = client.fs_storage_info()
    type_names = {'1': '主存储', '4': '备份存储'}
    for type_id, sinfo in space.items():
        name = type_names.get(type_id, f'类型{type_id}')
        total = format_size(sinfo.get('total', 0))
        used = format_size(sinfo.get('used', 0))
        pct = sinfo.get('used', 0) / sinfo.get('total', 1) * 100 if sinfo.get('total') else 0
        print(f"  {name}: {used} / {total} ({pct:.1f}%)")

    # 根目录预览
    print("\n═══ 根目录预览 ═══")
    items = get_list_data(client.fs_files_aps({"cid": 0, "limit": 10}), "获取根目录预览")
    for item in items:
        print_item(item)

    # 离线配额
    print("\n═══ 离线下载 ═══")
    try:
        quota = require_success(client.offline_quota_info(), "获取离线配额")
        if isinstance(quota.get('data'), dict):
            quota = quota['data']
        print(f"  配额: {quota.get('quota', '?')} / {quota.get('total', '?')}")
    except Exception as e:
        print(f"  ⚠️ 获取离线配额失败: {e}")

    print("\n✅ 115 网盘连接正常!")


if __name__ == '__main__':
    main()
