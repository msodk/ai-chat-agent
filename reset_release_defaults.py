# -*- coding: utf-8 -*-

import os
import time

ROOT = r"D:\AI\ai-chat-agent"
DIST = os.path.join(ROOT, "dist", "AI聊天智能体桌面版")
ORPHAN = r"D:\AI\_deleted_orphans_%s" % time.strftime("%Y-%m-%d")
os.makedirs(ORPHAN, exist_ok=True)


def _move_out(path):
    
    if not os.path.exists(path):
        return
    base = os.path.basename(path)
    dst = os.path.join(ORPHAN, "%s_reset_%d" % (base, int(time.time() * 1000)))
    try:
        os.rename(path, dst)
        print("  [reset] 移出个人文件: %s -> %s" % (path, dst))
    except OSError as e:
        print("  [warn] 移出失败(被占用): %s :: %s" % (path, e))


def _write_default(path, content):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print("  [reset] 写入默认: %s" % path)
    except OSError as e:
        print("  [warn] 写入失败: %s :: %s" % (path, e))



DEFAULT_SETTINGS = """{
  "voice_enabled": true,
  "voice_speed": 150,
  "voice_volume": 1.0,
  "auto_scroll": true,
  "screen_narrate": true,
  "seamless_read": true,
  "background_type": "image",
  "color1": "#667eea",
  "color2": "#764ba2",
  "background_image": "",
  "permissions": {
    "enabled": false,
    "read": false,
    "write": false,
    "delete": false,
    "system": false
  },
  "selected_voices": {
    "openvoice": {
      "kind": "system",
      "id": "HKEY_LOCAL_MACHINE\\\\SOFTWARE\\\\Microsoft\\\\Speech\\\\Voices\\\\Tokens\\\\TTS_MS_ZH-CN_HUIHUI_11.0",
      "name": "\\u5fae\\u8f6f\\u6167\\u6167\\uff08\\u4e2d\\u6587\\u5973\\u58f0\\uff09",
      "backend": "openvoice"
    }
  },
  "selected_voice": {
    "kind": "system",
    "id": "HKEY_LOCAL_MACHINE\\\\SOFTWARE\\\\Microsoft\\\\Speech\\\\Voices\\\\Tokens\\\\TTS_MS_ZH-CN_HUIHUI_11.0",
    "name": "\\u5fae\\u8f6f\\u6167\\u6167\\uff08\\u4e2d\\u6587\\u5973\\u58f0\\uff09",
    "backend": "openvoice"
  }
}
"""

DEFAULT_TTS = """{
  "backend": "openvoice"
}
"""

DEFAULT_AI_MODELS = """[
  {
    "name": "Ollama \\u00b7 qwen2.5vl:7b",
    "base_url": "http://127.0.0.1:11434/v1",
    "api_key": "",
    "model": "qwen2.5vl:7b",
    "is_local": true,
    "id": "local:424805ee",
    "active": true,
    "builtin": true
  }
]
"""

print(">>> [1] 项目根写入出厂默认配置 ...")
_write_default(os.path.join(ROOT, "settings.json"), DEFAULT_SETTINGS)
_write_default(os.path.join(ROOT, "tts_config.json"), DEFAULT_TTS)
_write_default(os.path.join(ROOT, "ai_models.json"), DEFAULT_AI_MODELS)

print(">>> [2] 项目根移出个人克隆音色 ...")
_move_out(os.path.join(ROOT, "cloned_voices.json"))
_move_out(os.path.join(ROOT, "voices_cloned"))

print(">>> [3] dist 移出全部个人产物（让构建快照为空）...")
for name in ("settings.json", "tts_config.json", "ai_models.json",
             "cloned_voices.json", "voices_cloned", "cosyvoice_prompt_ref.wav"):
    _move_out(os.path.join(DIST, name))

print("=== RESET DONE ===")
print("孤儿目录(待你本机手动清空):", ORPHAN)
