#!/usr/bin/env python3
"""
list_files.py —— 列出 SMB 共享目录下的文件
===========================================
stdin/stdout 协议：
  输入(stdin): 宿主传入的智能体参数 {"path": "subdir"}（可选）
  输出(stdout): {"code":0, "msg":"ok", "data":{"path":"...", "smb_connection":{...}, "items":[...], "total": N}}
  方法名:      sys.argv[1] = "smb.file.list"

每个文件项包含 smb_url 字段，可直接用于 SMB 访问。
配置从 plugin.json 读取，无需宿主传参。
"""
import sys
import json
import traceback
from urllib.parse import quote

from smb_utils import (
    connect_smb,
    disconnect_smb,
    list_directory,
    normalize_path,
    output_json,
    get_smb_config,
    get_smb_connection_info,
)


def build_smb_url(conn_info: dict, target_path: str, filename: str) -> str:
    """构造单个文件的 SMB 访问 URL，密码中的特殊字符做 URL 编码"""
    server = conn_info["server"]
    share = conn_info["share"]
    username = conn_info["username"]
    password = conn_info["password"]

    # 拼接路径
    path_parts = []
    if share:
        path_parts.append(share)
    if target_path:
        path_parts.append(target_path)
    path_parts.append(quote(filename, safe="/"))
    file_path = "/".join(path_parts)

    # smb://username:password@server/share/base_path/filename
    # 密码中的 @ : / 等特殊字符需要 URL 编码，防止解析歧义
    if username:
        encoded_user = quote(username, safe="")
        encoded_pass = quote(password, safe="")
        return f"smb://{encoded_user}:{encoded_pass}@{server}/{file_path}"
    else:
        return f"smb://{server}/{file_path}"


def main():
    method_name = sys.argv[1] if len(sys.argv) > 1 else "unknown"

    raw = sys.stdin.read().strip()
    try:
        params = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        print(f"[{method_name}] Invalid params JSON: {raw[:200]}", file=sys.stderr)
        sys.exit(1)

    config = get_smb_config()
    base_path = str(config.get("smb_base_path", "")).strip()
    sub_path = str(params.get("path", "")).strip()

    target_path = normalize_path(base_path, sub_path)
    conn_info = get_smb_connection_info()

    conn, sess, tree = None, None, None
    try:
        conn, sess, tree = connect_smb()
        entries = list_directory(tree, target_path if target_path else "")

        # 为每个文件构造 smb_url
        for entry in entries:
            entry["smb_url"] = build_smb_url(conn_info, target_path, entry["name"])

        output_json(
            0,
            "ok",
            {
                "path": target_path or "(根目录)",
                "smb_connection": conn_info,
                "items": entries,
                "total": len(entries),
            },
        )
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        output_json(-1, str(e))
    finally:
        disconnect_smb(conn, sess, tree)


if __name__ == "__main__":
    main()
