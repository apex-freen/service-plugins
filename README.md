<!--
  ┌──────────────────────────────────────────────────────┐
  │  apex-mcp-bridge Service Plugins                     │
  │  Production documentation — fully expanded MCP       │
  │  protocol support (2026-07-28).                      │
  └──────────────────────────────────────────────────────┘
-->
<p align="center">
  <img src="https://img.shields.io/badge/host-apex--mcp--bridge-6c5ce7?style=flat-square" alt="Host">
  <img src="https://img.shields.io/badge/api%20version-plugin.gis%2Fv1-6c5ce7?style=flat-square" alt="API Version">
  <img src="https://img.shields.io/badge/python-≥3.10-3776AB?logo=python&style=flat-square" alt="Python">
  <img src="https://img.shields.io/badge/MCP-2026.07.28-6c5ce7?style=flat-square" alt="MCP Protocol">
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License">
</p>

# apex-mcp-bridge Service Plugins

The official plugin ecosystem for [apex-mcp-bridge](https://github.com/apex-freen/apex-mcp-bridge). Each plugin extends the bridge with a specific service capability — file management, data reporting, network printing, and more. **Now fully expanded with complete [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) support (2026-07-28)** — all plugins are natively exposed as MCP tools, enabling seamless AI agent integration.

> **Philosophy**: copy a plugin folder into `service_plugins/`, and the bridge dynamically detects and loads it — no restart, no wiring, no registration step.
>
> **The real power**: You don't even need to write a single line of code. This repository provides a complete, standardized plugin framework — all method input schemas, configuration templates, stdin/stdout communication protocol, and unified response format are pre-built. Simply hand these templates as constraints to an AI agent, describe the service you want in natural language (a printer plugin? a data report?), and the agent generates complete, ready-to-run plugin code within the framework. How the script reads parameters, how it returns results, how it handles errors — it's all wired up in the template already. Outstanding community contributions will be featured in the official plugin library.

> ⚠️ **Security notice**: Plugins execute arbitrary Python code on your host. Only install plugins from the official repository or sources you fully trust. If you obtained a plugin from an unofficial channel and you don't understand its code, **do not use it** — it may contain malicious logic that compromises your system or data.

> **Related projects:**
> - [apex-esp32-s3-v6](https://github.com/apex-freen/apex-esp32-s3-v6) — Hardware framework (ESP32-S3)
> - [apex-esp32-c3-v6](https://github.com/apex-freen/apex-esp32-c3-v6) — Hardware framework (ESP32-C3)
> - [service-plugins](https://github.com/apex-freen/service-plugins) — Plugin framework (this repository)
> - [apex-mcp-bridge](https://github.com/apex-freen/apex-mcp-bridge) — Core project framework

## Table of Contents

- [Available Plugins](#available-plugins)
- [Architecture](#architecture)
- [Quick Start: Using a Plugin](#quick-start-using-a-plugin)
- [Plugin Development Guide](#plugin-development-guide)
  - [Directory Structure](#directory-structure)
  - [plugin.json Specification](#pluginjson-specification)
  - [Communication Protocol](#communication-protocol)
  - [Method Handler Template](#method-handler-template)
  - [Response Format](#response-format)
  - [Error Handling](#error-handling)
  - [Shared Utilities](#shared-utilities)
- [FAQ](#faq)

## Available Plugins

| Plugin | Service Type | Description |
|--------|-------------|-------------|
| [fnos-smb-file-manager](./fnos-smb-file-manager/) | `file-manager` | FNOS SMB file management — list, create directories, delete files on FNOS devices via MCP tools |

> The plugin ecosystem is fully expanded. All plugins are natively exposed as MCP tools — just install and invoke via any MCP-compatible client. More plugins are under active development.

## Architecture

```
┌──────────────────────────────┐
│       apex-mcp-bridge         │  ← Rust host, Docker on FNOS
│  (plugin auto-discovery)      │
├──────────────────────────────┤
│       service_plugins/        │  ← this repository
│  ┌──────────────────────────┐ │
│  │  fnos-smb-file-manager/  │ │  ← self-contained plugin
│  │    plugin.json            │ │     • manifest
│  │    requirements.txt       │ │     • method definitions
│  │    *.py (handlers)        │ │     • runtime config
│  └──────────────────────────┘ │     • handler scripts
│  ┌──────────────────────────┐ │
│  │  future-plugins/         │ │
│  └──────────────────────────┘ │
└──────────────────────────────┘
```

**Key design principles:**

1. **Self-contained** — each plugin is a single folder. Copy it in, done.
2. **Declarative manifest** — `plugin.json` is the single source of truth: what the plugin is, what methods it exposes, what parameters they take, and how to run them.
3. **stdin/stdout protocol** — the bridge invokes handler scripts and communicates via standard I/O. No shared memory, no RPC framework, no import coupling.
4. **Process isolation** — each method invocation spawns a fresh Python process. A crash in one handler never affects the bridge or other plugins.
5. **Self-managed config** — plugin-specific configuration (server address, credentials, etc.) lives inside the plugin's own `plugin.json`. The handler reads it directly — the bridge never needs to know about it.

### How an MCP Tool Call Works

```
MCP Client → bridge (MCP server) → discovers method in plugin.json
                                  → spawns: python3 <handler.py> <method_name>
                                  → writes params JSON to stdin
                                  → reads response JSON from stdout
                                  → returns MCP tool result to Client
```

## Quick Start: Using a Plugin

1. Download a plugin folder and copy it into the bridge's plugin directory:

   ```bash
   cp -r fnos-smb-file-manager/ /path/to/apex-mcp-bridge/service_plugins/
   ```

   The bridge auto-detects and dynamically loads it — no restart needed.

   > Dependency installation is automatic — the bridge scans all `requirements.txt` on startup.

2. **Configure in the admin panel** — plugins ship with factory defaults. Open `apex-mcp-bridge`'s plugin management page to adjust:

   | You must configure | Why |
   |---|---|
   | **Server address** (`serverUrl`) | Tells the plugin which server hosts the actual service. Every plugin targets a specific server — set its IP or hostname. |
   | **Risk level** (`risk_level`) | Each method has a factory-default risk level, but your environment may demand tighter control. Adjust any method to `normal`, `risk`, `auth`, or `disable` as needed. |

   Other settings (port, share name, credentials, etc.) are plugin-specific — see the plugin's own README for details.

3. Done. The plugin is ready. Test a method call via MCP to verify connectivity.

## Plugin Development Guide

### Directory Structure

Every plugin follows this layout:

```
<plugin-name>/
├── plugin.json          # Manifest — the single source of truth
├── requirements.txt     # Python dependencies (pip install format)
├── <shared>.py          # Shared utilities (optional)
├── <handler_a>.py       # Method handler scripts
├── <handler_b>.py
├── README.md            # English documentation
└── README_ZH.md         # Chinese documentation (中文文档)
```

- The folder name is the plugin's identity (e.g., `fnos-smb-file-manager`).
- Every `.py` handler corresponds to one method in `plugin.json`.

### plugin.json Specification

The manifest is organized into five top-level sections:

| Section | Purpose |
|---------|---------|
| `manifest` | Plugin identity: name, version, target server address |
| `info` | Human-readable metadata: title, description, tags |
| `runtime` | Execution environment: interpreter, working directory |
| `methods` | Exposed MCP methods: name, parameters, handler, risk level |
| `config` | Plugin-private configuration (server credentials, etc.) |

#### Full Schema

```jsonc
{
  // ── Plugin Identity ──
  "manifest": {
    "name": "string",            // unique plugin ID, kebab-case
    "apiVersion": "plugin.gis/v1", // protocol version
    "kind": "Plugin",            // fixed
    "version": "1.0.0",         // semver
    "serviceType": "string",     // e.g. "file-manager", "printer", "report"
    "disabled": false,           // set true to temporarily disable
    "serverUrl": "string"        // target service IP (editable by admin)
  },

  // ── Display Metadata ──
  "info": {
    "title": "string",           // human-readable name
    "description": "string",     // one-paragraph summary
    "tags": ["string", "..."]    // for discovery / filtering
  },

  // ── Runtime ──
  "runtime": {
    "interpreter": "python3",    // fixed — all handlers are Python
    "workDir": "./service_plugins/<plugin-name>",
    "defaultTimeout": 30         // seconds
  },

  // ── Methods ──
  "methods": [
    {
      "name": "string",          // MCP method name, dot-separated
      "description": "string",   // what it does, one sentence
      "inputSchema": {           // JSON Schema for params
        "type": "object",
        "properties": { /* ... */ },
        "required": ["..."]
      },
      "handler": "script.py",    // relative to plugin root
      "mode": "sync",            // fixed — all methods are sync
      "timeout": 30,             // seconds, per-call
      "risk_level": "normal"     // "normal" | "risk" | "auth" | "disable"
    }
  ],

  // ── Plugin Config ──
  "config": {
    // plugin-specific key-value pairs
    // handlers read this directly — the bridge never touches it
  }
}
```

#### Method `risk_level`

Controls how the AI agent executes this method:

| Level | Behavior |
|-------|----------|
| `normal` | Direct execution. Logged to audit trail, no special marking. |
| `risk` | Direct execution, but **flagged prominently** in the audit log for later review. |
| `auth` | **HITL (Human In The Loop)** — the agent pauses and requires authorization from a designated approver before proceeding. |
| `disable` | **Disabled** — the method is unavailable. Users can turn off standard plugin features they don't need. The agent receives a "function disabled" response. |

#### Method `name` Convention

Use dot-separated hierarchical names:

```
<domain>.<category>.<action>

Examples:
  smb.file.list        — SMB domain, file category, list action
  smb.file.mkdir
  smb.file.delete
  printer.job.submit   — (future) printer domain, job category
  report.sales.weekly  — (future) report domain, sales category
```

### Communication Protocol

The bridge communicates with each handler via **stdin / stdout**. No CLI arguments other than the method name.

#### Bridge → Handler

```
Command:  python3 <handler.py> <method_name>

stdin:    {"param1": "value1", "param2": "value2"}
```

- `sys.argv[1]` — the method name (e.g., `"smb.file.list"`). Use it for logging or dispatch.
- `sys.stdin` — the full parameter object as a single JSON string, matching the method's `inputSchema`.

#### Handler → Bridge

```
stdout:   {"code": 0, "msg": "ok", "data": { ... }}
```

- `code` = `0` → success, bridge returns `data` to the caller.
- `code` = `-1` → failure, bridge returns `msg` as the error description.
- stdout **must contain exactly one line** — the JSON response.
- Debug / error logs go to `stderr`, never stdout.

#### Why stdin/stdout instead of CLI args?

1. **Arbitrary parameter complexity** — JSON on stdin handles nested objects, arrays, large payloads without shell escaping issues.
2. **Config isolation** — the bridge passes only the method parameters. Plugin-specific config (server address, credentials) is read by the handler directly from `plugin.json`. The bridge never sees it.
3. **Simplicity** — a single, unchanging protocol for all plugins. No positional arg ordering to memorize.

### Method Handler Template

```python
#!/usr/bin/env python3
"""
<handler>.py — <brief description>
"""
import sys
import json
import traceback
from <shared_module> import output_json


def main():
    # 1. Identify which method is being called
    method_name = sys.argv[1] if len(sys.argv) > 1 else "unknown"

    # 2. Read params from stdin
    raw = sys.stdin.read().strip()
    try:
        params = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        print(f"[{method_name}] Invalid params JSON: {raw[:200]}", file=sys.stderr)
        sys.exit(1)

    # 3. Validate required params
    required_param = params.get("required_param")
    if not required_param:
        output_json(-1, "Missing required parameter: required_param")

    # 4. Business logic
    try:
        # ... do the work ...
        result = {"key": "value"}
        output_json(0, "ok", result)
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        output_json(-1, str(e))


if __name__ == "__main__":
    main()
```

### Response Format

Every handler must output exactly one JSON object to stdout:

```json
// Success
{
  "code": 0,
  "msg": "ok",
  "data": {
    // Method-specific payload.
    // Can be any valid JSON: object, array, string, number, null.
  }
}

// Failure
{
  "code": -1,
  "msg": "Human-readable error description.",
  "data": null
}
```

Rules:
- `msg` on failure must be specific and actionable (e.g., `"Path 'foo/bar' does not exist"`, not `"Error"`).
- `data` on failure must be `null`.
- Use `ensure_ascii=False` when calling `json.dumps` to preserve non-ASCII characters in responses.

### Error Handling

- **Wrap everything** in a `try / except` at the top level of `main()`.
- **Never let the script crash** — an unhandled exception causes the bridge to receive no valid JSON and report a generic failure.
- **Log to stderr** — use `traceback.print_exc(file=sys.stderr)` for full stack traces; the bridge ignores stderr entirely.
- **Validate early** — check required parameters before any side-effect operations (network calls, file writes).

### Shared Utilities

Extract common logic into a shared module (e.g., `smb_utils.py`) within the plugin folder:

```python
# smb_utils.py — example structure
import json, sys, os

def output_json(code: int, msg: str, data=None):
    """Unified JSON response. Exits on failure."""
    print(json.dumps({"code": code, "msg": msg, "data": data},
          ensure_ascii=False, default=str))
    if code != 0:
        sys.exit(1)

def load_plugin_config() -> dict:
    """Read plugin.json from the script's directory."""
    config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "plugin.json"
    )
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_config_section(section: str) -> dict:
    """Get a specific section from plugin.json."""
    return load_plugin_config().get(section, {})
```

Key points:
- Config is loaded from `plugin.json` **relative to the script's own location** (`os.path.dirname(__file__)`), making the plugin fully portable.
- Cache the config if you read it frequently (each handler runs as a short-lived process, so caching is only useful within a single invocation).

## FAQ

<details>
<summary><b>Q: How does the bridge discover plugins?</b></summary>

On startup, the bridge scans `service_plugins/*/plugin.json`. Every folder containing a valid `plugin.json` is registered as an active plugin. Invalid manifests are logged and skipped.
</details>

<details>
<summary><b>Q: Can two plugins expose the same method name?</b></summary>

No. Method names in `plugin.json` must be globally unique across all plugins. The bridge uses the method name as the unique key for routing.
</details>

<details>
<summary><b>Q: How do I add a new method to an existing plugin?</b></summary>

1. Write a new `.py` handler script in the plugin folder.
2. Add a new entry to the `methods` array in `plugin.json` with the corresponding `handler` field.
3. The bridge dynamically loads the new method on next discovery cycle.
</details>

<details>
<summary><b>Q: Can a plugin depend on another plugin?</b></summary>

Plugins are designed to be independent and self-contained. Inter-plugin dependencies are not supported — if two services need to interact, expose additional methods on one plugin or introduce a third coordinating plugin.
</details>

<details>
<summary><b>Q: What happens if a handler times out?</b></summary>

The bridge terminates the Python process and returns a timeout error to the caller. The `timeout` field in each method definition controls the per-call limit.
</details>
