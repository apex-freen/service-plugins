#!/usr/bin/env python3
"""
smb_utils.py —— SMB 文件管理插件公共模块
==========================================
封装 smbprotocol 库的连接、操作和错误处理逻辑。
支持 SMB 2.0.2 ~ 3.1.1 协议，包括匿名/Guest 访问和 NTLM 认证。
"""
import uuid
import sys
import json
import os
from typing import Any

from smbprotocol.connection import Connection
from smbprotocol.session import Session
from smbprotocol.tree import TreeConnect
from smbprotocol.open import (
    Open,
    FilePipePrinterAccessMask,
    FileAttributes,
    ImpersonationLevel,
    ShareAccess,
    CreateDisposition,
    CreateOptions,
    FileInformationClass,
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
# 插件配置加载（从 plugin.json 直接读取，不依赖宿主传参）
# ============================================================

_plugin_config_cache = None


def load_plugin_config() -> dict:
    """读取当前插件目录下的 plugin.json，结果缓存"""
    global _plugin_config_cache
    if _plugin_config_cache is not None:
        return _plugin_config_cache

    # 脚本所在目录即为插件根目录
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


def get_smb_config() -> dict:
    """获取 SMB 连接配置（来自 plugin.json config 节）"""
    plugin = load_plugin_config()
    return plugin.get("config", {})


def get_manifest() -> dict:
    """获取插件清单（来自 plugin.json manifest 节）"""
    plugin = load_plugin_config()
    return plugin.get("manifest", {})


def get_server_url() -> str:
    """获取服务端 URL（来自 manifest.serverUrl）"""
    return get_manifest().get("serverUrl", "")


def get_smb_connection_info() -> dict:
    """获取 SMB 连接信息，用于返回给调用方构造访问 URL"""
    config = get_smb_config()
    manifest = get_manifest()
    return {
        "server": str(manifest.get("serverUrl", "")).strip(),
        "port": int(config.get("smb_port", 445)),
        "share": str(config.get("smb_share", "")).strip(),
        "base_path": str(config.get("smb_base_path", "")).strip(),
        "username": str(config.get("smb_username", "")).strip(),
        "password": str(config.get("smb_password", "")),
    }


# ============================================================
# SMB 连接管理
# ============================================================

def connect_smb() -> tuple:
    """
    从 plugin.json 读取 SMB 配置并建立连接

    manifest.serverUrl → SMB 服务器 IP（不含协议前缀）
    config.smb_port/smb_share/smb_username/smb_password/smb_domain → SMB 协议参数

    Returns:
        (connection, session, tree) 三元组
    """
    config = get_smb_config()
    manifest = get_manifest()

    server = str(manifest.get("serverUrl", "")).strip()
    port = int(config.get("smb_port", 445))
    share = str(config.get("smb_share", "")).strip()
    username = str(config.get("smb_username", "")).strip()
    password = str(config.get("smb_password", ""))
    domain = str(config.get("smb_domain", "")).strip()

    if not server:
        output_json(
            -1,
            "插件配置错误: manifest.serverUrl 未配置。"
            "请在 plugin.json 的 manifest.serverUrl 字段配置目标 SMB 服务器 IP 地址",
        )

    if not share:
        output_json(
            -1,
            "SMB配置错误: 缺少 smb_share。"
            "请在插件目录的 plugin.json 中 config.smb_share 字段配置共享名称",
        )

    try:
        # 1. 建立 TCP 连接
        connection = Connection(uuid.uuid4(), server, port)
        connection.connect()
    except Exception as e:
        output_json(-1, f"无法连接到SMB服务器 {server}:{port}: {e}")

    try:
        # 2. 建立会话（匿名或 NTLM 认证）
        #    域账号格式: DOMAIN\username
        effective_username = f"{domain}\\{username}" if domain and username else username
        session = Session(
            connection,
            username=effective_username,
            password=password,
        )
        session.connect()

        # 3. 连接到共享
        tree = TreeConnect(session, f"\\\\{server}\\{share}")
        tree.connect()
    except Exception as e:
        # 断开连接再抛出
        try:
            connection.disconnect()
        except Exception:
            pass
        auth_desc = "匿名/Guest" if not username else f"用户 {username}"
        output_json(-1, f"访问共享 \\\\{server}\\{share} 失败（{auth_desc}）: {e}")

    return connection, session, tree


def disconnect_smb(connection, session, tree) -> None:
    """安全断开 SMB 连接（忽略断开时的异常）"""
    for obj in (tree, session, connection):
        try:
            if obj is not None:
                obj.disconnect()
        except Exception:
            pass


# ============================================================
# 路径处理
# ============================================================

def normalize_path(base_path: str, sub_path: str = "") -> str:
    """
    拼接 base_path 和 sub_path，返回正斜杠格式的相对路径

    Args:
        base_path: 插件配置的 smb_base_path
        sub_path: 方法参数传入的 path

    Returns:
        正斜杠格式的路径，开头无 /
    """
    # 处理空值和多余空白
    base = base_path.strip() if base_path else ""
    sub = sub_path.strip() if sub_path else ""

    # 用 / 拼接
    if base and sub:
        combined = f"{base}/{sub}"
    elif base:
        combined = base
    else:
        combined = sub

    # 清理连续斜杠
    while "//" in combined:
        combined = combined.replace("//", "/")

    # 去掉开头和结尾的斜杠
    combined = combined.strip("/")

    return combined


# ============================================================
# 目录列表
# ============================================================

def list_directory(tree, path: str) -> list[dict]:
    """
    列出指定目录下的所有文件和子目录

    smbprotocol 返回的是结构化对象（如 FileDirectoryInformation），
    通过属性访问（.file_name）而非字典键访问。

    Args:
        tree: TreeConnect 实例
        path: 要列出的目录路径

    Returns:
        文件/目录信息列表，每项包含 name/type/size/created/modified/is_hidden
    """
    raw_entries = []

    try:
        dir_open = Open(tree, path)
        dir_open.create(
            ImpersonationLevel.Impersonation,
            FilePipePrinterAccessMask.GENERIC_READ,
            FileAttributes.FILE_ATTRIBUTE_DIRECTORY,
            ShareAccess.FILE_SHARE_READ | ShareAccess.FILE_SHARE_WRITE,
            CreateDisposition.FILE_OPEN,
            CreateOptions.FILE_DIRECTORY_FILE,
        )
    except Exception as e:
        output_json(-1, f"无法打开目录 '{path}': {e}")

    # 读取目录（单次调用，避免某些 SMB 实现的分页 bug 导致无限循环）
    try:
        raw_entries = dir_open.query_directory(
            "*", FileInformationClass.FILE_DIRECTORY_INFORMATION, flags=0
        )
    except Exception as e:
        dir_open.close()
        output_json(-1, f"读取目录 '{path}' 失败: {e}")

    dir_open.close()

    entries = []
    for entry in raw_entries:
        # SMB 协议中 file_name 是 UTF-16LE 编码的字节，需要解码
        name_field = entry["file_name"]
        name_bytes = name_field.get_value() if hasattr(name_field, "get_value") else name_field
        if isinstance(name_bytes, bytes):
            # 去掉尾部 null 字节后，确保字节数为偶数（UTF-16LE 每字符 2 字节）
            name_bytes = name_bytes.rstrip(b"\x00")
            if len(name_bytes) % 2 != 0:
                name_bytes = name_bytes + b"\x00"
            name = name_bytes.decode("utf-16-le", errors="replace")
        else:
            name = str(name_bytes)
        # 跳过 . 和 ..
        if name in (".", ".."):
            continue

        attrs_field = entry["file_attributes"]
        attrs = int(attrs_field.get_value() if hasattr(attrs_field, "get_value") else attrs_field)
        is_dir = bool(attrs & FileAttributes.FILE_ATTRIBUTE_DIRECTORY)
        is_hidden = bool(attrs & FileAttributes.FILE_ATTRIBUTE_HIDDEN)

        entry_type = "directory" if is_dir else "file"
        eof_field = entry["end_of_file"]
        size = int(eof_field.get_value() if hasattr(eof_field, "get_value") else eof_field) if not is_dir else 0

        entries.append(
            {
                "name": name,
                "type": entry_type,
                "size": size,
                "created": str(entry["creation_time"].get_value() if hasattr(entry["creation_time"], "get_value") else entry["creation_time"]),
                "modified": str(entry["last_write_time"].get_value() if hasattr(entry["last_write_time"], "get_value") else entry["last_write_time"]),
                "is_hidden": is_hidden,
            }
        )

    # 排序：目录在前，文件在后，同类按名称字母序
    entries.sort(key=lambda x: (0 if x["type"] == "directory" else 1, x["name"].lower()))

    return entries


# ============================================================
# 创建目录
# ============================================================

def create_directory(tree, path: str) -> str:
    """
    递归创建目录

    Args:
        tree: TreeConnect 实例
        path: 要创建的目录路径

    Returns:
        创建的完整路径
    """
    if not path:
        output_json(-1, "目录路径不能为空")

    # 递归创建各级目录
    parts = [p for p in path.split("/") if p]
    current = ""

    for part in parts:
        current = f"{current}/{part}" if current else part

        # 尝试创建当前级目录
        try:
            dir_open = Open(tree, current)
            dir_open.create(
                ImpersonationLevel.Impersonation,
                0,  # 创建目录不需要数据访问权限
                FileAttributes.FILE_ATTRIBUTE_DIRECTORY,
                ShareAccess.FILE_SHARE_READ | ShareAccess.FILE_SHARE_WRITE,
                CreateDisposition.FILE_CREATE,
                CreateOptions.FILE_DIRECTORY_FILE,
            )
            dir_open.close()
        except Exception as e:
            err_msg = str(e)
            # STATUS_OBJECT_NAME_COLLISION 表示目录已存在，继续处理下一级
            if "STATUS_OBJECT_NAME_COLLISION" in err_msg or "EXISTS" in err_msg.upper():
                continue
            output_json(-1, f"创建目录 '{current}' 失败: {e}")

    return path


# ============================================================
# 删除文件/目录
# ============================================================

def delete_item(tree, path: str) -> dict:
    """
    删除文件或空目录

    Args:
        tree: TreeConnect 实例
        path: 要删除的路径

    Returns:
        {"deleted": path, "type": "file"|"directory"}
    """
    if not path:
        output_json(-1, "删除路径不能为空")

    # 先检查路径类型
    try:
        check_open = Open(tree, path)
        check_open.create(
            ImpersonationLevel.Impersonation,
            FilePipePrinterAccessMask.GENERIC_READ,
            FileAttributes.FILE_ATTRIBUTE_NORMAL,
            ShareAccess.FILE_SHARE_READ | ShareAccess.FILE_SHARE_WRITE | ShareAccess.FILE_SHARE_DELETE,
            CreateDisposition.FILE_OPEN,
            CreateOptions.FILE_NON_DIRECTORY_FILE,
        )
        # 成功打开 → 是文件
        is_directory = False
        check_open.close()
    except Exception:
        try:
            check_open = Open(tree, path)
            check_open.create(
                ImpersonationLevel.Impersonation,
                FilePipePrinterAccessMask.GENERIC_READ,
                FileAttributes.FILE_ATTRIBUTE_DIRECTORY,
                ShareAccess.FILE_SHARE_READ | ShareAccess.FILE_SHARE_WRITE | ShareAccess.FILE_SHARE_DELETE,
                CreateDisposition.FILE_OPEN,
                CreateOptions.FILE_DIRECTORY_FILE,
            )
            is_directory = True
            check_open.close()
        except Exception as e:
            output_json(-1, f"路径 '{path}' 不存在或无法访问: {e}")

    item_type = "directory" if is_directory else "file"

    # 打开并标记为删除
    try:
        item_open = Open(tree, path)
        create_options = CreateOptions.FILE_DIRECTORY_FILE if is_directory else CreateOptions.FILE_NON_DIRECTORY_FILE
        item_open.create(
            ImpersonationLevel.Impersonation,
            FilePipePrinterAccessMask.DELETE,
            FileAttributes.FILE_ATTRIBUTE_DIRECTORY if is_directory else FileAttributes.FILE_ATTRIBUTE_NORMAL,
            ShareAccess.FILE_SHARE_READ | ShareAccess.FILE_SHARE_WRITE | ShareAccess.FILE_SHARE_DELETE,
            CreateDisposition.FILE_OPEN,
            create_options,
        )

        # 设置 FILE_DISPOSITION_INFORMATION: DeletePending = 1
        item_open.set_info(
            FileInformationClass.FILE_DISPOSITION_INFORMATION,
            b"\x01",
        )
        item_open.close()
    except Exception as e:
        err_msg = str(e)
        if "DIRECTORY_NOT_EMPTY" in err_msg.upper():
            output_json(-1, f"删除失败: 目录 '{path}' 非空，只能删除空目录")
        output_json(-1, f"删除 '{path}' 失败: {e}")

    return {"deleted": path, "type": item_type}
