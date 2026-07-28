<!--
  ┌──────────────────────────────────────────────────────────────────────┐
  │  apex-mcp-bridge Plugin README Template (English)                    │
  │  All plugins (data reports, network printer, data service, etc.)     │
  │  follow this structure.                                              │
  └──────────────────────────────────────────────────────────────────────┘
-->
<p align="center">
  <img src="https://img.shields.io/badge/plugin-FNOS-00b894?style=flat-square" alt="FNOS">
  <img src="https://img.shields.io/badge/api%20version-plugin.gis%2Fv1-6c5ce7?style=flat-square" alt="API Version">
  <img src="https://img.shields.io/badge/version-1.0.0-blue?style=flat-square" alt="Version">
  <img src="https://img.shields.io/badge/python-≥3.10-3776AB?logo=python&style=flat-square" alt="Python">
  <img src="https://img.shields.io/badge/protocol-SMB%202.0.2--3.1.1-orange?style=flat-square" alt="SMB">
</p>

# FNOS SMB File Manager

A dedicated plugin for [FNOS](https://club.fnnas.com/portal.php) (Feiniu NAS System) — manage shared files on FNOS devices via the SMB / CIFS protocol. Supports file listing, directory creation, and file / empty directory deletion, covering SMB 2.0.2 through 3.1.1.

> **Why FNOS-specific?** FNOS does not support anonymous (Guest) or `Everyone` role access without credentials — all SMB connections require authentication. This means you cannot simply leave username and password blank to connect, unlike many other NAS systems. The solution is to create a **public account** on FNOS (e.g., `fnos`), grant it read / write permissions on the target share, then configure the plugin with that account's credentials. This public account effectively replaces the traditional `Everyone` / `Guest` role found on other NAS platforms.
>
> SMB file management plugins for other NAS systems (e.g., Synology, QNAP) will be provided as separate plugins in the future.

This plugin runs on top of [apex-mcp-bridge](https://github.com/apex-freen/apex-mcp-bridge). For the complete plugin system architecture, MCP protocol integration, and how to develop new plugins, please refer to the apex-mcp-bridge project documentation.

## Table of Contents

- [Quick Start](#quick-start)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [API Reference](#api-reference)
  - [smb.file.list — List Files](#smbfilelist--list-files)
  - [smb.file.mkdir — Create Directory](#smbfilemkdir--create-directory)
  - [smb.file.delete — Delete File / Directory](#smbfiledelete--delete-file--directory)
- [File Structure](#file-structure)
- [FAQ](#faq)

## Quick Start

1. Copy this folder into `apex-mcp-bridge`'s plugin directory:

   ```bash
   cp -r fnos-smb-file-manager/ /path/to/apex-mcp-bridge/service_plugins/
   ```

2. Edit `plugin.json` with your FNOS device information:

   ```jsonc
   {
     "manifest": {
       "serverUrl": "192.168.1.100"   // ← your FNOS device IP
     },
     "config": {
       "smb_share": "music",          // ← your share name
       "smb_username": "fnos",        // ← FNOS public account username
       "smb_password": "your_pass"    // ← FNOS public account password
     }
   }
   ```

3. The bridge auto-detects the new plugin folder and dynamically loads it — no restart needed.

   > No manual dependency installation needed — the system scans all plugins' `requirements.txt` and installs everything on startup.

## Prerequisites

| Requirement | Description |
|-------------|-------------|
| Python | ≥ 3.10 |
| Dependencies | [smbprotocol](https://pypi.org/project/smbprotocol/) ≥ 1.15.0 (pure-Python SMB 2/3 implementation) |
| Network | The host running `apex-mcp-bridge` must be able to reach the FNOS device on TCP port 445 |
| FNOS Device | FNOS (Feiniu NAS System) deployed with SMB file sharing enabled |
| Public Account | A dedicated FNOS account with read / write permissions on the target share (FNOS does not support anonymous access) |

## Installation

This project uses a **shared virtual environment + auto-install on startup** approach. Users only need to copy the plugin folder — dependencies are managed automatically by `apex-mcp-bridge`.

### Production

```bash
# Copy the plugin folder into service_plugins/
cp -r fnos-smb-file-manager/ /path/to/apex-mcp-bridge/service_plugins/

# The bridge auto-detects new plugin folders — no restart needed.
```

On startup, `entrypoint.sh` handles:
- Checking for `.plugins-venv` (creates it if absent)
- Scanning all plugin `requirements.txt` files and running `pip install`
- Injecting the virtual environment into `PATH` so `"python3"` in `plugin.json` automatically resolves to the venv

### Local Development

```bash
# Create shared venv (one-time)
python3 -m venv .plugins-venv

# Install this plugin's dependencies
.plugins-venv/bin/pip install -r service_plugins/fnos-smb-file-manager/requirements.txt

# Inject PATH and start
export PATH="$PWD/.plugins-venv/bin:$PATH"
cargo run
```

## Configuration

All configuration lives in `plugin.json`. Changes take effect on the next method call (each invocation starts a fresh process — no stale cache).

### Configuration Reference

| Field | Level | Type | Required | Default | Description |
|-------|-------|------|----------|---------|-------------|
| `serverUrl` | `manifest` | string | **Yes** | — | FNOS device IP address (no protocol prefix), e.g., `192.168.1.100` |
| `smb_port` | `config` | int | No | `445` | SMB service port |
| `smb_share` | `config` | string | **Yes** | — | Share name, e.g., `shared`, `music` |
| `smb_base_path` | `config` | string | No | `""` | Subdirectory path within the share; leave empty for root |
| `smb_username` | `config` | string | **Yes** | — | FNOS public account username (FNOS does **not** support anonymous access) |
| `smb_password` | `config` | string | **Yes** | — | FNOS public account password |
| `smb_domain` | `config` | string | No | `""` | Domain (required for domain-joined servers, format: `DOMAIN\username`) |

### Full Configuration Example

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

### Authentication

> FNOS **does not support anonymous access** — both `smb_username` and `smb_password` are required.

**Setup steps:**

1. Create a dedicated public account in the FNOS admin console (e.g., `fnos`) and set a password
2. Grant the account read / write permissions on the target share
3. Fill in the account credentials in `plugin.json`:

```json
{
  "config": {
    "smb_username": "fnos",
    "smb_password": "your_public_account_password"
  }
}
```

This public account effectively replaces the `Everyone` / `Guest` role found in other NAS systems, enabling controlled shared file access.

## API Reference

All methods are invoked via MCP's `local_service_call`. Each method runs in an independent process, receiving JSON parameters via stdin and returning a unified JSON response on stdout:

```json
{
  "code": 0,
  "msg": "ok",
  "data": { ... }
}
```

- `code` = `0` indicates success; `-1` indicates failure, with details in `msg`
- `data` contents vary by method — see each method's documentation below

> **About `risk_level`**: Each method's `risk_level` is the plugin's factory default. Users can reconfigure it in the `apex-mcp-bridge` admin panel:
> - Set to `disable` to turn off unused methods;
> - Elevate to `auth` (HITL) to require human approval before execution;
> - Downgrade `risk` to `normal` to skip audit flagging.
>
> The risk levels shown below are the factory defaults.

---

### smb.file.list — List Files

Lists all files and subdirectories in the specified directory on the SMB share.

| Property | Value |
|----------|-------|
| Risk Level | `normal` |
| Timeout | 30s |
| Mode | `sync` |

**Parameters**

```json
{
  "path": "subdir1/subdir2"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | No | Subdirectory path relative to `smb_base_path`; leave empty to list the root |

**Response**

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

| Field | Type | Description |
|-------|------|-------------|
| `path` | string | The queried directory path |
| `smb_connection` | object | Current SMB connection info (password redacted) |
| `items` | array | File / directory list; directories first, files second, each group sorted alphabetically |
| `items[].name` | string | File or directory name |
| `items[].type` | string | `"file"` or `"directory"` |
| `items[].size` | int | File size in bytes (always 0 for directories) |
| `items[].created` | string | Creation time |
| `items[].modified` | string | Last modified time |
| `items[].is_hidden` | bool | Whether the item is hidden |
| `items[].smb_url` | string | SMB URL with credentials, ready for use in SMB clients |
| `total` | int | Total entry count |

---

### smb.file.mkdir — Create Directory

Creates a new directory on the SMB share. Supports recursive creation of nested directories.

| Property | Value |
|----------|-------|
| Risk Level | `normal` |
| Timeout | 30s |
| Mode | `sync` |

**Parameters**

```json
{
  "path": "new_folder/sub_folder"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | **Yes** | Directory path relative to `smb_base_path`, e.g., `a/b/c` |

**Response**

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "created": "new_folder/sub_folder"
  }
}
```

> If intermediate directories already exist, they are silently skipped — only missing levels are created.

---

### smb.file.delete — Delete File / Directory

Deletes a file or empty directory on the SMB share.

| Property | Value |
|----------|-------|
| Risk Level | `risk` |
| Timeout | 30s |
| Mode | `sync` |

> Factory default risk level is `risk` — the call is flagged in the audit log but executes directly. Users can change this to `normal`, `auth`, or `disable` in the admin panel.

**Parameters**

```json
{
  "path": "file_or_directory_to_delete"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | **Yes** | File or directory path relative to `smb_base_path` |

**Response**

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

**Limitations**

- Only **empty directories** can be deleted. Non-empty directories return: `Directory not empty — only empty directories can be deleted`

## File Structure

```
fnos-smb-file-manager/
├── plugin.json          # Plugin manifest (metadata + method definitions + default config)
├── requirements.txt     # Python dependency declaration
├── smb_utils.py         # Shared module (connection / path / directory ops / unified output)
├── list_files.py        # smb.file.list handler
├── mkdir.py             # smb.file.mkdir handler
├── delete.py            # smb.file.delete handler
├── README.md            # Documentation (English)
└── README_ZH.md         # 中文文档 (Chinese)
```

## FAQ

<details>
<summary><b>Q: Connection fails with "Unable to connect to SMB server"?</b></summary>

1. Verify `manifest.serverUrl` contains the correct IP of your FNOS device
2. Ensure the host running `apex-mcp-bridge` can ping the device
3. Confirm TCP port 445 is not blocked by a firewall: `telnet <server_ip> 445`
</details>

<details>
<summary><b>Q: Why must I provide a username and password? Can't I use anonymous access?</b></summary>

FNOS does not support anonymous (Guest) or `Everyone` role access without credentials — this is a deliberate security design choice in FNOS. All SMB connections must be authenticated. Please create a public account (e.g., `fnos`) in the FNOS admin console, grant it read / write permissions on the target share, then configure the plugin with that account's credentials.
</details>

<details>
<summary><b>Q: Do I need to restart after modifying plugin.json?</b></summary>

No. Each method invocation starts a fresh Python process that reads the latest `plugin.json` configuration automatically.
</details>

<details>
<summary><b>Q: How do I add a new method?</b></summary>

1. Write a new `.py` handler script (refer to `smb_utils.py` for shared utilities)
2. Add a new method entry in `plugin.json`'s `methods` array, pointing `handler` to the new script
3. The bridge dynamically loads the new method on next discovery cycle
</details>
