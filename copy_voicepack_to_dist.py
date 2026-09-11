# -*- coding: utf-8 -*-

import os
import shutil
import time

SRC = r"D:\AI\ai-chat-agent"
DST = r"D:\AI\ai-chat-agent\dist\AI聊天智能体桌面版"


def _rename_aside(path):
    if not os.path.exists(path):
        return None
    new = "%s_old_%d" % (path, int(time.time()))
    shutil.move(path, new)
    return new



dd = os.path.join(DST, "voices_cloned")
if os.path.isdir(dd):
    print("dist 已存在 voices_cloned/，保留不动（个人音色不内置）")
else:
    os.makedirs(dd, exist_ok=True)
    print("已为 dist 创建空 voices_cloned/ 骨架（个人音色需用户自行拖入生成）")



dj = os.path.join(DST, "cloned_voices.json")
if os.path.isfile(dj):
    print("dist 已有 cloned_voices.json，保留不动")
else:
    with open(dj, "w", encoding="utf-8") as f:
        f.write('{\n  "voices": []\n}\n')
    print("已写入空 cloned_voices.json")






for cfg in ("settings.json", "tts_config.json", "ai_models.json"):
    src_cfg = os.path.join(SRC, cfg)
    dst_cfg = os.path.join(DST, cfg)
    if os.path.isfile(dst_cfg):
        print("dist 已有 %s，保留不动（用户运行期配置不覆盖）" % cfg)
    elif os.path.isfile(src_cfg):
        shutil.copy2(src_cfg, dst_cfg)
        print("已从项目根补回 %s" % cfg)
    else:
        print("警告：项目根缺少 %s，dist 将无此配置（程序会回退默认）" % cfg)

print("=== VOICEPACK PREP DONE（个人音色不会内置分发） ===")
print("dist voices_cloned 存在:", os.path.isdir(os.path.join(DST, "voices_cloned")))
