# SSDP 发现中继服务 (SSDP Relay)

[中文版本](#中文) | [English Version](#english)

---

## 中文

### 1. 为什么需要这个服务？

#### 1.1 背景

`dmc-to-mcp` 插件运行在 Docker 容器内，需要通过 SSDP 协议（`239.255.255.250:1900`）自动发现局域网内的 DLNA 设备（DMS/DMR）。

#### 1.2 问题

Docker 的端口映射（`-p 1900:1900/udp`）**只处理单播流量，不转发多播流量**。SSDP 使用多播通信，因此容器内无法收发 SSDP 包，导致设备自动发现失败。

```
                Docker 端口映射 (-p 1900:1900/udp)
                ┌─────────────────────────────────┐
  单播 ───────►  │  DNAT 匹配，转发给容器 ✅        │  单播能工作
  多播 ───────►  │  DNAT 不匹配，丢弃 ❌            │  SSDP 不工作
                └─────────────────────────────────┘
```

#### 1.3 设计决策

我们**拒绝**使用 `--network host` 方案，原因如下：

1. **无侵入设计**：容器不获取宿主机网络权限，保持隔离
2. **全局架构原则**：不能因为一个插件需要 SSDP 多播，就让所有容器放弃网络隔离
3. **最小权限**：每个容器只获得完成其功能所需的最少权限

**这个原则不会改变。** 如果未来有其他插件也需要多播能力，我们会用同样的中继模式解决，而不是放弃网络隔离。

#### 1.4 解决方案

在**宿主机**上运行一个轻量级的 SSDP 中继服务，充当"桥梁"：

```
[宿主机] ssdp_relay.py (常驻)
  ├── 监听 SSDP 多播 (NOTIFY) → 缓存设备信息
  ├── 按需发送 M-SEARCH → 主动发现设备
  └── 暴露 HTTP API (端口 1901) → 供容器查询
         │
         │ HTTP 单播 (走 Docker NAT, 不需要端口映射)
         ▼
[容器] dlna_utils.py
  ├── GET /scan → 获取设备列表
  ├── 用 LOCATION URL 直接 HTTP/SOAP 控制设备
  └── 完全不需要 async_upnp_client 的 SSDP 功能
```

### 2. 架构说明

```
┌─────────────────────────────────────────────────────────────┐
│  宿主机 (fnos)                                              │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  ssdp_relay.py (常驻守护进程)                        │   │
│  │                                                     │   │
│  │  线程1: SSDP NOTIFY 监听                            │   │
│  │  ┌─ socket bind(0.0.0.0:1900)                      │   │
│  │  └─ join multicast 239.255.255.250                 │   │
│  │     收到 NOTIFY → 缓存 {udn, location, name, ...}   │   │
│  │                                                     │   │
│  │  线程2: M-SEARCH 扫描                               │   │
│  │  ┌─ 绑定每张真实网卡的源 IP                         │   │
│  │  └─ 发送 M-SEARCH → 收集响应                       │   │
│  │                                                     │   │
│  │  线程3: HTTP API (端口 1901)                        │   │
│  │  ┌─ GET /health    → 健康检查                      │   │
│  │  ├─ GET /devices   → 缓存设备列表                  │   │
│  │  ├─ GET /scan      → 主动 M-SEARCH 扫描             │   │
│  │  └─ GET /find?udn= → 按 UDN 查找                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐   │
│  │  end0 网卡  │  │ Docker NAT   │  │  容器 (dlna)     │   │
│  │ 192.168.99.x│  │ 自动出站     │  │                 │   │
│  └──────┬──────┘  └──────┬───────┘  └────────┬────────┘   │
│         │                │                   │              │
│         │  SSDP 多播     │  HTTP 单播        │              │
│         │──────────────────────────────────► │              │
│         │                │  GET /scan        │              │
│         │                │                   │              │
└─────────┴────────────────┴───────────────────┴──────────┘
          │
          │ SSDP M-SEARCH 多播
          ▼
┌──────────────────────┐
│  DLNA 设备 (DMR/DMS) │
│  Yamaha RX1085 等    │
└──────────────────────┘
```

### 3. HTTP API

| 端点 | 方法 | 参数 | 说明 |
|------|------|------|------|
| `/health` | GET | — | 健康检查，返回运行状态和缓存设备数 |
| `/devices` | GET | `role` (可选: `dmr`/`dms`) | 返回缓存设备列表（瞬时响应） |
| `/scan` | GET | `timeout` (默认3), `role` (可选) | 主动 M-SEARCH 扫描（3-5秒） |
| `/find` | GET | `udn` (必填), `timeout` (可选) | 按 UDN 查找设备 |

响应格式（统一）：
```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "devices": [
      {
        "udn": "uuid:550e8400-e29b-41d4-a716-1051db851228",
        "location": "http://192.168.99.103:49152/device.xml",
        "name": "Apex Audio DMR",
        "device_type": "urn:schemas-upnp-org:device:MediaRenderer:1",
        "device_role": "DMR",
        "services": [
          "urn:schemas-upnp-org:service:AVTransport:1",
          "urn:schemas-upnp-org:service:RenderingControl:1",
          "urn:schemas-upnp-org:service:ConnectionManager:1"
        ],
        "last_seen": 1728288000
      }
    ],
    "total": 3
  }
}
```

### 4. 部署步骤

#### 4.1 宿主机上安装 Python 3

```bash
# 检查是否已安装
python3 --version

# 如果未安装，按系统安装
# Debian/Ubuntu:
sudo apt-get install -y python3
# CentOS/RHEL:
sudo yum install -y python3
# Alpine:
sudo apk add python3
```

#### 4.2 上传脚本到宿主机

将以下文件复制到宿主机的同一目录（如 `/opt/dlna-relay/`）：

- `ssdp_relay.py` — 中继服务主程序
- `ssdp_relay_manage.sh` — 运维管理脚本

```bash
# 赋予执行权限
chmod +x ssdp_relay_manage.sh
```

#### 4.3 启动服务（两种方式）

**方式 A：交互式管理脚本（推荐）**
```bash
./ssdp_relay_manage.sh
```
按提示选择语言 → 启动服务 → 选择网络接口

**方式 B：直接命令行**
```bash
# 启动（指定接口和端口）
python3 ssdp_relay.py --interface end0 --port 1901 --bind 0.0.0.0

# 后台运行
nohup python3 ssdp_relay.py --interface end0 --port 1901 &
```

#### 4.4 配置插件

插件会自动从 `manifest.serverUrl`（宿主机 IP）推导 relay 地址，**无需额外配置**。

如果需要自定义，可在 `plugin.json` 的 `config` 中设置：
```json
{
  "config": {
    "ssdp_helper_url": "http://192.168.99.105:1901"
  }
}
```

### 5. 运维脚本使用方法

#### 5.1 交互模式

```bash
./ssdp_relay_manage.sh
```

```
╔══════════════════════════════════════╗
║    SSDP 发现中继 - 运维管理工具      ║
╚══════════════════════════════════════╝

请选择语言 / Select Language:
1) 中文
2) English
输入选项 [1-2]: 1

请选择操作:
1) 启动服务 (Start)
2) 停止服务 (Stop)
3) 重启服务 (Restart)
4) 查看状态 (Status)
0) 退出 (Exit)
输入选项 [0-4]: 1
```

#### 5.2 命令行模式（适合脚本化）

```bash
# 启动
./ssdp_relay_manage.sh start

# 停止
./ssdp_relay_manage.sh stop

# 重启
./ssdp_relay_manage.sh restart

# 查看状态
./ssdp_relay_manage.sh status
```

#### 5.3 systemd 服务（可选）

创建 `/etc/systemd/system/ssdp-relay.service`：
```ini
[Unit]
Description=SSDP Discovery Relay Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/dlna-relay/ssdp_relay.py --interface end0 --port 1901
Restart=on-failure
WorkingDirectory=/opt/dlna-relay

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable ssdp-relay
sudo systemctl start ssdp-relay
```

### 6. 故障排查

| 问题 | 排查方法 |
|------|---------|
| 服务启动后无设备 | 检查日志 `tail -20 ssdp_relay.log`，确认是否绑定了正确的网卡接口 |
| 容器调 `/scan` 返回空 | 检查 relay 是否在运行：`curl http://127.0.0.1:1901/health` |
| 发现到设备但无法控制 | 设备可能已离线或 IP 变化，调 `/scan` 重新扫描 |
| 端口 1901 被占用 | 修改 `--port` 参数，同时更新插件配置中的端口 |
| 多播收不到 | 确认宿主机防火墙放行了 UDP 1900：`sudo iptables -L -n` |

### 7. 文件清单

| 文件 | 说明 |
|------|------|
| `ssdp_relay.py` | 中继服务主程序（零依赖，Python 标准库） |
| `ssdp_relay_manage.sh` | 运维管理脚本（交互式菜单 + 命令行模式） |
| `ssdp_relay.pid` | 运行时生成的 PID 文件 |
| `ssdp_relay.log` | 运行日志 |

---

## English

### 1. Why This Service Exists?

#### 1.1 Background

The `dmc-to-mcp` plugin runs inside a Docker container and needs to auto-discover DLNA devices (DMS/DMR) on the LAN via SSDP protocol (`239.255.255.250:1900`).

#### 1.2 The Problem

Docker port mapping (`-p 1900:1900/udp`) **only handles unicast traffic, not multicast**. SSDP uses multicast, so containers cannot send or receive SSDP packets — device auto-discovery fails.

```
                Docker Port Mapping (-p 1900:1900/udp)
                ┌─────────────────────────────────┐
  Unicast  ───►  │  DNAT matches, forwards ✅      │  Unicast works
  Multicast ─►  │  DNAT skips, dropped ❌         │  SSDP broken
                └─────────────────────────────────┘
```

#### 1.3 Design Decision

We **reject** the `--network host` approach because:

1. **Non-intrusive design**: containers must not gain host network privileges
2. **Global architecture principle**: one plugin's multicast need should not force all containers to give up network isolation
3. **Least privilege**: each container gets only the minimum permissions required for its function

**This principle will not change.** If future plugins also need multicast, we use the same relay pattern — not abandon network isolation.

#### 1.4 Solution

Run a lightweight SSDP relay on the **host** machine as a "bridge":

```
[Host] ssdp_relay.py (always running)
  ├── Listens for SSDP NOTIFY (multicast) → caches device info
  ├── Sends M-SEARCH on demand → proactive discovery
  └── Exposes HTTP API (port 1901) → container queries
         │
         │ HTTP unicast (via Docker NAT, no port mapping needed)
         ▼
[Container] dlna_utils.py
  ├── GET /scan → get device list
  ├── Use LOCATION URL for direct HTTP/SOAP control
  └── No async_upnp_client SSDP dependency needed
```

### 2. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Host Machine                                               │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  ssdp_relay.py (daemon)                             │   │
│  │                                                     │   │
│  │  Thread 1: SSDP NOTIFY Listener                     │   │
│  │  ┌─ socket bind(0.0.0.0:1900)                      │   │
│  │  └─ join multicast 239.255.255.250                 │   │
│  │     On NOTIFY → cache {udn, location, name, ...}   │   │
│  │                                                     │   │
│  │  Thread 2: M-SEARCH Scanner                          │   │
│  │  ┌─ Bind each real NIC's source IP                 │   │
│  │  └─ Send M-SEARCH → collect responses              │   │
│  │                                                     │   │
│  │  Thread 3: HTTP API (port 1901)                     │   │
│  │  ┌─ GET /health    → health check                  │   │
│  │  ├─ GET /devices   → cached devices                │   │
│  │  ├─ GET /scan      → proactive M-SEARCH            │   │
│  │  └─ GET /find?udn= → find by UDN                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐   │
│  │  end0 NIC   │  │ Docker NAT   │  │  Container      │   │
│  │ 192.168.99.x│  │ auto-outbound│  │  (dlna plugin)  │   │
│  └──────┬──────┘  └──────┬───────┘  └────────┬────────┘   │
│         │                │                   │              │
│         │ SSDP multicast │ HTTP unicast      │              │
│         │──────────────────────────────────► │              │
│         │                │  GET /scan        │              │
│         │                │                   │              │
└─────────┴────────────────┴───────────────────┴──────────┘
          │
          │ SSDP M-SEARCH multicast
          ▼
┌──────────────────────┐
│  DLNA Devices        │
│  (DMR/DMS)           │
└──────────────────────┘
```

### 3. HTTP API

| Endpoint | Method | Parameters | Description |
|----------|--------|-----------|-------------|
| `/health` | GET | — | Health check, returns status and cached device count |
| `/devices` | GET | `role` (optional: `dmr`/`dms`) | Returns cached devices (instant response) |
| `/scan` | GET | `timeout` (default 3), `role` (optional) | Proactive M-SEARCH scan (3-5s) |
| `/find` | GET | `udn` (required), `timeout` (optional) | Find device by UDN |

Response format (uniform):
```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "devices": [
      {
        "udn": "uuid:550e8400-e29b-41d4-a716-1051db851228",
        "location": "http://192.168.99.103:49152/device.xml",
        "name": "Apex Audio DMR",
        "device_type": "urn:schemas-upnp-org:device:MediaRenderer:1",
        "device_role": "DMR",
        "services": [
          "urn:schemas-upnp-org:service:AVTransport:1",
          "urn:schemas-upnp-org:service:RenderingControl:1",
          "urn:schemas-upnp-org:service:ConnectionManager:1"
        ],
        "last_seen": 1728288000
      }
    ],
    "total": 3
  }
}
```

### 4. Deployment

#### 4.1 Install Python 3 on Host

```bash
# Check if installed
python3 --version

