#!/usr/bin/env python3
"""
status.py —— 查询 DMR 当前播放状态
=====================================
返回：传输状态、播放位置、总时长、音量、当前媒体 URI
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


def main():
    method_name = sys.argv[1] if len(sys.argv) > 1 else "unknown"

    raw = sys.stdin.read().strip()
    try:
        params = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        print(f"[{method_name}] Invalid params JSON: {raw[:200]}", file=sys.stderr)
        sys.exit(1)

    dmr_udn = str(params.get("dmr_udn", "")).strip()

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
        rc_service = get_service(dmr, "RenderingControl")

        result_data = {"dmr_name": getattr(dmr, "name", "")}

        # 传输状态
        if avt_service:
            try:
                transport_info = call_action_sync(avt_service, "GetTransportInfo", InstanceID=0)
                result_data["transport_state"] = str(transport_info.get("CurrentTransportState", ""))
                result_data["transport_status"] = str(transport_info.get("CurrentTransportStatus", ""))
                result_data["playback_speed"] = str(transport_info.get("CurrentSpeed", ""))
            except Exception:
                pass

            # 播放位置
            try:
                pos_info = call_action_sync(avt_service, "GetPositionInfo", InstanceID=0)
                result_data["track"] = int(pos_info.get("Track", 0) or 0)
                result_data["track_duration"] = str(pos_info.get("TrackDuration", ""))
                result_data["track_metadata"] = str(pos_info.get("TrackMetaData", ""))
                result_data["current_uri"] = str(pos_info.get("TrackURI", ""))
                result_data["relative_time"] = str(pos_info.get("RelTime", ""))
                result_data["absolute_time"] = str(pos_info.get("AbsTime", ""))
            except Exception:
                pass

            # 媒体信息
            try:
                media_info = call_action_sync(avt_service, "GetMediaInfo", InstanceID=0)
                result_data["media_duration"] = str(media_info.get("MediaDuration", ""))
                result_data["current_uri"] = result_data.get("current_uri") or str(media_info.get("CurrentURI", ""))
                result_data["nr_of_tracks"] = int(media_info.get("NrTracks", 0) or 0)
            except Exception:
                pass

        # 音量
        if rc_service:
            try:
                vol = call_action_sync(rc_service, "GetVolume", InstanceID=0, Channel="Master")
                result_data["volume"] = int(vol.get("CurrentVolume", 0) or 0)
            except Exception:
                pass
            try:
                mute = call_action_sync(rc_service, "GetMute", InstanceID=0, Channel="Master")
                result_data["mute"] = bool(mute.get("CurrentMute", False))
            except Exception:
                pass

        output_json(0, "ok", result_data)

    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        output_json(-1, f"查询状态失败: {e}")


if __name__ == "__main__":
    main()
