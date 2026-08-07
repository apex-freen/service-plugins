#!/usr/bin/env python3
"""
dlna_utils.py —— DLNA DMC 插件公共模块（纯标准库实现）
===================================================
封装 DLNA 设备发现、UPnP 服务调用和错误处理逻辑。
完全使用 Python 标准库（urllib, xml.etree.ElementTree, socket）。
支持所有遵循 UPnP AV 标准的 DLNA 设备（DMS / DMR）。
"""
import asyncio
import json
import os
import re
import socket
import sys
import threading
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlparse

# ============================================================
# UPnP 设备类型常量
# ============================================================
UPNP_DMS = "urn:schemas-upnp-org:device:MediaServer:1"
UPNP_DMR = "urn:schemas-upnp-org:device:MediaRenderer:1"

# SSDP 常量
SSDP_MULTICAST_ADDR = "239.255.255.250"
SSDP_PORT = 1900
SSDP_MSEARCH_TEMPLATE = (
    "M-SEARCH * HTTP/1.1\r\n"
    "HOST: 239.255.255.250:1900\r\n"
    'MAN: "ssdp:discover"\r\n'
    "MX: {mx}\r\n"
    "ST: {st}\r\n"
    "\r\n"
)


# ============================================================
# 统一响应输出
# ============================================================

def output_json(code: int, msg: str, data: Any = None) -> None:
    """统一输出 JSON 响应到 stdout"""
    print(json.dumps({"code": code, "msg": msg, "data": data}, ensure_ascii=False, default=str))
    if code != 0:
        sys.exit(1)


# ============================================================
# 插件配置加载
# ============================================================

_plugin_config_cache = None


def load_plugin_config() -> dict:
    """读取当前插件目录下的 plugin.json，结果缓存"""
    global _plugin_config_cache
    if _plugin_config_cache is not None:
        return _plugin_config_cache

    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "plugin.json")

    if not os.path.isfile(config_path):
        output_json(-1, f"插件配置文件不存在: {config_path}")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            _plugin_config_cache = json.load(f)
    except Exception as e:
        output_json(-1, f"读取 plugin.json 失败: {e}")

    return _plugin_config_cache


def get_config() -> dict:
    """获取插件配置（来自 plugin.json config 节）"""
    plugin = load_plugin_config()
    return plugin.get("config", {})


def get_manifest() -> dict:
    """获取插件清单（来自 plugin.json manifest 节）"""
    plugin = load_plugin_config()
    return plugin.get("manifest", {})


# ============================================================
# 数据模型：SimpleDevice / SimpleService
# ============================================================

class SimpleService:
    """轻量级 UPnP 服务对象"""

    def __init__(self, service_type: str, control_url: str, scpd_url: str = ""):
        self.service_type = service_type
        self.control_url = control_url
        self.scpd_url = scpd_url
        # 从 service_type 提取短名称，如 "AVTransport"
        m = re.search(r":service:([^:]+)", service_type)
        self.service_name = m.group(1) if m else service_type

    def __repr__(self):
        return f"SimpleService({self.service_name})"


class SimpleDevice:
    """轻量级 DLNA 设备对象，替代 UpnpDevice"""

    def __init__(self):
        self.name = ""
        self.device_type = ""
        self.udn = ""
        self.location = ""
        self.model_name = ""
        self.manufacturer = ""
        self.services: dict = {}  # key=service_name, value=SimpleService

    def __repr__(self):
        return f"SimpleDevice({self.name}, {self.device_type})"


# ============================================================
# XML 命名空间
# ============================================================
UPNP_DEVICE_NS = "urn:schemas-upnp-org:device-1-0"
UPNP_SERVICE_NS = "urn:schemas-upnp-org:service-1-0"
SOAP_ENV_NS = "http://schemas.xmlsoap.org/soap/envelope/"


# ============================================================
# 设备描述解析（device.xml）
# ============================================================