# Install by distro
# Debian/Ubuntu:
sudo apt-get install -y python3
# CentOS/RHEL:
sudo yum install -y python3
# Alpine:
sudo apk add python3
```

#### 4.2 Copy Scripts to Host

Copy these files to the same directory on the host (e.g., `/opt/dlna-relay/`):

- `ssdp_relay.py` — relay service main program
- `ssdp_relay_manage.sh` — management script

```bash
# Make executable
chmod +x ssdp_relay_manage.sh
```

#### 4.3 Start Service (Two Ways)

**Option A: Interactive Manager (Recommended)**
```bash
./ssdp_relay_manage.sh
```
Select language → Start → Choose network interface

**Option B: Direct CLI**
```bash
# Start (with interface and port)
python3 ssdp_relay.py --interface end0 --port 1901 --bind 0.0.0.0

# Background
nohup python3 ssdp_relay.py --interface end0 --port 1901 &
```

#### 4.4 Configure Plugin

The plugin auto-derives the relay URL from `manifest.serverUrl` (host IP). **No extra config needed.**

To customize, set in `plugin.json` config:
```json
{
  "config": {
    "ssdp_helper_url": "http://192.168.99.105:1901"
  }
}
```

### 5. Management Script Usage

#### 5.1 Interactive Mode

```bash
./ssdp_relay_manage.sh
```

```
╔══════════════════════════════════════╗
║    SSDP Relay - Management Tool     ║
╚══════════════════════════════════════╝

