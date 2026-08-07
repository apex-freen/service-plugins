#!/usr/bin/env python3
"""
discover.py —— 扫描发现局域网内的 DLNA 设备
=================================================
stdin/stdout 协议：
  输入(stdin): {"service_type": "all|dms|dmr", "timeout": 5}
  输出(stdout): {"code":0, "msg":"ok", "data":{"devices":[...], "total": N}}
"""
import sys
import json
import traceback

from dlna_utils import (
    output_json,
    discover_devices,
    get_config,
)


def main():
    method_name = sys.argv[1] if len(sys.argv) > 1 else "unknown"

    raw = sys.stdin.read().strip()
    try:
        params = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        print(f"[{method_name}] Invalid params JSON: {raw[:200]}", file=sys.stderr)
        sys.exit(1)

    service_type = str(params.get("service_type", "all")).strip().lower() or "all"
    cfg = get_config()
    timeout = int(params.get("timeout") or cfg.get("discover_timeout", 5))

    try:
        devices = discover_devices(service_filter=service_type, timeout=timeout)

        output_json(
            0,
            "ok",
            {
                "filter": service_type,
                "devices": devices,
                "total": len(devices),
            },
        )
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        output_json(-1, f"设备发现失败: {e}")


if __name__ == "__main__":
    main()
