#!/usr/bin/env python3
"""
play.py —— 将媒体推送到 DMR 播放并控制播放状态
===================================================
支持操作：
  - play_url: 推送指定 URL 到 DMR 并播放
  - play: 播放当前媒体
  - pause: 暂停
  - stop: 停止
  - volume: 设置音量
"""
import sys
import json
import traceback

from dlna_utils import (
    output_json,
    resolve_device,
    get_service,
    call_action_sync,
)


def _build_default_metadata(url: str, title: str = "") -> str:
    """构建简单的 DIDL-Lite 元数据 XML"""
    import urllib.parse
    safe_title = title or urllib.parse.urlparse(url).path.split("/")[-1] or "Unknown"
    return (
        f'<?xml version="1.0" encoding="utf-8"?>'
        f'<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"'
        f' xmlns:dc="http://purl.org/dc/elements/1.1/"'
        f' xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
        f'<item id="1" parentID="0" restricted="0">'
        f'<dc:title>{safe_title}</dc:title>'
        f'<upnp:class>object.item.audioItem.musicTrack</upnp:class>'
        f'<res protocolInfo="http-get:*:audio/mpeg:DLNA.ORG_PN=MP3;DLNA.ORG_OP=01;DLNA.ORG_CI=0;'
        f'DLNA.ORG_FLAGS=01700000000000000000000000000000">{url}</res>'
        f'</item>'
        f'</DIDL-Lite>'
    )


def main():
    method_name = sys.argv[1] if len(sys.argv) > 1 else "unknown"

    raw = sys.stdin.read().strip()
    try:
        params = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        print(f"[{method_name}] Invalid params JSON: {raw[:200]}", file=sys.stderr)
        sys.exit(1)

    dmr_udn = str(params.get("dmr_udn", "")).strip()
    action = str(params.get("action", "")).strip().lower()
    url = str(params.get("url", "")).strip()
    metadata = str(params.get("metadata", "")).strip()

    valid_actions = {"play_url", "play", "pause", "stop", "volume"}
    if action not in valid_actions:
        output_json(-1, f"无效的 action: {action}，有效值: {', '.join(sorted(valid_actions))}")

    if action == "play_url" and not url:
        output_json(-1, "action=play_url 时必须提供 url 参数")

    if action == "volume":
        vol = params.get("volume")
        if vol is None:
            output_json(-1, "action=volume 时必须提供 volume 参数 (0-100)")
        try:
            vol_val = int(vol)
            if not 0 <= vol_val <= 100:
                output_json(-1, "volume 必须在 0-100 之间")
        except (TypeError, ValueError):
            output_json(-1, "volume 必须是整数")

    try:
        dmr = resolve_device(
            udn=dmr_udn,
            default_udn_key="default_dmr_udn",
            default_name_key="default_dmr_name",
            device_role="DMR",
        )
        if not dmr:
            output_json(-1, "未找到 DMR 设备。请传入 dmr_udn，或在 plugin.json 中配置 default_dmr_udn / default_dmr_name")

        avt_service = get_service(dmr, "AVTransport")
        if not avt_service:
            output_json(-1, f"设备 {dmr.name} 不支持 AVTransport 服务，不是有效的 DMR")

        result_data = {"dmr_name": getattr(dmr, "name", ""), "action": action}

        if action == "play_url":
            # 1. 设置 URI
            meta = metadata if metadata else _build_default_metadata(url)
            call_action_sync(
                avt_service,
                "SetAVTransportURI",
                InstanceID=0,
                CurrentURI=url,
                CurrentURIMetaData=meta,
            )
            result_data["url"] = url
            # 2. 开始播放
            call_action_sync(avt_service, "Play", InstanceID=0, Speed="1")
            result_data["status"] = "playing"

        elif action == "play":
            call_action_sync(avt_service, "Play", InstanceID=0, Speed="1")
            result_data["status"] = "playing"

        elif action == "pause":
            call_action_sync(avt_service, "Pause", InstanceID=0)
            result_data["status"] = "paused"

        elif action == "stop":
            call_action_sync(avt_service, "Stop", InstanceID=0)
            result_data["status"] = "stopped"

        elif action == "volume":
            rc_service = get_service(dmr, "RenderingControl")
            if not rc_service:
                output_json(-1, f"设备 {dmr.name} 不支持 RenderingControl 服务，无法控制音量")
            call_action_sync(rc_service, "SetVolume", InstanceID=0, Channel="Master", DesiredVolume=vol_val)
            result_data["volume"] = vol_val

        output_json(0, "ok", result_data)

    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        output_json(-1, f"播放控制失败: {e}")


if __name__ == "__main__":
    main()