Select Language:
1) 中文
2) English
Enter choice [1-2]: 2

Select action:
1) Start service
2) Stop service
3) Restart service
4) Check status
0) Exit
Enter choice [0-4]: 1
```

#### 5.2 CLI Mode (for scripting)

```bash
# Start
./ssdp_relay_manage.sh start

# Stop
./ssdp_relay_manage.sh stop

# Restart
./ssdp_relay_manage.sh restart

# Status
./ssdp_relay_manage.sh status
```

#### 5.3 systemd Service (Optional)

Create `/etc/systemd/system/ssdp-relay.service`:
```ini
[Unit]
Description=SSDP Discovery Relay Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/dlna-relay/ssdp_relay.py --interface end0 --port 1901
Restart=on-failure
WorkingDirectory=/opt/dlna-relay

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable ssdp-relay
sudo systemctl start ssdp-relay
```

### 6. Troubleshooting

| Issue | How to Check |
|-------|-------------|
| No devices after startup | Check logs: `tail -20 ssdp_relay.log`, confirm correct NIC bound |
| Container `/scan` returns empty | Check relay is running: `curl http://127.0.0.1:1901/health` |
| Device found but can't control | Device may be offline or IP changed, call `/scan` to refresh |
| Port 1901 conflict | Change `--port` param, update plugin config accordingly |
| Multicast not received | Verify firewall allows UDP 1900: `sudo iptables -L -n` |

### 7. File List

| File | Description |
|------|-------------|
| `ssdp_relay.py` | Relay service (zero dependencies, Python stdlib only) |
| `ssdp_relay_manage.sh` | Management script (interactive menu + CLI mode) |
| `ssdp_relay.pid` | Runtime PID file |
| `ssdp_relay.log` | Runtime logs |