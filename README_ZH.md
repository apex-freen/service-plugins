<!--
  ┌──────────────────────────────────────────────────┐
  │  apex-mcp-bridge Service Plugins                 │
  │  README 模板 —— 所有项目级文档均照此结构           │
  └──────────────────────────────────────────────────┘
-->
<p align="center">
  <img src="https://img.shields.io/badge/host-apex--mcp--bridge-6c5ce7?style=flat-square" alt="Host">
  <img src="https://img.shields.io/badge/api%20version-plugin.gis%2Fv1-6c5ce7?style=flat-square" alt="API Version">
  <img src="https://img.shields.io/badge/python-≥3.10-3776AB?logo=python&style=flat-square" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License">
</p>

# apex-mcp-bridge 服务插件集

[apex-mcp-bridge](https://github.com/apex-freen/apex-mcp-bridge) 的官方插件生态仓库。每个插件为一个独立服务能力 —— 文件管理、数据报表、网络打印等。

> **设计哲学**：把插件文件夹拷贝到 `service_plugins/` 下，bridge 自动检测并动态加载，无需重启、无需接线、无需注册。
>
> **真正的亮点**：任何人 —— 哪怕完全不懂代码 —— 都可以让 AI 智能体按照本文档中的模板和规范，自动生成自己需要的插件。想要打印机插件？数据报表插件？只需用自然语言描述需求，智能体就能帮你写出来。优秀的社区作品将收录到官方插件库。

> ⚠️ **安全提醒**：插件会在你的主机上执行 Python 代码。请仅安装来自官方仓库或你完全信任来源的插件。如果你从非官方渠道获取了插件，且不了解其代码内容，**请不要使用** —— 它可能包含恶意逻辑，危及你的系统和数据安全。

## 目录

- [已有插件](#已有插件)
- [架构概览](#架构概览)
- [快速开始：使用一个插件](#快速开始使用一个插件)
- [插件开发指南](#插件开发指南)
  - [目录结构](#目录结构)
  - [plugin.json 规范](#pluginjson-规范)
  - [通信协议](#通信协议)
  - [方法处理器模板](#方法处理器模板)
  - [响应格式](#响应格式)
  - [错误处理](#错误处理)
  - [公共工具模块](#公共工具模块)
- [常见问题](#常见问题)

## 已有插件

| 插件 | 服务类型 | 说明 |
|------|----------|------|
| [fnos-smb-file-manager](./fnos-smb-file-manager/) | `file-manager` | FNOS SMB 文件管理 —— 列出文件、创建目录、删除文件/空目录 |

> 更多插件正在开发中。详见[项目路线图](#)。

## 架构概览

```
┌──────────────────────────────┐
│       apex-mcp-bridge         │  ← Rust 宿主，以 Docker 运行于 FNOS
│  (插件自动发现)                 │
├──────────────────────────────┤
│       service_plugins/        │  ← 本仓库
│  ┌──────────────────────────┐ │
│  │  fnos-smb-file-manager/  │ │  ← 自包含插件
│  │    plugin.json            │ │     • manifest（身份标识）
│  │    requirements.txt       │ │     • methods（方法定义）
│  │    *.py（处理器脚本）       │ │     • runtime（运行环境）
│  └──────────────────────────┘ │     • config（私有配置）
│  ┌──────────────────────────┐ │     • handler 脚本
│  │  未来更多插件...           │ │
│  └──────────────────────────┘ │
└──────────────────────────────┘
```

**核心设计原则：**

1. **自包含** —— 每个插件是一个独立文件夹。拷贝即用。
2. **声明式清单** —— `plugin.json` 是唯一真相来源：描述插件是什么、暴露哪些方法、参数长什么样、如何执行。
3. **stdin/stdout 协议** —— bridge 启动处理器脚本后通过标准输入输出通信。没有共享内存、没有 RPC 框架、没有 import 耦合。
4. **进程隔离** —— 每次方法调用启动全新 Python 进程。一个处理器崩溃不会影响 bridge 或其他插件。
5. **配置自管** —— 插件私有配置（服务器地址、凭证等）放在插件自身的 `plugin.json` 中，由处理器直接读取。bridge 完全不需要了解这些。

### 一次方法调用的完整流程

```
用户 (MCP) → bridge → 在 plugin.json 中发现方法
                    → 启动: python3 <handler.py> <方法名>
                    → 通过 stdin 写入参数 JSON
                    → 通过 stdout 读取响应 JSON
                    → 返回给用户
```

## 快速开始：使用一个插件

1. 下载插件文件夹，拷贝到 bridge 的插件目录：

   ```bash
   cp -r fnos-smb-file-manager/ /path/to/apex-mcp-bridge/service_plugins/
   ```

   bridge 自动检测并动态加载，无需重启。

   > 依赖安装是自动的 —— bridge 启动时会扫描所有 `requirements.txt` 并安装。

2. **在管理界面中完成配置** —— 插件下载后为标准化出厂默认值。打开 `apex-mcp-bridge` 的插件管理页面进行调整：

   | 你必须配置 | 说明 |
   |---|---|
   | **服务地址**（`serverUrl`） | 告诉插件目标服务跑在哪台服务器上。每个插件对接一个具体的服务端 —— 在这里填入对应的 IP 或主机名。 |
   | **风险等级**（`risk_level`） | 插件各方法携带出厂默认的风险等级，但你的实际环境可能需要更严格的风控。将任意方法调整为 `normal`、`risk`、`auth` 或 `disable`。 |

   其余配置项（端口、共享名、凭证等）因插件而异 —— 详见各插件自身的 README。

3. 完成。通过 MCP 调用一次方法，验证连通性。

## 插件开发指南

### 目录结构

每个插件遵循统一布局：

```
<插件名称>/
├── plugin.json          # 清单文件 —— 唯一真相来源
├── requirements.txt     # Python 依赖（pip install 格式）
├── <公共模块>.py         # 公共工具（可选）
├── <处理器_a>.py        # 方法处理器脚本
├── <处理器_b>.py
├── README.md            # 英文文档
└── README_ZH.md         # 中文文档
```

- 文件夹名称即插件标识（如 `fnos-smb-file-manager`）。
- 每个 `.py` 处理器对应 `plugin.json` 中的一个方法。

### plugin.json 规范

清单文件分为五个顶层区块：

| 区块 | 用途 |
|------|------|
| `manifest` | 插件身份：名称、版本、目标服务器地址 |
| `info` | 人类可读的元信息：标题、描述、标签 |
| `runtime` | 运行环境：解释器、工作目录 |
| `methods` | 暴露的 MCP 方法：名称、参数、处理器、风险等级 |
| `config` | 插件私有配置（服务器凭证等） |

#### 完整 Schema

```jsonc
{
  // ── 插件身份 ──
  "manifest": {
    "name": "string",            // 唯一插件 ID，kebab-case 格式
    "apiVersion": "plugin.gis/v1", // 协议版本
    "kind": "Plugin",            // 固定值
    "version": "1.0.0",         // 语义化版本
    "serviceType": "string",     // 如 "file-manager"、"printer"、"report"
    "disabled": false,           // 设为 true 可临时禁用
    "serverUrl": "string"        // 目标服务 IP（管理员可修改）
  },

  // ── 展示元信息 ──
  "info": {
    "title": "string",           // 人类可读的名称
    "description": "string",     // 一段话简介
    "tags": ["string", "..."]    // 用于发现和筛选
  },

  // ── 运行环境 ──
  "runtime": {
    "interpreter": "python3",    // 固定值 —— 所有处理器均为 Python
    "workDir": "./service_plugins/<插件名称>",
    "defaultTimeout": 30         // 秒
  },

  // ── 方法定义 ──
  "methods": [
    {
      "name": "string",          // MCP 方法名，用点号分隔
      "description": "string",   // 一句话描述功能
      "inputSchema": {           // 参数的 JSON Schema
        "type": "object",
        "properties": { /* ... */ },
        "required": ["..."]
      },
      "handler": "script.py",    // 相对于插件根目录
      "mode": "sync",            // 固定值 —— 所有方法均为同步
      "timeout": 30,             // 秒，单次调用超时
      "risk_level": "normal"     // "normal" | "risk" | "auth" | "disable"
    }
  ],

  // ── 插件配置 ──
  "config": {
    // 插件自定义键值对
    // 由处理器直接读取 —— bridge 不关心内容
  }
}
```

#### 方法 `risk_level` 说明

控制 AI Agent 执行该方法时的风控规则：

| 级别 | 行为 |
|------|------|
| `normal` | 直接放行。记录到调用审计日志，无特殊标记。 |
| `risk` | 直接放行，但在审计日志中**醒目标记**，便于事后审查。 |
| `auth` | **HITL（Human In The Loop）** —— Agent 暂停执行，必须由指定授权人批准后才能继续。 |
| `disable` | **禁用**该功能。标准插件中用户不需要的方法可直接关闭，Agent 调用时将收到"功能已禁用"响应。 |

#### 方法 `name` 命名规范

使用点号分隔的层级命名：

```
<领域>.<类别>.<动作>

示例：
  smb.file.list        —— SMB 领域，文件类别，列表操作
  smb.file.mkdir
  smb.file.delete
  printer.job.submit   —— （未来）打印领域，任务类别
  report.sales.weekly  —— （未来）报表领域，销售类别
```

### 通信协议

bridge 与每个处理器之间通过 **stdin / stdout** 通信。除了方法名外，不通过命令行参数传参。

#### Bridge → 处理器

```
命令:     python3 <handler.py> <方法名>

stdin:    {"param1": "value1", "param2": "value2"}
```

- `sys.argv[1]` —— 方法名（如 `"smb.file.list"`）。用于日志或分发。
- `sys.stdin` —— 完整的参数对象，单行 JSON 字符串，格式匹配方法的 `inputSchema`。

#### 处理器 → Bridge

```
stdout:   {"code": 0, "msg": "ok", "data": { ... }}
```

- `code`=`0` → 成功，bridge 将 `data` 返回给调用方。
- `code`=`-1` → 失败，bridge 将 `msg` 作为错误描述返回。
- stdout **必须且只能有一行** —— 就是这条 JSON 响应。
- 调试/错误日志输出到 `stderr`，绝对不要输出到 stdout。

#### 为什么用 stdin/stdout 而非 CLI 参数？

1. **支持任意复杂参数** —— stdin 上的 JSON 可以承载嵌套对象、数组、大数据量，不受 shell 转义限制。
2. **配置隔离** —— bridge 只传入方法参数。插件私有配置（服务器地址、凭证）由处理器直接从 `plugin.json` 读取，bridge 不接触。
3. **简单统一** —— 所有插件一套协议，不用记参数位置顺序。

### 方法处理器模板

```python
#!/usr/bin/env python3
"""
<handler>.py —— <简要说明>
"""
import sys
import json
import traceback
from <公共模块> import output_json


def main():
    # 1. 获取方法名
    method_name = sys.argv[1] if len(sys.argv) > 1 else "unknown"

    # 2. 从 stdin 读取参数
    raw = sys.stdin.read().strip()
    try:
        params = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        print(f"[{method_name}] 参数 JSON 格式无效: {raw[:200]}", file=sys.stderr)
        sys.exit(1)

    # 3. 校验必填参数
    required_param = params.get("required_param")
    if not required_param:
        output_json(-1, "缺少必填参数: required_param")

    # 4. 业务逻辑
    try:
        # ... 执行业务操作 ...
        result = {"key": "value"}
        output_json(0, "ok", result)
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        output_json(-1, str(e))


if __name__ == "__main__":
    main()
```

### 响应格式

每个处理器必须向 stdout 输出唯一一个 JSON 对象：

```json
// 成功
{
  "code": 0,
  "msg": "ok",
  "data": {
    // 方法特定的返回数据。
    // 可以是任意合法 JSON：对象、数组、字符串、数字、null。
  }
}

// 失败
{
  "code": -1,
  "msg": "人类可读的错误描述。",
  "data": null
}
```

规则：
- 失败时的 `msg` 必须具体、可操作（如 `"路径 'foo/bar' 不存在"`，而非 `"错误"`）。
- 失败时的 `data` 必须为 `null`。
- 调用 `json.dumps` 时使用 `ensure_ascii=False`，保留响应中的非 ASCII 字符。

### 错误处理

- **顶层包裹** —— 在 `main()` 最外层用 `try / except` 包裹全部逻辑。
- **绝不让脚本崩溃** —— 未捕获异常会导致 bridge 收不到有效 JSON，只能返回一个通用失败。
- **日志走 stderr** —— 用 `traceback.print_exc(file=sys.stderr)` 输出完整堆栈；bridge 完全忽略 stderr。
- **提前校验** —— 在任何副作用操作（网络调用、文件写入）之前检查必填参数。

### 公共工具模块

把通用逻辑提取到插件文件夹内的公共模块（如 `smb_utils.py`）：

```python
# smb_utils.py —— 示例结构
import json, sys, os

def output_json(code: int, msg: str, data=None):
    """统一 JSON 响应输出。失败时自动退出。"""
    print(json.dumps({"code": code, "msg": msg, "data": data},
          ensure_ascii=False, default=str))
    if code != 0:
        sys.exit(1)

def load_plugin_config() -> dict:
    """从脚本所在目录读取 plugin.json。"""
    config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "plugin.json"
    )
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_config_section(section: str) -> dict:
    """获取 plugin.json 中指定区块的配置。"""
    return load_plugin_config().get(section, {})
```

要点：
- 配置是从 `plugin.json` 中，**相对于脚本自身位置**（`os.path.dirname(__file__)`）读取的，保证插件完全可移植。
- 如果频繁读取配置可以做缓存（每个处理器是短生命周期进程，缓存仅在一次调用内有效）。

## 常见问题

<details>
<summary><b>Q: bridge 如何发现插件？</b></summary>

启动时，bridge 扫描 `service_plugins/*/plugin.json`。每个包含合法 `plugin.json` 的文件夹会被注册为活跃插件。不合法的清单会被记录日志并跳过。
</details>

<details>
<summary><b>Q: 两个插件可以暴露同名方法吗？</b></summary>

不可以。`plugin.json` 中的方法名在所有插件之间必须全局唯一。bridge 以方法名作为路由的唯一键。
</details>

<details>
<summary><b>Q: 如何给已有插件增加新方法？</b></summary>

1. 在插件文件夹内编写新的 `.py` 处理器脚本。
2. 在 `plugin.json` 的 `methods` 数组中新增一条定义，`handler` 指向新脚本。
3. bridge 在下次检测周期自动加载新方法。
</details>

<details>
<summary><b>Q: 插件之间可以有依赖关系吗？</b></summary>

插件设计为独立、自包含。不支持插件间依赖 —— 如果两个服务需要交互，可以在一个插件上暴露更多方法，或引入第三个协调插件。
</details>

<details>
<summary><b>Q: 处理器超时会怎样？</b></summary>

bridge 会终止 Python 进程并向调用方返回超时错误。每个方法定义中的 `timeout` 字段控制单次调用的超时限制。
</details>
