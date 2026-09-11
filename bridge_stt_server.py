# bridge_stt_server.py
# Local STT bridge: wraps the already-cached whisper "small" model into an
# OpenAI-Whisper-compatible POST /v1/audio/transcriptions endpoint, so that
# Touhou Little Maid's "siliconflow" STT type can call it with zero cost,
# fully offline (no API key, no quota).
#
# Why siliconflow type: it uses the standard OpenAI Whisper request/response
# shape (multipart "file" field -> {"text": "..."}), which is exactly what we
# emulate here. We just point its url at this local server.
#
# Usage:
#   D:\AI\ai-chat-agent\.venv\Scripts\python.exe bridge_stt_server.py
import sys
import os
import re
import json
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import whisper

PORT = 4316
MODEL_NAME = "small"  # cached at C:\Users\22680\.cache\whisper\small.pt


def log(msg):
    sys.stderr.write("[stt] " + msg + "\n")
    sys.stderr.flush()


log("loading whisper %s (cpu, fp16=False) ..." % MODEL_NAME)
MODEL = whisper.load_model(MODEL_NAME, device="cpu")
log("model loaded")


def parse_multipart(body, boundary):
    """Return the raw bytes of the first file part (name=file/audio or any
    part that carries a filename). Works without the removed cgi module."""
    delim = b"--" + boundary
    for part in body.split(delim):
        if part in (b"", b"--", b"\r\n--"):
            continue
        if b"\r\n\r\n" not in part:
            continue
        header, content = part.split(b"\r\n\r\n", 1)
        if content.endswith(b"\r\n"):
            content = content[:-2]
        h = header.lower()
        if (b"filename=" in h or b'name="file"' in h or b"name='file'" in h
                or b'name="audio"' in h or b"name='audio'" in h):
            return content
    return None


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"status": "ok"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/v1/audio/transcriptions":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            ctype = self.headers.get("Content-Type", "")
            m = re.search(r"boundary=([^;]+)", ctype)
            if not m:
                self._send(400, {"error": "no multipart boundary"})
                return
            boundary = m.group(1).strip().strip('"').strip("'").encode("utf-8")
            audio = parse_multipart(body, boundary)
            if not audio:
                self._send(400, {"error": "no audio field in multipart"})
                return

            fd, path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            with open(path, "wb") as f:
                f.write(audio)
            try:
                res = MODEL.transcribe(path, language="zh", fp16=False)
                text = (res.get("text") or "").strip()
            finally:
                try:
                    os.remove(path)
                except OSError:
                    pass

            log("recognized: %r" % text[:80])
            self._send(200, {"text": text})
        except Exception as e:
            log("error: %s" % e)
            self._send(500, {"error": str(e)})

    def log_message(self, *args):
        log(args[0] % args[1:])


def main():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    log("listening on http://127.0.0.1:%d/v1/audio/transcriptions" % PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()
