<!--
  ┌──────────────────────────────────────────────────────┐
  │  apex-mcp-bridge 插件 —— 正式文档                     │
  │  FNOS SMB 文件管理 —— 原生 MCP 工具支持               │
  │  (MCP 协议 — 2026-07-28)                              │
  └──────────────────────────────────────────────────────┘
-->
<p align="center">
  <img src="https://img.shields.io/badge/plugin-FNOS-00b894?style=flat-square" alt="FNOS">
  <img src="https://img.shields.io/badge/api%20version-plugin.gis%2Fv1-6c5ce7?style=flat-square" alt="API Version">
  <img src="https://img.shields.io/badge/version-1.0.0-blue?style=flat-square" alt="Version">
  <img src="https://img.shields.io/badge/python-≥3.10-3776AB?logo=python&style=flat-square" alt="Python">
  <img src="https://img.shields.io/badge/MCP-2026.07.28-6c5ce7?style=flat-square" alt="MCP Protocol">
  <img src="https://img.shields.io/badge/protocol-SMB%202.0.2--3.1.1-orange?style=flat-square" alt="SMB">
</p>

# FNOS SMB 文件管理服务

[FNOS](https://club.fnnas.com/portal.php)（飞牛 NAS 系统）专用插件——通过 SMB / CIFS 协议管理 FNOS 设备上的共享文件，支持文件列表、创建目录、删除文件/空目录，覆盖 SMB 2.0.2 至 3.1.1 协议。**全面兼容 MCP（2026-07-28）**——所有方法均原生暴露为 MCP 工具，支持任意 MCP 客户端调用。

> **为什么是 FNOS 专用？** FNOS 不支持匿名用户（Guest）或 `Everyone` 角色的免密访问——所有 SMB 连接均强制要求身份验证。这意味着你无法像其他 NAS 那样空着用户名密码直接连上。解法是在 FNOS 上创建一个**公开账户**（如 `fnos`），赋予相应共享目录的读写权限，然后在插件配置中填入该账户凭证，以替代传统 NAS 的匿名 / Everyone 访问方式。
>
> 其他 NAS 系统（如 Synology、QNAP 等）的 SMB 文件管理插件将由后续独立插件提供。

本插件运行在 [apex-mcp-bridge](https://gitee.com/freen/apex-mcp-bridge) 之上 —— 一个完整的 MCP（Model Context Protocol，模型上下文协议）服务器，可自动发现插件并将其暴露为原生 MCP 工具。关于插件系统的完整工作原理、MCP 协议集成细节及如何开发新插件，请参阅 apex-mcp-bridge 项目文档。

## 目录

- [快速开始](#快速开始)
- [前置条件](#前置条件)
- [安装](#安装)
- [配置](#配置)
- [API 参考](#api-参考)
  - [smb.file.list — 列出文件](#smbfilelist--列出文件)
  - [smb.file.mkdir — 创建目录](#smbfilemkdir--创建目录)
  - [smb.file.delete — 删除文件/目录](#smbfiledelete--删除文件目录)
- [文件结构](#文件结构)
- [常见问题](#常见问题)

## 快速开始

1. 将本文件夹完整拷贝到 `apex-mcp-bridge` 的插件目录下：

   ```bash
   cp -r fnos-smb-file-manager/ /path/to/apex-mcp-bridge/service_plugins/
   ```

2. 编辑 `plugin.json`，填入你的 FNOS 设备信息：

   ```jsonc
   {
     "manifest": {
       "serverUrl": "192.168.1.100"   // ← 改成你的 FNOS 设备 IP
     },
     "config": {
       "smb_share": "music",          // ← 改成你的共享名称
       "smb_username": "fnos",        // ← FNOS 登录用户名
       "smb_password": "your_pass"    // ← FNOS 登录密码
     }
   }
   ```

3. bridge 自动检测新插件文件夹并动态加载，无需重启。

   > 无需手动安装依赖——系统启动时会自动扫描所有插件的 `requirements.txt` 并完成安装。

## 前置条件

| 条件 | 说明 |
|------|------|
| Python | ≥ 3.10 |
| 依赖库 | [smbprotocol](https://pypi.org/project/smbprotocol/) ≥ 1.15.0（SMB 2/3 协议纯 Python 实现） |
| 网络 | 运行 `apex-mcp-bridge` 的主机需能访问目标 SMB 服务器的 TCP 445 端口 |
| FNOS 设备 | 已部署并开启 FNOS（飞牛 NAS 系统），SMB 文件共享服务正常运行 |

## 安装

项目采用**共享虚拟环境 + 启动自动安装**方案，用户只需拷贝插件文件夹，依赖由 `apex-mcp-bridge` 自动管理。

### 生产环境

```bash
# 将插件文件夹拷贝到 service_plugins/
cp -r fnos-smb-file-manager/ /path/to/apex-mcp-bridge/service_plugins/

# bridge 自动检测新插件文件夹 —— 无需重启。
```

系统启动时 `entrypoint.sh` 自动完成：
- 检测 `.plugins-venv`，不存在则创建共享虚拟环境
- 扫描所有插件目录的 `requirements.txt`，执行 `pip install`
- 将虚拟环境注入 `PATH`，`plugin.json` 中的 `interpreter: "python3"` 会自动指向该环境

### 本地开发

```bash
# 创建共享虚拟环境（一次性操作）
python3 -m venv .plugins-venv

# 安装本插件依赖
.plugins-venv/bin/pip install -r service_plugins/fnos-smb-file-manager/requirements.txt

# 注入 PATH 后启动
export PATH="$PWD/.plugins-venv/bin:$PATH"
cargo run
```

## 配置

所有配置集中在 `plugin.json`，修改后重新调用方法即生效（每次调用启动新进程，无缓存残留）。

### 配置项说明

| 字段 | 层级 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|------|--------|------|
| `serverUrl` | `manifest` | string | **是** | — | FNOS 设备 IP 地址（不含协议前缀），如 `192.168.1.100` |
| `smb_port` | `config` | int | 否 | `445` | SMB 服务端口 |
| `smb_share` | `config` | string | **是** | — | 共享名称，如 `shared`、`music` |
| `smb_base_path` | `config` | string | 否 | `""` | 共享下的子目录路径，留空表示根目录 |
| `smb_username` | `config` | string | **是** | — | FNOS 公开账户用户名（FNOS 不支持匿名访问，必须填写） |
| `smb_password` | `config` | string | **是** | — | FNOS 公开账户密码 |
| `smb_domain` | `config` | string | 否 | `""` | 域（加入域的服务器需填写，格式 `DOMAIN\username`） |

### 完整配置示例

```json
{
  "manifest": {
    "serverUrl": "192.168.99.105"
  },
  "config": {
    "smb_port": 445,
    "smb_share": "documents",
    "smb_base_path": "project/files",
    "smb_username": "fnos",
    "smb_password": "",
    "smb_domain": "WORKGROUP"
  }
}
```

### 身份认证

> FNOS **不支持匿名访问**——`smb_username` 和 `smb_password` 均为必填项。

**操作步骤：**

1. 在 FNOS 管理后台创建一个专用的公开账户（如 `fnos`），设置密码
2. 为该账户授予目标共享目录的读写权限
3. 在 `plugin.json` 中填入该账户的凭证：

```json
{
  "config": {
    "smb_username": "fnos",
    "smb_password": "your_public_account_password"
  }
}
```

该公开账户本质上替代了其他 NAS 系统中的 `Everyone` / `Guest` 角色，实现可受控的共享文件访问。

## API 参考

所有方法通过 MCP 的 `local_service_call` 调用。每个方法独立进程运行，通过 stdin 接收 JSON 参数，stdout 返回统一格式响应：

```json
{
  "code": 0,
  "msg": "ok",
  "data": { ... }
}
```

- `code` = `0` 表示成功；`-1` 表示失败，`msg` 中携带错误描述
- `data` 内容因方法不同而不同，详见各方法说明

> **关于 `risk_level`**：每个方法的 `risk_level` 为插件预设的默认值，用户可在 `apex-mcp-bridge` 管理界面中按需修改：
> - 不需要的方法可设为 `disable` 直接关闭；
> - 需要人工审批的可升级为 `auth`（HITL）；
> - 风险操作可降级为 `normal` 以简化流程。
>
> 下图标注的 `风险等级` 均为插件出厂默认值。

---

### smb.file.list — 列出文件

列出 SMB 共享指定目录下的所有文件和子目录。

| 属性 | 值 |
|------|-----|
| 风险等级 | `normal` |
| 超时时间 | 30s |
| 调用模式 | `sync` |

**参数**

```json
{
  "path": "subdir1/subdir2"
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `path` | string | 否 | 相对于 `smb_base_path` 的子目录路径，留空则列出根目录 |

**返回**

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "path": "subdir1/subdir2",
    "smb_connection": {
      "server": "192.168.99.105",
      "port": 445,
      "share": "music",
      "base_path": "",
      "username": "fnos"
    },
    "items": [
      {
        "name": "song.mp3",
        "type": "file",
        "size": 4096000,
        "created": "2026-01-15 10:30:00",
        "modified": "2026-07-20 14:22:00",
        "is_hidden": false,
        "smb_url": "smb://fnos:***@192.168.99.105/music/song.mp3"
      },
      {
        "name": "playlists",
        "type": "directory",
        "size": 0,
        "created": "2026-01-10 08:00:00",
        "modified": "2026-06-01 09:00:00",
        "is_hidden": false,
        "smb_url": "smb://fnos:***@192.168.99.105/music/playlists"
      }
    ],
    "total": 2
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `path` | string | 实际查询的路径 |
| `smb_connection` | object | 当前 SMB 连接信息（密码已脱敏） |
| `items` | array | 文件/目录列表，目录在前、文件在后，同类按名称字母排序 |
| `items[].name` | string | 文件/目录名 |
| `items[].type` | string | `"file"` 或 `"directory"` |
| `items[].size` | int | 文件大小（字节），目录固定为 0 |
| `items[].created` | string | 创建时间 |
| `items[].modified` | string | 最后修改时间 |
| `items[].is_hidden` | bool | 是否隐藏文件 |
| `items[].smb_url` | string | 可直接用于 SMB 客户端访问的 URL（含认证信息） |
| `total` | int | 条目总数 |

---

### smb.file.mkdir — 创建目录

在 SMB 共享目录下创建新目录，支持递归创建多级目录。

| 属性 | 值 |
|------|-----|
| 风险等级 | `normal` |
| 超时时间 | 30s |
| 调用模式 | `sync` |

**参数**

```json
{
  "path": "new_folder/sub_folder"
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `path` | string | **是** | 相对于 `smb_base_path` 的目录路径，如 `a/b/c` |

**返回**

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "created": "new_folder/sub_folder"
  }
}
```

> 如果中间目录已存在，自动跳过继续创建下一级，不会报错。

---

### smb.file.delete — 删除文件/目录

删除 SMB 共享目录下的指定文件或空目录。

| 属性 | 值 |
|------|-----|
| 风险等级 | `risk` |
| 超时时间 | 30s |
| 调用模式 | `sync` |

> 出厂默认风险等级为 `risk`，执行时会在审计日志中醒目标记。用户可在管理界面将其改为 `normal`、`auth` 或 `disable`。

**参数**

```json
{
  "path": "file_or_directory_to_delete"
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `path` | string | **是** | 相对于 `smb_base_path` 的文件或目录路径 |

**返回**

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "deleted": "old_file.txt",
    "type": "file"
  }
}
```

**限制**

- 只能删除**空目录**。如果目录非空，返回错误：`目录非空，只能删除空目录`

## 文件结构

```
fnos-smb-file-manager/
├── plugin.json          # 插件清单（manifest + 方法定义 + 配置默认值）
├── requirements.txt     # Python 依赖声明
├── smb_utils.py         # 公共模块（连接管理 / 路径处理 / 目录操作 / 统一输出）
├── list_files.py        # smb.file.list 处理器
├── mkdir.py             # smb.file.mkdir 处理器
├── delete.py            # smb.file.delete 处理器
├── README.md            # English documentation
└── README_ZH.md         # 本文件（中文）
```

## 常见问题

<details>
<summary><b>Q: 连接时报 "无法连接到 SMB 服务器"？</b></summary>

1. 确认 `manifest.serverUrl` 填的是 SMB 服务器的正确 IP
2. 确认 `apex-mcp-bridge` 所在主机能 ping 通该 IP
3. 确认目标服务器 TCP 445 端口未被防火墙拦截：`telnet <server_ip> 445`
</details>

<details>
<summary><b>Q: 为什么必须填写用户名和密码？不能用匿名访问吗？</b></summary>

FNOS 不支持匿名用户（Guest）或 `Everyone` 角色的免密访问——这是 FNOS 的安全设计决策。所有 SMB 连接都必须经过身份验证。请先在 FNOS 管理后台创建一个公开账户（如 `fnos`），授予共享目录的读写权限，然后在插件配置中填写该账户的用户名和密码。
</details>

<details>
<summary><b>Q: 修改 plugin.json 后需要重启吗？</b></summary>

不需要。每次调用方法都会启动全新的 Python 进程，自动读取最新的 `plugin.json` 配置。
</details>

<details>
<summary><b>Q: 如何添加新的方法？</b></summary>

1. 编写新的 `.py` handler 文件（参考 `smb_utils.py` 的公共工具）
2. 在 `plugin.json` 的 `methods` 数组中新增一条方法定义，指定 `handler` 指向新脚本
3. bridge 在下次检测周期自动加载新方法
</details>

## 相关项目

- [apex-esp32-s3-v6](https://gitee.com/freen/apex-esp32-s3-v6) — 底层硬件框架 (ESP32-S3)
- [apex-esp32-c3-v6](https://gitee.com/freen/apex-esp32-c3-v6) — 底层硬件框架 (ESP32-C3)
- [service-plugins](https://gitee.com/freen/service-plugins) — 插件框架
- [apex-mcp-bridge](https://gitee.com/freen/apex-mcp-bridge) — 核心 MCP 服务器框架
