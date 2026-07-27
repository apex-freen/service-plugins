#!/usr/bin/env python3
"""
delete.py —— 删除 SMB 共享目录下的文件或空目录
================================================
stdin/stdout 协议：
  输入(stdin): 宿主传入的智能体参数 {"path": "file.txt"}
  输出(stdout): {"code":0, "msg":"ok", "data":{"deleted":"...", "type":"file|directory"}}
  方法名:      sys.argv[1] = "smb.file.delete"

配置（smb_server/smb_share/smb_base_path）从 plugin.json 读取，无需宿主传参。
注意: 只能删除空目录，非空目录会返回错误。风险等级为 risk。
"""
import sys
import json
import traceback
from smb_utils import connect_smb, disconnect_smb, delete_item, normalize_path, output_json, get_smb_config


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

    if not sub_path:
        output_json(-1, "缺少必填参数: path")

    target_path = normalize_path(base_path, sub_path)

    conn, sess, tree = None, None, None
    try:
        conn, sess, tree = connect_smb()
        result = delete_item(tree, target_path)

        output_json(0, "ok", result)
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        output_json(-1, str(e))
    finally:
        disconnect_smb(conn, sess, tree)


if __name__ == "__main__":
    main()
