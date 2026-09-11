# -*- coding: utf-8 -*-

import os
import re
import sys
import json
import subprocess


PERM_READ = "read"
PERM_WRITE = "write"
PERM_DELETE = "delete"
PERM_SYSTEM = "system"

PERM_LABELS = {
    PERM_READ: "文件读取",
    PERM_WRITE: "文件写入",
    PERM_DELETE: "文件删除",
    PERM_SYSTEM: "系统/程序控制",
}

DEFAULT_PERMISSIONS = {
    "enabled": False,
    PERM_READ: False,
    PERM_WRITE: False,
    PERM_DELETE: False,
    PERM_SYSTEM: False,
}


def get_config_path():
    if getattr(sys, "_MEIPASS", None):
        return os.path.join(os.path.dirname(sys.executable), "settings.json")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")


def load_permissions():
    
    try:
        with open(get_config_path(), "r", encoding="utf-8") as f:
            cfg = json.load(f)
        perms = cfg.get("permissions", {})
        return {
            "enabled": bool(perms.get("enabled", False)),
            PERM_READ: bool(perms.get(PERM_READ, False)),
            PERM_WRITE: bool(perms.get(PERM_WRITE, False)),
            PERM_DELETE: bool(perms.get(PERM_DELETE, False)),
            PERM_SYSTEM: bool(perms.get(PERM_SYSTEM, False)),
        }
    except Exception:
        return dict(DEFAULT_PERMISSIONS)


def _extract_path(text):
    

    m = re.search(r'[“"「\'‘]([^”"」\'’]+\.\w+)[”"」\'’]', text)
    if m:
        return m.group(1).strip()

    m = re.search(r'[A-Za-z]:[\\/][^\s，。,；;！!？?]+', text)
    if m:
        return m.group(0).strip().rstrip("。，,；;！!？?")

    m = re.search(r'(?:^|\s)(/[^\s，。,；;！!？?]+)', text)
    if m:
        return m.group(1).strip()
    return None


def detect_tool(text):
    
    if not text:
        return None
    t = text.strip()
    tl = t.lower()


    if re.search(r"(关机|关闭电脑|关闭计算机|power\s*off|shut\s*down)", tl):
        return {"tool": "shutdown_system"}
    if re.search(r"(重启电脑|重新启动电脑|reboot|restart\s*computer)", tl):
        return {"tool": "shutdown_system", "action": "restart"}
    if re.search(r"(关闭程序|退出程序|退出应用|关闭本程序|关闭软件|退出本程序|close\s*app|quit\s*app)", tl):
        return {"tool": "close_app"}
    if re.search(r"(重启程序|重启应用|重新打开程序|restart\s*app)", tl):
        return {"tool": "restart_app"}


    if re.search(r"(删除|删掉|移除|del\s|rm\s)", tl):
        p = _extract_path(t)
        if p:
            return {"tool": "delete_file", "path": p}


    if re.search(r"(写入|保存到|保存为|写到|创建文件|新建文件|把.+?保存)", tl):
        p = _extract_path(t)
        if p:
            content = ""
            m = re.search(r"把(.+?)保存到", t)
            if m:
                content = m.group(1).strip()
            return {"tool": "write_file", "path": p, "content": content}


    if re.search(r"(读(一下|取)?|查看|打开|读取)", tl):
        p = _extract_path(t)
        if p:
            return {"tool": "read_file", "path": p}

    return None


def execute_tool(spec, permissions):
    
    if not permissions.get("enabled"):
        return ("⚠️ 模型工具权限未开启，无法执行该操作。请在「设置 → 模型权限」中开启总开关。", None)

    tool = spec.get("tool")
    perm_map = {
        "read_file": PERM_READ,
        "write_file": PERM_WRITE,
        "delete_file": PERM_DELETE,
        "shutdown_system": PERM_SYSTEM,
        "close_app": PERM_SYSTEM,
        "restart_app": PERM_SYSTEM,
    }
    need = perm_map.get(tool)
    if need and not permissions.get(need):
        label = PERM_LABELS.get(need, need)
        return ("⚠️ 未授权：该操作需要「%s」权限。请在「设置 → 模型权限」中开启对应权限。" % label, None)

    if tool == "read_file":
        return _do_read(spec.get("path"))
    if tool == "write_file":
        return _do_write(spec.get("path"), spec.get("content", ""))
    if tool == "delete_file":
        return _do_delete(spec.get("path"))
    if tool == "shutdown_system":
        return _do_shutdown(spec.get("action") == "restart")
    if tool == "close_app":
        return ("👋 收到关闭指令，正在退出程序…", "close_app")
    if tool == "restart_app":
        return ("🔄 收到重启指令，正在重启程序…", "restart_app")
    return ("❓ 未知工具：" + str(tool), None)


def _do_read(path):
    if not path:
        return ("❌ 未指定文件路径", None)
    if not os.path.exists(path):
        return ("❌ 文件不存在：%s" % path, None)
    try:
        size = os.path.getsize(path)
        if size > 200_000:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                data = f.read(200_000)
            return ("📄 %s（仅显示前 200KB，文件共 %dKB）：\n%s" % (path, size // 1024, data), None)
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            data = f.read()
        return ("📄 %s 内容：\n%s" % (path, data), None)
    except Exception as e:
        return ("❌ 读取失败：%s" % e, None)


def _do_write(path, content):
    if not path:
        return ("❌ 未指定写入路径", None)
    if not content:
        content = "（由 AI 模型生成的内容）"
    try:
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return ("✅ 已写入文件：%s（%d 字符）" % (path, len(content)), None)
    except Exception as e:
        return ("❌ 写入失败：%s" % e, None)


def _do_delete(path):
    if not path:
        return ("❌ 未指定删除路径", None)
    if not os.path.exists(path):
        return ("❌ 文件不存在：%s" % path, None)
    try:
        os.remove(path)
        return ("🗑️ 已删除文件：%s" % path, None)
    except Exception as e:
        return ("❌ 删除失败：%s" % e, None)


def _do_shutdown(restart=False):
    try:
        if sys.platform.startswith("win"):
            cmd = ["shutdown", "/r" if restart else "/s", "/t", "3"]
        else:
            cmd = ["shutdown", "-r" if restart else "-h", "now"] if restart \
                else ["shutdown", "-h", "now"]
        subprocess.Popen(cmd)
        verb = "重启" if restart else "关机"
        return ("🔌 电脑将在 3 秒后%s…" % verb, "shutdown_restart" if restart else "shutdown")
    except Exception as e:
        return ("❌ 关机/重启指令执行失败：%s" % e, None)


def maybe_handle(user_text):
    
    spec = detect_tool(user_text)
    if not spec:
        return (None, None)
    perms = load_permissions()
    return execute_tool(spec, perms)
