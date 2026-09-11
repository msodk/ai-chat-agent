# -*- coding: utf-8 -*-

import os
import shutil
import time

SITE = r"D:\AI\ai-chat-agent\.venv\Lib\site-packages"
DIST = r"D:\AI\ai-chat-agent\dist\AI聊天智能体桌面版"


def _rename_aside(path):
    
    if not os.path.exists(path):
        return None
    new = "%s_old_%d" % (path, int(time.time()))
    shutil.move(path, new)
    return new


for pkg in ("torch", "torchaudio", "torchgen"):
    src = os.path.join(SITE, pkg)
    dst = os.path.join(DIST, pkg)
    if not os.path.isdir(src):
        print("跳过(源不存在):", src)
        continue
    print("复制 %s -> %s" % (pkg, dst))
    _rename_aside(dst)
    shutil.copytree(src, dst, copy_function=shutil.copy2, dirs_exist_ok=True)
    print("  完成 %s 文件数=%d" % (pkg, len(list(os.walk(dst)))))

print("=== TORCH COPY DONE ===")
print("dist torch 存在:", os.path.isdir(os.path.join(DIST, "torch")))
