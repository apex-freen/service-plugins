#!/usr/bin/env python3
"""
browse.py —— 浏览 DMS 上的媒体内容目录
===========================================
stdin/stdout 协议：
  输入(stdin): {"dms_udn": "...", "object_id": "0", "browse_flag": "BrowseDirectChildren"}
  输出(stdout): {"code":0, "msg":"ok", "data":{"dms_name":"...", "object_id":"...", "items":[...], "total": N}}
"""
import sys
import json
import traceback
import xml.etree.ElementTree as ET

from dlna_utils import (
    output_json,
    resolve_device,
    get_service,
    call_action_sync,
)


DIDL_NS = "urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
DC_NS = "http://purl.org/dc/elements/1.1/"
UPNP_NS = "urn:schemas-upnp-org:metadata-1-0/upnp/"


def _parse_didl(didl_xml: str) -> list:
    """解析 DIDL-Lite XML，提取媒体条目信息"""
    items = []
    if not didl_xml:
        return items

    try:
        root = ET.fromstring(didl_xml)
    except ET.ParseError:
        return items

    for elem in root:
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag not in ("item", "container"):
            continue

        entry = {
            "id": elem.get("id", ""),
            "parent_id": elem.get("parentID", ""),
            "type": "directory" if tag == "container" else "file",
            "title": "",
            "artist": "",
            "album": "",
            "genre": "",
            "res_url": "",
            "res_protocol": "",
            "res_size": 0,
            "res_duration": "",
            "class": "",
        }

        for child in elem:
            child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if child_tag == "title":
                entry["title"] = child.text or ""
            elif child_tag == "creator" or child_tag == "artist":
                entry["artist"] = child.text or ""
            elif child_tag == "album":
                entry["album"] = child.text or ""
            elif child_tag == "genre":
                entry["genre"] = child.text or ""
            elif child_tag == "class":
                entry["class"] = child.text or ""
            elif child_tag == "res":
                entry["res_url"] = child.text or ""
                entry["res_protocol"] = child.get("protocolInfo", "")
                try:
                    entry["res_size"] = int(child.get("size", "0") or "0")
                except ValueError:
                    entry["res_size"] = 0
                entry["res_duration"] = child.get("duration", "") or ""

        items.append(entry)

    return items


def main():
    method_name = sys.argv[1] if len(sys.argv) > 1 else "unknown"

    raw = sys.stdin.read().strip()
    try:
        params = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        print(f"[{method_name}] Invalid params JSON: {raw[:200]}", file=sys.stderr)
        sys.exit(1)

    dms_udn = str(params.get("dms_udn", "")).strip()
    object_id = str(params.get("object_id", "0")).strip() or "0"
    browse_flag = str(params.get("browse_flag", "BrowseDirectChildren")).strip() or "BrowseDirectChildren"

    try:
        dms = resolve_device(
            udn=dms_udn,
            default_udn_key="default_dms_udn",
            default_name_key="default_dms_name",
            device_role="DMS",
        )
        if not dms:
            output_json(-1, "未找到 DMS 设备。请传入 dms_udn，或在 plugin.json 中配置 default_dms_udn / default_dms_name")

        cd_service = get_service(dms, "ContentDirectory")
        if not cd_service:
            output_json(-1, f"设备 {dms.name} 不支持 ContentDirectory 服务，不是有效的 DMS")

        result = call_action_sync(
            cd_service,
            "Browse",
            ObjectID=object_id,
            BrowseFlag=browse_flag,
            Filter="*",
            StartingIndex=0,
            RequestedCount=0,
            SortCriteria="",
        )

        didl_xml = result.get("Result", "")
        items = _parse_didl(didl_xml)
        number_returned = int(result.get("NumberReturned", len(items)) or len(items))
        total_matches = int(result.get("TotalMatches", len(items)) or len(items))

        # 排序：目录在前，文件在后，同类按标题
        items.sort(key=lambda x: (0 if x["type"] == "directory" else 1, x["title"].lower()))

        output_json(
            0,
            "ok",
            {
                "dms_name": getattr(dms, "name", ""),
                "object_id": object_id,
                "browse_flag": browse_flag,
                "items": items,
                "returned": number_returned,
                "total": total_matches,
            },
        )
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        output_json(-1, f"浏览 DMS 失败: {e}")


if __name__ == "__main__":
    main()