def _parse_device_xml(location: str, timeout: int = 5) -> SimpleDevice | None:
    """
    获取并解析设备描述文档 (device.xml)。
    纯标准库实现（urllib + ElementTree）。
    """
    try:
        req = urllib.request.Request(location, headers={"User-Agent": "dlna-utils/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            xml_data = resp.read()

        root = ET.fromstring(xml_data)
        device = SimpleDevice()
        device.location = location

        # 提取 base URL
        parsed_loc = urlparse(location)
        base_url = f"{parsed_loc.scheme}://{parsed_loc.hostname}"
        if parsed_loc.port:
            base_url += f":{parsed_loc.port}"

        # 尝试带命名空间
        ns = {"d": UPNP_DEVICE_NS}
        dev_el = root.find(".//d:device", ns)
        if dev_el is None:
            dev_el = root.find(".//device")
            ns = {}

        if dev_el is None:
            return None

        def _findtext(tag):
            if ns:
                el = dev_el.findtext(f"d:{tag}", "", ns)
            else:
                el = dev_el.findtext(tag, "")
            return el or ""

        device.name = _findtext("friendlyName")
        device.device_type = _findtext("deviceType")
        device.model_name = _findtext("modelName")
        device.manufacturer = _findtext("manufacturer")
        device.udn = _findtext("UDN")

        # 解析服务列表
        if ns:
            svc_list = dev_el.findall(".//d:service", ns)
        else:
            svc_list = dev_el.findall(".//service")

        for svc in svc_list:
            if ns:
                st = svc.findtext("d:serviceType", "", ns)
                cu = svc.findtext("d:controlURL", "", ns)
                su = svc.findtext("d:scpdURL", "", ns)
            else:
                st = svc.findtext("serviceType", "")
                cu = svc.findtext("controlURL", "")
                su = svc.findtext("scpdURL", "")

            if not st:
                continue

            # 拼接完整 URL
            control_url = cu if cu.startswith("http") else f"{base_url}{cu}"
            scpd_url = su if su.startswith("http") else f"{base_url}{su}"

            svc_obj = SimpleService(st, control_url, scpd_url)
            device.services[svc_obj.service_name] = svc_obj

        # 如果没有名称，用 UDN 或 device_type 兜底
        if not device.name:
            device.name = device.udn or device.device_type or location

        return device

    except Exception:
        return None


# ============================================================
# SSDP 发现（M-SEARCH + NOTIFY）
# ============================================================

def _classify_device(device_info: dict) -> str:
    """根据设备类型判断是 DMS 还是 DMR"""
    device_type = device_info.get("device_type", "")
    if "MediaServer" in device_type:
        return "DMS"
    elif "MediaRenderer" in device_type:
        return "DMR"
    st = device_info.get("st", "")
    if "MediaServer" in st:
        return "DMS"
    elif "MediaRenderer" in st:
        return "DMR"
    services = device_info.get("services", [])
    service_str = " ".join(services)
    if "ContentDirectory" in service_str:
        return "DMS"
    if "AVTransport" in service_str:
        return "DMR"
    return "UNKNOWN"


def _get_local_ipv4_addresses() -> list:
    """获取本机所有可用的 IPv4 地址"""
    ips = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127.") and ip not in ips:
            ips.append(ip)
    except Exception:
        pass
    return ips


def _get_helper_url() -> str:
    """
    获取 SSDP helper URL。
    优先级：显式配置 > 从 manifest.serverUrl 自动推导 > 空（直接 SSDP）
    """
    cfg = get_config()
    explicit = cfg.get("ssdp_helper_url", "").strip()
    if explicit:
        return explicit

    server_url = get_manifest().get("serverUrl", "").strip()
    if server_url:
        parsed = urlparse(server_url if "://" in server_url else f"http://{server_url}")
        ip = parsed.hostname
        if ip and not ip.startswith("127."):
            return f"http://{ip}:1901"

    return ""


def _discover_via_helper(helper_url: str, timeout: int = 5) -> list:
    """通过宿主机 SSDP relay 服务发现设备"""
    url = f"{helper_url.rstrip('/')}/scan?timeout={min(timeout, 5)}"
    try:
        with urllib.request.urlopen(url, timeout=timeout + 5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("data", {}).get("devices", [])
    except Exception as e:
        print(f"[WARN] SSDP helper 调用失败: {e}", file=sys.stderr)
        return []


def _parse_ssdp_response(data: bytes) -> dict:
    """解析 SSDP 响应/NOTIFY 数据"""
    headers = {}
    try:
        text = data.decode("utf-8", errors="replace")
        for line in text.split("\r\n")[1:]:
            if ":" in line:
                key, _, value = line.partition(":")
                headers[key.strip().lower()] = value.strip()
    except Exception:
        pass
    return headers


def _extract_usn_udn(usn: str) -> str:
    """从 USN 中提取 UDN"""
    if not usn:
        return ""
    if "::" in usn:
        return usn.split("::")[0]
    return usn


def _ssdp_msearch_on_interface(local_ip: str, msg: bytes, timeout: int) -> list:
    """在单个接口上发送 M-SEARCH 并收集响应"""
    results = []
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((local_ip, 0))
        sock.settimeout(timeout)
        sock.sendto(msg, (SSDP_MULTICAST_ADDR, SSDP_PORT))

        deadline = time.time() + timeout
        while time.time() < deadline:
            remain = max(0.1, deadline - time.time())
            sock.settimeout(remain)
            try:
                data, addr = sock.recvfrom(4096)
                headers = _parse_ssdp_response(data)
                if headers:
                    results.append(headers)
            except socket.timeout:
                break
            except OSError:
                break
    except Exception as e:
        print(f"[WARN] 接口 {local_ip} M-SEARCH 失败: {e}", file=sys.stderr)
    finally:
        try:
            sock.close()
        except Exception:
            pass
    return results


def _ssdp_discover_raw(service_target: str = "ssdp:all", timeout: int = 5) -> list:
    """
    原始 SSDP 多播搜索（纯 socket 实现）。
    在所有可用接口上并发发送 M-SEARCH，收集响应。
    """
    local_ips = _get_local_ipv4_addresses()
    if not local_ips:
        return []

    mx = min(timeout, 3)
    msg = SSDP_MSEARCH_TEMPLATE.format(mx=mx, st=service_target).encode("utf-8")

    all_headers = []
    threads = []
    lock = threading.Lock()

    def _search(ip):
        results = _ssdp_msearch_on_interface(ip, msg, timeout)
        with lock:
            all_headers.extend(results)

    for ip in local_ips:
        t = threading.Thread(target=_search, args=(ip,), daemon=True)
        t.start()
        threads.append(t)

    for t in threads:
        t.join(timeout=timeout + 2)

    # 去重并提取设备信息
    devices = {}
    for headers in all_headers:
        usn = headers.get("usn", "")
        location = headers.get("location", "")
        if not usn or not location:
            continue
        udn = _extract_usn_udn(usn)
        if not udn or udn in devices:
            continue
        devices[udn] = {
            "udn": udn,
            "location": location,
            "st": headers.get("st", "") or headers.get("nt", ""),
            "usn": usn,
        }

    # 获取每个设备的详细信息
    result = []
    for udn, info in devices.items():
        device = _parse_device_xml(info["location"])
        if device:
            entry = {
                "udn": device.udn or udn,
                "location": info["location"],
                "st": info.get("st", ""),
                "name": device.name,
                "device_type": device.device_type,
                "model_name": device.model_name,
                "manufacturer": device.manufacturer,
                "services": [s.service_type for s in device.services.values()],
                "device_role": _classify_device({
                    "device_type": device.device_type,
                    "st": info.get("st", ""),
                    "services": [s.service_type for s in device.services.values()],
                }),
            }
            result.append(entry)
        else:
            entry = {
                "udn": udn,
                "location": info["location"],
                "name": udn,
                "device_type": "",
                "st": info.get("st", ""),
                "services": [],
                "device_role": _classify_device(entry),
            }
            result.append(entry)

    return result


def _ssdp_discover(service_target: str = "ssdp:all", timeout: int = 5) -> list:
    """
    执行 SSDP 搜索，返回发现的设备信息列表。
    - 配置了 ssdp_helper_url 时，通过宿主机 relay 代理发现
    - 否则直接使用原始 socket M-SEARCH
    """
    helper_url = _get_helper_url()
    if helper_url:
        return _discover_via_helper(helper_url, timeout)
    return _ssdp_discover_raw(service_target, timeout)


# ============================================================
# Async 运行器（同步转异步桥接）
# ============================================================

def run_async(coro):
    """在同步代码中运行协程"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        return asyncio.ensure_future(coro)
    else:
        return asyncio.run(coro)


# ============================================================
# SOAP 调用（纯标准库实现）
# ============================================================

def _build_soap_envelope(service_type: str, action_name: str, **kwargs) -> str:
    """构建 SOAP 请求 XML"""
    params_xml = ""
    for key, value in kwargs.items():
        if isinstance(value, str):
            params_xml += f"<{key}>{value}</{key}>"
        else:
            params_xml += f"<{key}>{value}</{key}>"

    return (
        '<?xml version="1.0"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        '<s:Body>'
        f'<u:{action_name} xmlns:u="{service_type}">'
        f'{params_xml}'
        f'</u:{action_name}>'
        '</s:Body>'
        '</s:Envelope>'
    )


def _parse_soap_response(xml_text: str, action_name: str) -> dict:
    """解析 SOAP 响应 XML，提取输出参数"""
    result = {}
    try:
        root = ET.fromstring(xml_text)

        # 找 Body 下的 Response 元素
        ns = {"s": SOAP_ENV_NS}
        body = root.find(".//s:Body", ns)
        if body is None:
            body = root.find(".//Body")
            ns = {}

        if body is None:
            # 尝试在根下直接找 Response
            for child in root:
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if tag.endswith("Response"):
                    body = child
                    break

        if body is not None:
            response_tag = f"{action_name}Response"
            for child in body:
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if tag == response_tag or tag.endswith("Response"):
                    for param in child:
                        param_tag = param.tag.split("}")[-1] if "}" in param.tag else param.tag
                        result[param_tag] = param.text or ""
                    break
            if not result:
                for param in body:
                    param_tag = param.tag.split("}")[-1] if "}" in param.tag else param.tag
                    result[param_tag] = param.text or ""

        # 检查 SOAP Fault
        fault = root.find(".//s:Fault", ns) if ns else root.find(".//Fault")
        if fault is not None:
            fault_code = fault.findtext(".//faultcode", "", ns) if ns else fault.findtext(".//faultcode", "")
            fault_string = fault.findtext(".//faultstring", "", ns) if ns else fault.findtext(".//faultstring", "")
            if fault_string:
                raise RuntimeError(f"SOAP Fault: {fault_code} - {fault_string}")

    except ET.ParseError:
        pass

    return result


def _soap_call(service: SimpleService, action_name: str, **kwargs) -> dict:
    """
    执行 SOAP 调用（同步，纯标准库实现）。

    Args:
        service: SimpleService 对象
        action_name: 动作名称，如 "GetTransportInfo"
        **kwargs: 参数键值对，如 InstanceID=0

    Returns:
        dict: 响应中的输出参数
    """
    body = _build_soap_envelope(service.service_type, action_name, **kwargs)
    soap_action = f'"{service.service_type}#{action_name}"'

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPACTION": soap_action,
        "User-Agent": "dlna-utils/1.0",
    }

    req = urllib.request.Request(
        service.control_url,
        data=body.encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            xml_text = resp.read().decode("utf-8", errors="replace")
        return _parse_soap_response(xml_text, action_name)
    except urllib.error.HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        parsed = _parse_soap_response(error_body, action_name)
        if parsed:
            raise RuntimeError(f"SOAP HTTP {e.code}: {parsed}")
        raise RuntimeError(f"SOAP HTTP {e.code}: {e.reason}")
    except Exception:
        raise


# ============================================================
# 设备发现与解析
# ============================================================

def _build_simple_device_from_info(info: dict) -> SimpleDevice | None:
    """从发现的设备信息构建 SimpleDevice"""
    location = info.get("location", "")
    if not location:
        return None
    device = _parse_device_xml(location)
    if device:
        # 补充发现阶段的信息
        if not device.udn:
            device.udn = info.get("udn", "")
        if not device.device_type:
            device.device_type = info.get("device_type", "")
        return device
    return None


def _find_device_by_udn(udn: str, timeout: int = 5) -> SimpleDevice | None:
    """
    通过 UDN 查找并创建设备对象。
    - 有 helper_url: 通过 relay 查找 LOCATION，然后解析 device.xml
    - 无 helper_url: 直接 SSDP 搜索
    """
    helper_url = _get_helper_url()

    if helper_url:
        # Docker 模式：通过 relay 查找设备
        url = f"{helper_url.rstrip('/')}/find?udn={urllib.parse.quote(udn)}&timeout={min(timeout, 5)}"
        try:
            with urllib.request.urlopen(url, timeout=timeout + 5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("code") != 0:
                return None
            location = data.get("data", {}).get("location", "")
            if not location:
                return None
        except Exception:
            return None

        # 解析 device.xml 创建设备对象
        return _parse_device_xml(location)

    # 非 Docker 模式：原始 socket SSDP 搜索
    discovered = _ssdp_discover_raw("ssdp:all", timeout)
    for d in discovered:
        if udn.lower() in d.get("udn", "").lower():
            return _build_simple_device_from_info(d)
    return None


def _find_device_by_name(name: str, device_role: str = "", timeout: int = 5) -> SimpleDevice | None:
    """通过设备名称查找并创建设备对象"""
    devices = _ssdp_discover(timeout=timeout)
    for d in devices:
        if device_role and d.get("device_role") != device_role:
            continue
        if name and d.get("name") and name.lower() in d["name"].lower():
            udn = d.get("udn", "")
            if udn:
                return _find_device_by_udn(udn, timeout=2)
    return None


# ============================================================
# 公共 API
# ============================================================

def discover_devices(service_filter: str = "all", timeout: int = 5) -> list:
    """
    同步：发现局域网内的 DLNA 设备

    Args:
        service_filter: 'all' / 'dms' / 'dmr'
        timeout: 搜索超时（秒）

    Returns:
        设备信息列表
    """
    devices = _ssdp_discover(service_target="ssdp:all", timeout=timeout)

    if service_filter == "dms":
        devices = [d for d in devices if d.get("device_role") == "DMS"]
    elif service_filter == "dmr":
        devices = [d for d in devices if d.get("device_role") == "DMR"]

    devices.sort(key=lambda x: (0 if x.get("device_role") == "DMS" else 1,
                               x.get("name", "").lower()))
    return devices


def resolve_device(udn: str, default_udn_key: str, default_name_key: str,
                   device_role: str = "") -> SimpleDevice | None:
    """
    同步：解析目标设备（按 UDN → 预设 UDN → 预设名称的优先级）

    Args:
        udn: 用户传入的 UDN（可能为空）
        default_udn_key: config 中预设 UDN 的键名
        default_name_key: config 中预设名称的键名
        device_role: 'DMS' 或 'DMR'，用于按名称搜索时过滤

    Returns:
        SimpleDevice 对象或 None
    """
    cfg = get_config()

    # 优先级 1: 传入 UDN
    if udn:
        device = _find_device_by_udn(udn)
        if device:
            return device

    # 优先级 2: config 中预设 UDN
    preset_udn = cfg.get(default_udn_key, "").strip()
    if preset_udn:
        device = _find_device_by_udn(preset_udn)
        if device:
            return device

    # 优先级 3: config 中预设名称
    preset_name = cfg.get(default_name_key, "").strip()
    if preset_name:
        device = _find_device_by_name(preset_name, device_role=device_role)
        if device:
            return device

    return None


def get_service(device: SimpleDevice, service_type: str) -> SimpleService | None:
    """
    从设备中获取指定类型的服务

    Args:
        device: SimpleDevice 对象
        service_type: 如 'ContentDirectory', 'AVTransport', 'RenderingControl'

    Returns:
        SimpleService 对象或 None
    """
    for svc_name, svc in device.services.items():
        if service_type in svc_name or service_type in svc.service_type:
            return svc
    return None


def call_action_sync(service: SimpleService, action_name: str, **kwargs) -> dict:
    """
    同步调用 UPnP 服务动作（纯标准库 SOAP 实现）

    Args:
        service: SimpleService 对象
        action_name: 动作名称，如 'GetTransportInfo', 'Play', 'SetVolume'
        **kwargs: 参数键值对

    Returns:
        dict: 响应中的输出参数
    """
    return _soap_call(service, action_name, **kwargs)
