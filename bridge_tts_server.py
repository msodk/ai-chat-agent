# -*- coding: utf-8 -*-

import os
import sys
import json
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

print("[bridge] 加载 OpenVoice 模型(CPU, 首次较慢，请稍候)...", flush=True)
from voice_clone import VoiceCloner, get_model_dir

SE_PATH = os.path.join(get_model_dir(), "base_speakers", "ses", "zh.pth")
if not os.path.exists(SE_PATH):
    raise SystemExit("缺少中文默认声纹文件: " + SE_PATH)


cloner = VoiceCloner(device="cpu")
_warm = cloner.synthesize("预热。", SE_PATH, lang="zh")
print("[bridge] 模型就绪，监听 http://127.0.0.1:9880/tts", flush=True)
print("[bridge] 默认音色: OpenVoice ZH 中文女声（ses/zh.pth）", flush=True)


class TTSHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        route = self.path.split("?")[0].rstrip("/")
        if route != "/tts":
            self.send_error(404, "only /tts supported")
            return
        try:
            n = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(n) if n else b"{}"
            try:
                data = json.loads(raw)
            except Exception:
                data = dict(urllib.parse.parse_qsl(raw.decode("utf-8", "ignore")))
        except Exception as e:
            self.send_error(400, "bad request: %s" % e)
            return

        text = (data.get("text") or data.get("tts_text") or "").strip()
        lang = (data.get("text_lang") or data.get("lang") or "zh")
        if not text:
            self.send_error(400, "missing 'text'")
            return

        try:
            wav = cloner.synthesize(text, SE_PATH, lang=lang)
            with open(wav, "rb") as f:
                audio = f.read()
        except Exception as e:
            self.send_error(500, "synth failed: %s" % e)
            return

        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(audio)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(audio)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 9880), TTSHandler).serve_forever()
