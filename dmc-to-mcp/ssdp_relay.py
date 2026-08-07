#!/usr/bin/env python3
"""
ssdp_relay.py —— SSDP 发现中继服务（宿主机端）
=================================================
Docker 容器无法收发 SSDP 多播流量，本脚本运行在宿主机上，
充当"SSDP 发现代理"，为容器内的 DLNA 插件提供设备发现能力。

功能：
  1. 持续监听 SSDP NOTIFY 多播，缓存局域网内的 DLNA 设备
  2. 按需发送 M-SEARCH，主动发现设备
  3. 获取设备描述文档 (device.xml)，返回完整设备信息
  4. 通过 HTTP API 向容器提供查询接口

零第三方依赖，仅使用 Python 标准库。

用法:
    python3 ssdp_relay.py [--port 1901] [--interface end0] [--ssdp-timeout 3]

HTTP API:
    GET /health          健康检查
    GET /devices         返回缓存设备列表（瞬时）
    GET /scan?timeout=3  主动 M-SEARCH 扫描后返回
    GET /scan?timeout=3&role=dmr  扫描并过滤 DMR
    GET /find?udn=xxx    按 UDN 查找设备
"""

import argparse
import json
import socket
import struct
import sys
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# ============================================================
# 常量
# ============================================================

SSDP_MULTICAST_ADDR = "239.255.255.250"
SSDP_PORT = 1900
SSDP_MSEARCH_TEMPLATE = (
    "M-SEARCH * HTTP/1.1\r\n"
    "HOST: 239.255.255.250:1900\r\n"
    "MAN: \"ssdp:discover\"\r\n"
    "MX: {mx}\r\n"
    "ST: {st}\r\n"
    "\r\n"
)
DEVICE_CACHE_TTL = 300  # 缓存过期时间（秒），5 分钟未更新则移除


# ============================================================
# 工具函数
# ============================================================

def get_local_ipv4_addresses(interface=None):
    """获取本机可用的 IPv4 地址列表。指定 interface 时只返回该接口的 IP。"""
    ips = []

    if interface:
        # 指定接口名（Linux）：通过 socket.if_nameindex() 匹配
        try:
            for name, addr in socket.if_nameindex():
                if name == interface:
                    # 用 ioctl 获取接口 IP（Linux 专用）
                    try:
                        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        result = fcntl.ioctl(s.fileno(), 0x8915, struct.pack('256s', name.encode()[:15]))
                        ip = socket.inet_ntoa(result[20:24])
                        if ip and not ip.startswith("127."):
                            ips.append(ip)
                        s.close()
                    except Exception:
                        pass
        except Exception:
            pass

    if not ips:
        # 通用方法：UDP socket 探测出口 IP
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127."):
                ips.append(ip)
        except Exception:
            pass

        # 备用：hostname 解析
        try:
            hostname = socket.gethostname()
            for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
                ip = info[4][0]
                if ip and not ip.startswith("127.") and ip not in ips:
                    ips.append(ip)
        except Exception:
            pass

    return ips


def classify_device(device_type, st, services):
    """根据设备类型/ST/服务列表判断 DMS 或 DMR"""
    dt = device_type or ""
    st_str = st or ""
    svc_str = " ".join(services or [])
    if "MediaServer" in dt or "MediaServer" in st_str:
        return "DMS"
    if "MediaRenderer" in dt or "MediaRenderer" in st_str:
        return "DMR"
    if "ContentDirectory" in svc_str:
        return "DMS"
    if "AVTransport" in svc_str:
        return "DMR"
    return "UNKNOWN"


def parse_ssdp_response(data):
    """解析 SSDP 响应/NOTIFY 数据，返回 headers 字典"""
    headers = {}
    try:
        text = data.decode("utf-8", errors="replace")
        for line in text.split("\r\n")[1:]:  # 跳过状态行
            if ":" in line:
                key, _, value = line.partition(":")
                headers[key.strip().lower()] = value.strip()
    except Exception:
        pass
    return headers


def extract_usn_udn(usn):
    """从 USN 中提取 UDN。USN 格式: uuid:xxx::service_type"""
    if not usn:
        return ""
    if "::" in usn:
        return usn.split("::")[0]
    return usn


def fetch_device_description(location, timeout=5):
    """
    获取设备描述文档 (device.xml)，解析出设备名称、类型、服务列表。
    纯标准库实现（urllib + ElementTree）。
    """
    try:
        req = urllib.request.Request(location, headers={"User-Agent": "ssdp_relay/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            xml_data = resp.read()

        root = ET.fromstring(xml_data)
        ns = {"d": "urn:schemas-upnp-org:device-1-0"}

        device = root.find(".//d:device", ns)
        if device is None:
            # 尝试无命名空间
            device = root.find(".//device")
            ns = {}

        if device is None:
            return None

        def _findtext(tag):
            if ns:
                el = device.findtext(f"d:{tag}", "", ns)
            else:
                el = device.findtext(tag, "")
            return el or ""

        name = _findtext("friendlyName")
        device_type = _findtext("deviceType")
        model_name = _findtext("modelName")
        manufacturer = _findtext("manufacturer")
        udn = _findtext("UDN")

        # 服务列表
        services = []
        if ns:
            svc_list = device.findall(".//d:service", ns)
        else:
            svc_list = device.findall(".//service")
        for svc in svc_list:
            if ns:
                st = svc.findtext("d:serviceType", "", ns)
            else:
                st = svc.findtext("serviceType", "")
            if st:
                services.append(st)

        return {
            "name": name or udn,
            "device_type": device_type,
            "model_name": model_name,
            "manufacturer": manufacturer,
            "udn": udn,
            "services": services,
        }
    except Exception:
        return None


# ============================================================
# SSDP 中继核心
# ============================================================

class SSDPRelay:
    """SSDP 发现中继：监听 NOTIFY + 主动 M-SEARCH + 设备缓存"""

    def __init__(self, interface=None, ssdp_timeout=3):
        self._interface = interface
        self._ssdp_timeout = ssdp_timeout
        self._devices = {}  # udn -> device_info
        self._lock = threading.Lock()
        self._local_ips = get_local_ipv4_addresses(interface)
        self._listen_sock = None

    # --- 设备缓存管理 ---

    def _update_device(self, headers):
        """从 SSDP 响应头更新设备缓存"""
        usn = headers.get("usn", "")
        location = headers.get("location", "")
        st = headers.get("st", "") or headers.get("nt", "")

        if not usn or not location:
            return

        udn = extract_usn_udn(usn)
        if not udn:
            return

        with self._lock:
            existing = self._devices.get(udn, {})
            existing.update({
                "udn": udn,
                "location": location,
                "st": st,
                "usn": usn,
                "last_seen": time.time(),
            })
            # 如果还没有详细信息，异步获取
            if "name" not in existing:
                existing["device_role"] = classify_device(
                    existing.get("device_type", ""), st, existing.get("services", [])
                )
            self._devices[udn] = existing

        # 异步获取设备描述（不阻塞 SSDP 接收）
        if "name" not in self._devices.get(udn, {}):
            threading.Thread(
                target=self._fetch_description_async,
                args=(udn, location),
                daemon=True,
            ).start()

    def _fetch_description_async(self, udn, location):
        """异步获取设备描述并更新缓存"""
        desc = fetch_device_description(location)
        if not desc:
            return

        with self._lock:
            device = self._devices.get(udn, {})
            device.update({
                "name": desc["name"],
                "device_type": desc["device_type"],
                "model_name": desc["model_name"],
                "manufacturer": desc["manufacturer"],
                "services": desc["services"],
                "device_role": classify_device(
                    desc["device_type"],
                    device.get("st", ""),
                    desc["services"],
                ),
                "last_seen": time.time(),
            })
            self._devices[udn] = device

    def _cleanup_expired(self):
        """清理过期设备（超过 DEVICE_CACHE_TTL 未更新）"""
        now = time.time()
        with self._lock:
            expired = [
                udn for udn, info in self._devices.items()
                if now - info.get("last_seen", 0) > DEVICE_CACHE_TTL
            ]
            for udn in expired:
                del self._devices[udn]

    def get_devices(self, role=None):
        """获取缓存中的设备列表"""
        self._cleanup_expired()
        with self._lock:
            devices = list(self._devices.values())
        if role:
            devices = [d for d in devices if d.get("device_role") == role.upper()]
        # 排序：DMS 在前，同类按名称
        devices.sort(key=lambda x: (0 if x.get("device_role") == "DMS" else 1,
                                     x.get("name", "").lower()))
        return devices

    def find_device(self, udn, timeout=None):
        """按 UDN 查找设备，缓存未命中时触发扫描"""
        if timeout is None:
            timeout = self._ssdp_timeout

        # 先查缓存
        with self._lock:
            if udn in self._devices:
                return self._devices[udn]

        # 触发扫描
        self.send_msearch(timeout=timeout)

        with self._lock:
            return self._devices.get(udn)

    # --- SSDP 监听（NOTIFY）---

    def start_listener(self):
        """启动 SSDP 多播监听线程（接收 NOTIFY）"""
        if not self._local_ips:
            print("[WARN] 未找到本地 IPv4 地址，NOTIFY 监听不可用", file=sys.stderr)
            return

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except (AttributeError, OSError):
                pass  # Windows 没有 SO_REUSEPORT

            sock.bind(("0.0.0.0", SSDP_PORT))

            # 在每个接口上加入多播组
            for ip in self._local_ips:
                try:
                    mreq = struct.pack("=4s4s",
                                       socket.inet_aton(SSDP_MULTICAST_ADDR),
                                       socket.inet_aton(ip))
                    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                    print(f"[INFO] SSDP 监听已加入多播组 (接口 {ip})", file=sys.stderr)
                except OSError as e:
                    print(f"[WARN] 接口 {ip} 加入多播组失败: {e}", file=sys.stderr)

            sock.settimeout(1.0)  # 定期检查运行状态
            self._listen_sock = sock

            print(f"[INFO] SSDP NOTIFY 监听已启动 (端口 {SSDP_PORT})", file=sys.stderr)

            while True:
                try:
                    data, addr = sock.recvfrom(4096)
                    headers = parse_ssdp_response(data)
                    if headers:
                        self._update_device(headers)
                except socket.timeout:
                    continue
                except OSError:
                    break

        except OSError as e:
            print(f"[WARN] 端口 {SSDP_PORT} 绑定失败: {e}", file=sys.stderr)
            print("[INFO] NOTIFY 被动监听不可用，将仅使用主动 M-SEARCH", file=sys.stderr)

    # --- 主动 M-SEARCH ---

    def send_msearch(self, timeout=None, search_target="ssdp:all"):
        """在所有接口上发送 M-SEARCH 并收集响应"""
        if timeout is None:
            timeout = self._ssdp_timeout

        if not self._local_ips:
            print("[WARN] 无可用网络接口，无法发送 M-SEARCH", file=sys.stderr)
            return

        mx = min(timeout, 3)
        msg = SSDP_MSEARCH_TEMPLATE.format(mx=mx, st=search_target).encode("utf-8")

        # 在每个接口上发送（并发线程）
        threads = []
        for ip in self._local_ips:
            t = threading.Thread(
                target=self._msearch_on_interface,
                args=(ip, msg, timeout),
                daemon=True,
            )
            t.start()
            threads.append(t)

        # 等待所有扫描完成
        for t in threads:
            t.join(timeout=timeout + 2)

    def _msearch_on_interface(self, local_ip, msg, timeout):
        """在单个接口上发送 M-SEARCH 并接收响应"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((local_ip, 0))  # 绑定源 IP，随机端口
            sock.settimeout(timeout)

            # 发送 M-SEARCH
            sock.sendto(msg, (SSDP_MULTICAST_ADDR, SSDP_PORT))

            # 接收响应
            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    data, addr = sock.recvfrom(4096)
                    headers = parse_ssdp_response(data)
                    if headers:
                        self._update_device(headers)
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


# ============================================================
# HTTP API
# ============================================================

class RelayHTTPHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器，提供设备查询/扫描 API"""

    relay = None  # 由外部注入 SSDPRelay 实例

    def _send_json(self, code, msg, data=None):
        body = json.dumps({"code": code, "msg": msg, "data": data},
                          ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/health":
            self._send_json(0, "ok", {"status": "running", "devices": len(self.relay.get_devices())})
            return

        if parsed.path == "/devices":
            role = qs.get("role", [None])[0]
            devices = self.relay.get_devices(role=role)
            self._send_json(0, "ok", {"devices": devices, "total": len(devices)})
            return

        if parsed.path == "/scan":
            timeout = int(qs.get("timeout", ["3"])[0])
            role = qs.get("role", [None])[0]
            # 触发 M-SEARCH
            self.relay.send_msearch(timeout=timeout)
            devices = self.relay.get_devices(role=role)
            self._send_json(0, "ok", {"devices": devices, "total": len(devices)})
            return

        if parsed.path == "/find":
            udn = qs.get("udn", [""])[0]
            timeout = int(qs.get("timeout", ["3"])[0])
            if not udn:
                self._send_json(-1, "缺少 udn 参数")
                return
            device = self.relay.find_device(udn, timeout=timeout)
            if device:
                self._send_json(0, "ok", device)
            else:
                self._send_json(-1, f"未找到 UDN: {udn}")
            return

        self._send_json(-1, f"未知路径: {parsed.path}")

    def log_message(self, fmt, *args):
        # 简化日志输出
        print(f"[HTTP] {self.client_address[0]} - {fmt % args}", file=sys.stderr)


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="SSDP 发现中继服务（宿主机端）")
    parser.add_argument("--port", type=int, default=1901, help="HTTP API 端口（默认 1901）")
    parser.add_argument("--interface", type=str, default=None,
                        help="指定监听的网络接口名（如 end0），留空则自动检测")
    parser.add_argument("--ssdp-timeout", type=int, default=3,
                        help="M-SEARCH 扫描超时秒数（默认 3）")
    parser.add_argument("--bind", type=str, default="0.0.0.0",
                        help="HTTP API 绑定地址（默认 0.0.0.0）")
    args = parser.parse_args()

    print("=" * 50, file=sys.stderr)
    print(" SSDP 发现中继服务", file=sys.stderr)
    print(f" 网络接口: {args.interface or '自动检测'}", file=sys.stderr)
    print(f" 本机 IP: {get_local_ipv4_addresses(args.interface)}", file=sys.stderr)
    print(f" HTTP API: http://{args.bind}:{args.port}", file=sys.stderr)
    print(f" SSDP 超时: {args.ssdp_timeout}s", file=sys.stderr)
    print("=" * 50, file=sys.stderr)

    relay = SSDPRelay(interface=args.interface, ssdp_timeout=args.ssdp_timeout)

    # 启动 SSDP NOTIFY 监听线程
    listener_thread = threading.Thread(target=relay.start_listener, daemon=True)
    listener_thread.start()

    # 启动时做一次初始扫描
    print("[INFO] 启动时执行初始 M-SEARCH 扫描...", file=sys.stderr)
    relay.send_msearch(timeout=args.ssdp_timeout)
    devices = relay.get_devices()
    print(f"[INFO] 初始扫描完成，发现 {len(devices)} 台设备", file=sys.stderr)
    for d in devices:
        print(f"  - {d.get('name', '?')} ({d.get('device_role', '?')}) @ {d.get('location', '?')}",
              file=sys.stderr)

    # 启动 HTTP API
    RelayHTTPHandler.relay = relay
    httpd = HTTPServer((args.bind, args.port), RelayHTTPHandler)
    print(f"[INFO] HTTP API 已启动，监听 {args.bind}:{args.port}", file=sys.stderr)
    print("[INFO] 按 Ctrl+C 退出", file=sys.stderr)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] 正在退出...", file=sys.stderr)
        httpd.shutdown()


if __name__ == "__main__":
    # Linux 下需要 fcntl 来通过接口名获取 IP
    try:
        import fcntl
    except ImportError:
        fcntl = None
    main()
