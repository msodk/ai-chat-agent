
import sys
import os
import json
import urllib.parse
import datetime
import random
import re
import threading
import queue
import shutil
import time
import uuid
import base64
import subprocess
import mimetypes
import tempfile
import pyttsx3






try:
    import torch  # noqa: F401
except Exception:
    torch = None

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLineEdit, QPushButton,
                             QPlainTextEdit, QTextEdit,
                             QLabel, QFrame, QScrollArea, QComboBox,
                             QDialog, QCheckBox, QSlider, QGroupBox,
                             QSpinBox, QListWidget, QListWidgetItem, QRadioButton,
                             QButtonGroup, QFileDialog, QGridLayout,
                             QMenu, QAction, QMessageBox,
                             QSystemTrayIcon, QGraphicsDropShadowEffect)


from cosyvoice_tts import (synthesize_cloned, set_tts_backend, get_tts_backend,
                            RECOMMENDED_VOICE_TEXT)
from PyQt5.QtCore import (Qt, QThread, pyqtSignal, QTimer, QRect, QRectF, QPoint,
                         QPointF, QObject, QPropertyAnimation,
                         QEasingCurve, QParallelAnimationGroup, QSize,
                         QEvent)
from PyQt5.QtGui import (QFont, QColor, QPixmap, QPalette, QBrush, QPainter,
                         QImage, QPen, QRadialGradient, QIcon,
                         QPainterPath, QPolygonF, QCursor)
from PyQt5.QtMultimedia import QSound






class _SafeStream:
    def __init__(self, stream):
        self._s = stream

    def write(self, s):
        if self._s is None:
            return 0
        if not isinstance(s, str):
            s = str(s)
        try:
            self._s.write(s)
            return len(s)
        except UnicodeEncodeError:
            try:
                self._s.buffer.write(s.encode('utf-8', 'replace'))
                return len(s)
            except Exception:
                return 0
        except Exception:
            return 0

    def flush(self):
        if self._s is not None:
            try:
                self._s.flush()
            except Exception:
                pass

    def __getattr__(self, name):
        return getattr(self._s, name)


if not isinstance(sys.stdout, _SafeStream):
    sys.stdout = _SafeStream(sys.stdout)
if not isinstance(sys.stderr, _SafeStream):
    sys.stderr = _SafeStream(sys.stderr)






def _run_synthesis_test():
    print("=== SYNTHESIS TEST START ===", flush=True)
    try:
        from voice_clone import VoiceCloner, load_cloned_voices
        voices = load_cloned_voices()
        if not voices:
            print("SYNTHESIS_FAIL: 没有可用克隆音色", flush=True)
            return 1
        vc = VoiceCloner.get_instance(device="cpu")
        se_path = voices[0]["se_path"]
        print("音色:", voices[0]["name"], se_path, flush=True)
        out_wav = vc.synthesize("你好，这是一条测试语音。", se_path, lang="zh")
        print("SYNTHESIS_OK:", out_wav, "size=", os.path.getsize(out_wav), flush=True)
        return 0
    except Exception as e:
        import traceback
        print("SYNTHESIS_FAIL:", e, flush=True)
        traceback.print_exc()
        return 1


if __name__ == "__main__" and "--run-synthesis-test" in sys.argv:
    sys.exit(_run_synthesis_test())




def _run_extract_test():
    print("=== EXTRACT TEST START ===", flush=True)
    try:
        from voice_clone import VoiceCloner
        vc = VoiceCloner.get_instance(device="cpu")
        src = sys.argv[sys.argv.index("--run-extract-test") + 1]
        if not os.path.isfile(src):
            print("EXTRACT_FAIL: 文件不存在", src, flush=True)
            return 1
        print("提取:", src, flush=True)
        pt, err = vc.extract_voice_pack(src)
        if err:
            print("EXTRACT_FAIL:", err, flush=True)
            return 1
        print("EXTRACT_OK:", pt, "size=", os.path.getsize(pt), flush=True)
        return 0
    except Exception as e:
        import traceback
        print("EXTRACT_FAIL:", e, flush=True)
        traceback.print_exc()
        return 1


if __name__ == "__main__" and "--run-extract-test" in sys.argv:
    sys.exit(_run_extract_test())








def _run_panel_test():
    print("=== PANEL TEST START ===", flush=True)
    try:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication
        app = QApplication(sys.argv)

        from voice_cloning_panel import VoiceCloningPanel, CloneWorker
        panel = VoiceCloningPanel()
        print("PANEL_CONSTRUCT_OK", flush=True)

        src = sys.argv[sys.argv.index("--run-panel-test") + 1]
        if not os.path.isfile(src):
            print("PANEL_FAIL: 文件不存在", src, flush=True)
            return 1

        result = {}
        def _on_done(success, fail):
            result["success"] = success
            result["fail"] = fail
            app.quit()
        worker = CloneWorker([src])
        worker.done_signal.connect(_on_done)
        worker.start()
        app.exec_()

        print("PANEL_WORKER result:", result, flush=True)
        if result.get("success", 0) >= 1:
            print("PANEL_OK", flush=True)
            return 0
        print("PANEL_FAIL: success=", result.get("success"), flush=True)
        return 1
    except Exception as e:
        import traceback
        print("PANEL_FAIL:", e, flush=True)
        traceback.print_exc()
        return 1


if __name__ == "__main__" and "--run-panel-test" in sys.argv:
    sys.exit(_run_panel_test())


class SystemTTSThread(QThread):
    
    finished_signal = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self._queue = queue.Queue()
        self._active_token = 0
        self._voice_id = None
        self._quit = False
        self._engine = None

    def run(self):



        _com = None
        try:
            import pythoncom
            pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
            _com = pythoncom
        except Exception:
            pass
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            self._engine.setProperty('rate', 150)
            self._engine.setProperty('volume', 1.0)
        except Exception as e:
            print("系统朗读引擎初始化失败:", e)
            self._engine = None
        try:
            while not self._quit:
                try:
                    item = self._queue.get(timeout=0.5)
                except Exception:
                    continue
                token, text, voice_id = item
                if token != self._active_token:
                    continue
                if self._engine is None or not text:
                    continue
                try:
                    if voice_id:
                        self._engine.setProperty('voice', voice_id)
                    self._engine.say(text)
                    self._engine.runAndWait()
                except Exception as e:
                    print("系统朗读失败:", e)
                finally:
                    if token == self._active_token:
                        self.finished_signal.emit(token)
        finally:
            if _com is not None:
                try:
                    _com.CoUninitialize()
                except Exception:
                    pass

    def enqueue(self, token, text, voice_id):
        
        self._active_token = token
        self._queue.put((token, text, voice_id))

    def interrupt(self, token):
        
        self._active_token = token
        try:
            if self._engine is not None:
                self._engine.stop()
        except Exception:
            pass

    def shutdown(self):
        self._quit = True
        try:
            self._queue.put((self._active_token, "", None))
        except Exception:
            pass


class CloneStreamSynth(QThread):
    
    finished_signal = pyqtSignal(int)  # token

    def __init__(self, se_path, lang, token, synth_lock, queue_, engine,
                 enable_emotion=True, profile=None, speed=1.0):
        super().__init__()
        self.se_path = se_path
        self.lang = lang
        self.token = token
        self.synth_lock = synth_lock
        self.queue = queue_
        self.engine = engine
        self.enable_emotion = enable_emotion


        self.profile = profile or {"se_path": se_path}
        self.speed = speed
        self.task_queue = queue.Queue()

    def submit(self, seg):
        
        self.task_queue.put(seg)

    def finish(self):
        
        self.task_queue.put(None)

    def run(self):
        try:
            while True:
                seg = self.task_queue.get()
                if seg is None:
                    break

                if self.token != self.engine._speak_token:
                    break
                try:
                    with self.synth_lock:

                        wav_path = synthesize_cloned(
                            seg, self.profile, self.lang,
                            enable_emotion=self.enable_emotion, speed=self.speed)
                    self.queue.put((wav_path, self.token, seg))
                except Exception as e:
                    print("分句合成失败:", e)
                    try:
                        self.engine.synth_status_signal.emit("❌ 语音合成失败: %s" % e)
                    except Exception:
                        pass

            self.queue.put((None, self.token, ""))
        finally:
            self.finished_signal.emit(self.token)






class SpeechEngine(QObject):
    

    synth_status_signal = pyqtSignal(str)

    speaking_started = pyqtSignal()
    speaking_finished = pyqtSignal()

    segment_playing = pyqtSignal(str)


    stream_reveal = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.engine = None
        self.voices = []
        self.zh_voice_id = None
        self.en_voice_id = None
        self.current_thread = None
        self._threads = []
        self.is_speaking = False

        self._tts_token = 0
        self._tts_thread = SystemTTSThread()
        self._tts_thread.finished_signal.connect(self.on_speak_finished)
        self._tts_thread.start()

        self._synth_lock = threading.Lock()
        self._speak_token = 0
        self._stream_queue = None
        self._stream_token = 0
        self._stream_first_played = False

        self._stream_files = []


        self._stream_pending = ""
        self._stream_pending_token = 0
        self._stream_flush_timer = None
        self._stream_flush_ms = 120
        self._stream_max_pending = 80

        self._reveal_timer = None
        self._reveal_remaining = 0


        self.voice_speed = 150


        self.seamless_read = True
        self.initialize_engine()

        self.active_voice = {"type": "system", "id": self.zh_voice_id}

        self.emotion_enabled = True

        self._start_openvoice_warmup()

    def initialize_engine(self):
        
        try:
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', 150)
            self.engine.setProperty('volume', 1.0)


            self.voices = self.engine.getProperty('voices')
            

            for voice in self.voices:
                voice_name = voice.name.lower()
                voice_id = voice.id.lower()
                

                if ('chinese' in voice_name or 'zh' in voice_id or 
                    'huihui' in voice_name or '中文' in voice.name):
                    if not self.zh_voice_id:
                        self.zh_voice_id = voice.id
                        print(f"找到中文音色: {voice.name}")
                

                elif ('zira' in voice_name or 'david' in voice_name or 
                      'english' in voice_name or 'en-us' in voice_id):
                    if not self.en_voice_id:
                        self.en_voice_id = voice.id
                        print(f"找到英文音色: {voice.name}")
            

            if not self.zh_voice_id and self.voices:
                self.zh_voice_id = self.voices[0].id
            if not self.en_voice_id and self.voices:
                self.en_voice_id = self.voices[0].id if len(self.voices) == 1 else self.voices[1].id

        except Exception as e:
            print(f"语音引擎初始化失败: {e}")
            self.engine = None

    def detect_language(self, text):
        

        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))

        english_chars = len(re.findall(r'[a-zA-Z]', text))
        

        if chinese_chars > english_chars:
            return 'zh'
        elif english_chars > 0:
            return 'en'
        else:
            return 'zh'

    def speak(self, text):
        

        self.stop()

        try:
            lang = self.detect_language(text)
            av = self.active_voice or {}



            if av.get("type") == "system":
                self._speak_system(text, lang)
                return


            if get_tts_backend() == "cosyvoice":
                self._speak_cloned(text, None, lang)
                return


            if av.get("type") == "cloned":
                se_path = av.get("se_path")
                if not se_path:
                    print("克隆音色缺少 se_path")
                    return


                if lang == 'zh':
                    try:
                        from voice_clone import get_model_dir
                        zh_ckpt = os.path.join(get_model_dir(), "base_speakers", "ZH", "checkpoint.pth")
                        if not os.path.isfile(zh_ckpt):
                            print("【朗读】克隆音色缺少中文基础模型 (base_speakers/ZH)，"
                                  "中文自动回退到系统音色")
                            self._speak_system(text, lang)
                            return
                    except Exception:
                        pass
                self._speak_cloned(text, se_path, lang)
                return


            self._speak_system(text, lang)

        except Exception as e:
            print(f"语音朗读失败: {e}")
            self.is_speaking = False

    def _speak_system(self, text, lang):
        
        if not self.voices:
            print("语音引擎未初始化")
            return

        if lang == 'zh' and self.zh_voice_id:
            voice_id = self.zh_voice_id
        else:
            voice_id = self.en_voice_id


        if not voice_id and self.voices:
            voice_id = self.voices[0].id

        voice_name = "未知"
        for v in self.voices:
            if v.id == voice_id:
                voice_name = v.name
                break
        print(f"使用系统音色朗读: {voice_name} ({voice_id})")


        self._tts_token += 1
        token = self._tts_token
        self.is_speaking = True
        self.speaking_started.emit()
        self._tts_thread.enqueue(token, text, voice_id)

        self._start_char_reveal(text, self._estimate_speak_duration_ms(text, lang))

    def set_active_voice(self, voice_dict):
        
        self.active_voice = voice_dict or {"type": "system", "id": self.zh_voice_id}

    def restore_cloned_voice(self, sel):
        
        try:
            from voice_clone import load_cloned_voices
            if not sel or sel.get("kind") != "cloned":
                return
            name = sel.get("name")
            for v in load_cloned_voices():
                if v.get("name") == name:
                    self.active_voice = {"type": "cloned", "name": name,
                                         "se_path": v.get("se_path"),
                                         "lang": v.get("lang", "zh")}
                    print("已恢复 OpenVoice 克隆音色:", name)
                    return
        except Exception as e:
            print("恢复克隆音色失败:", e)

    def set_tts_backend(self, backend):
        
        set_tts_backend(backend)
        print("TTS 后端已切换为:", backend)

    def _split_sentences(self, text):
        
        text = text.strip()
        if not text:
            return []



        if len(text) <= 120:
            return [text]
        parts = re.split(r'([。！？!?；;\n\r]+)', text)
        segs = []
        for i in range(0, len(parts), 2):
            chunk = parts[i]
            punct = parts[i + 1] if i + 1 < len(parts) else ""
            seg = (chunk + punct).strip()
            if seg:
                segs.append(seg)
        if not segs:
            segs = [text]
        return segs

    def _speak_cloned(self, text, se_path, lang):
        
        speed = self._cosyvoice_speed()
        self._start_stream_session(self.active_voice, lang, speed=speed)
        segs = self._split_sentences(text)
        if not segs:
            self._synth_thread.finish()
            return
        for s in segs:
            self._synth_thread.submit(s)
        self._synth_thread.finish()

    def _current_lang(self):
        
        av = self.active_voice or {}
        return av.get("lang", "zh")

    def _cosyvoice_speed(self):
        
        try:
            rate = float(self.voice_speed) or 150.0
        except Exception:
            rate = 150.0
        sp = rate / 150.0
        return max(0.5, min(2.8, sp))

    def _start_stream_session(self, profile, lang, enable_emotion=None, speed=None):
        
        emo = enable_emotion if enable_emotion is not None else self.emotion_enabled
        if speed is None:
            speed = self._cosyvoice_speed()
        se_path = profile.get("se_path") if isinstance(profile, dict) else profile

        self._cleanup_stream_files()
        self._speak_token += 1
        token = self._speak_token
        self._stream_token = token
        self._stream_first_played = False
        self._stream_pending = ""
        self._stream_pending_token = token
        if self._stream_flush_timer is not None:
            self._stream_flush_timer.stop()
            self._stream_flush_timer = None
        self._stream_queue = queue.Queue()
        self._seamless_chunks = []
        self._synth_thread = CloneStreamSynth(
            se_path, lang, token, self._synth_lock, self._stream_queue, self,
            enable_emotion=emo, profile=profile, speed=speed,
        )
        self._synth_thread.finished_signal.connect(self._on_stream_synth_done)
        self._threads.append(self._synth_thread)
        self._synth_thread.start()
        self.is_speaking = True
        self.speaking_started.emit()
        self.synth_status_signal.emit("🎙️ 正在用克隆音色合成语音，请稍候…")

        QTimer.singleShot(40, self._stream_play_next)

    def append_speak(self, text, lang=None):
        
        if not self.engine:
            return
        lang = lang or self._current_lang()


        if (not self.active_voice or self.active_voice.get("type") != "cloned") \
                and get_tts_backend() != "cosyvoice":

            self._speak_system(text, lang)
            return
        if self._stream_queue is None or self._stream_token != self._speak_token:
            self._start_stream_session(self.active_voice, lang)

        self._stream_pending += text







        if get_tts_backend() == "cosyvoice":
            if len(self._stream_pending) >= 60:
                self._flush_stream_pending()
                return

        else:
            if (re.search(r"[。！？!?；;]", self._stream_pending) or
                    len(self._stream_pending) >= self._stream_max_pending):
                self._flush_stream_pending()
                return

        if self._stream_flush_timer is None:
            self._stream_flush_timer = QTimer(self)
            self._stream_flush_timer.setSingleShot(True)
            self._stream_flush_timer.timeout.connect(self._flush_stream_pending)
        self._stream_flush_timer.start(self._stream_flush_ms)

    def _flush_stream_pending(self):
        
        if self._stream_flush_timer is not None:
            self._stream_flush_timer.stop()
            self._stream_flush_timer = None

        if self._stream_pending_token != self._speak_token:
            self._stream_pending = ""
            return
        pending = self._stream_pending
        self._stream_pending = ""
        if not pending or self._synth_thread is None:
            return

        segs = self._split_sentences(pending)
        for s in segs:
            self._synth_thread.submit(s)

    def finish_stream_session(self):
        
        self._flush_stream_pending()
        if self._synth_thread is not None and self._stream_queue is not None:
            self._synth_thread.finish()

    def _on_stream_synth_done(self, token):

        t = self.sender()
        if t is not None and t in self._threads:
            self._threads.remove(t)
        if token != self._speak_token:
            print("流式合成线程被新请求取代，已停止后续合成")

    def _stop_char_reveal(self):
        
        t = getattr(self, "_reveal_timer", None)
        if t is not None:
            try:
                t.stop()
            except Exception:
                pass
        self._reveal_timer = None
        self._reveal_remaining = 0

    def _start_char_reveal(self, text, duration_ms):
        
        self._stop_char_reveal()
        n = len(text)
        if n <= 0 or not duration_ms or duration_ms <= 0:
            return
        interval = max(25, int(duration_ms) // n)
        self._reveal_remaining = n
        timer = QTimer(self)
        self._reveal_timer = timer

        def _tick():
            if self._reveal_remaining <= 0:
                self._stop_char_reveal()
                return
            self._reveal_remaining -= 1
            self.stream_reveal.emit(1)
            if self._reveal_remaining <= 0:
                self._stop_char_reveal()
        timer.timeout.connect(_tick)
        timer.start()

    def _estimate_speak_duration_ms(self, text, lang):
        
        try:
            rate = float(self.voice_speed) or 150.0
        except Exception:
            rate = 150.0
        scale = rate / 150.0
        if lang == 'en':
            words = max(1, len(text.split()))
            return int(words / 2.5 / scale * 1000)
        chars = max(1, len(re.sub(r'\s+', '', text)))
        return int(chars / 4.5 / scale * 1000)

    def _stream_play_next(self):
        
        if self._stream_token != self._speak_token:
            return
        if self._stream_queue is None:
            return
        try:
            item = self._stream_queue.get_nowait()
        except queue.Empty:

            QTimer.singleShot(30, self._stream_play_next)
            return
        wav_path, seg_token, seg_text = item
        if wav_path is None:

            if seg_token != self._speak_token:
                return
            if getattr(self, "seamless_read", True) and getattr(self, "_seamless_chunks", None):
                self._play_seamless()
            else:
                if self._stream_token == self._speak_token:
                    self.is_speaking = False
                    self.synth_status_signal.emit("✅ 克隆语音播放完成")
                    self.speaking_finished.emit()

                self._cleanup_stream_files()
            return
        if seg_token != self._speak_token:

            self._stream_files.append(wav_path)
            QTimer.singleShot(0, self._stream_play_next)
            return


        wav_path = self._trim_wav_silence(wav_path)
        self._stream_files.append(wav_path)
        if getattr(self, "seamless_read", True):



            self._seamless_chunks.append((wav_path, seg_text))
            QTimer.singleShot(0, self._stream_play_next)
            return

        if not self._stream_first_played:
            self._stream_first_played = True
            self.synth_status_signal.emit("✅ 克隆语音播放中…")


        dur_ms = self._wav_duration_ms(wav_path)
        self._start_char_reveal(seg_text, dur_ms)
        self.play_wav(wav_path)
        QTimer.singleShot(int(dur_ms) + 20, self._stream_play_next)

    def _play_seamless(self):
        
        chunks = self._seamless_chunks
        self._seamless_chunks = []
        if not chunks:
            if self._stream_token == self._speak_token:
                self.is_speaking = False
                self.speaking_finished.emit()
            self._cleanup_stream_files()
            return
        paths = [c[0] for c in chunks]
        texts = [c[1] for c in chunks]
        combined = self._concat_wavs(paths, gap_ms=120)
        if not combined:

            combined = paths[0]

        for p in paths:
            self._stream_files.append(p)
        self._stream_files.append(combined)

        if not self._stream_first_played:
            self._stream_first_played = True
        self.synth_status_signal.emit("✅ 克隆语音播放中…")


        combined_text = "".join(texts)
        dur_ms = self._wav_duration_ms(combined)
        self._start_char_reveal(combined_text, dur_ms)
        self.play_wav(combined)


        QTimer.singleShot(int(dur_ms) + 80, self._on_seamless_done)

    def _on_seamless_done(self):
        if self._stream_token != self._speak_token:
            return
        self.is_speaking = False
        self.synth_status_signal.emit("✅ 克隆语音播放完成")
        self.speaking_finished.emit()
        self._cleanup_stream_files()

    def _concat_wavs(self, wav_list, gap_ms=120):
        
        try:
            import soundfile as sf
            import numpy as np
            target_sr = 44100
            arrays = []
            for p in wav_list:
                if not p or not os.path.exists(p):
                    continue
                try:
                    data, sr = sf.read(p, dtype="float32", always_2d=True)
                except Exception:
                    continue
                if data.shape[1] > 1:
                    data = data.mean(axis=1)
                else:
                    data = data[:, 0]
                if sr != target_sr and sr > 0:
                    n = int(round(len(data) * target_sr / float(sr)))
                    if n > 0:
                        idx = np.linspace(0.0, float(len(data) - 1), n)
                        data = np.interp(idx, np.arange(len(data), dtype=np.float64),
                                        data.astype(np.float64)).astype(np.float32)
                    sr = target_sr
                arrays.append(data)
            if not arrays:
                return None
            gap = np.zeros(int(target_sr * gap_ms / 1000.0), dtype=np.float32)
            out = arrays[0]
            for a in arrays[1:]:
                out = np.concatenate([out, gap, a])
            peak = float(np.max(np.abs(out))) or 1.0
            out = np.clip(out / peak * 0.92, -1.0, 1.0).astype(np.float32)
            tmp = tempfile.mktemp(suffix=".wav")
            sf.write(tmp, out, target_sr, subtype="PCM_16")
            return tmp
        except Exception as e:
            print("拼接 WAV 失败:", e)
            return None

    def _trim_wav_silence(self, path, lead_ms=30, tail_ms=90):
        
        try:
            import wave
            import struct
            with wave.open(path, "rb") as w:
                nch = w.getnchannels()
                sw = w.getsampwidth()
                fr = w.getframerate()
                nframes = w.getnframes()
                raw = w.readframes(nframes)
            if sw not in (2,):
                return path
            samples = struct.unpack("<%dh" % (len(raw) // 2), raw)
            if nch == 2:

                mono = [(samples[i] + samples[i + 1]) // 2 for i in range(0, len(samples), 2)]
            else:
                mono = list(samples)
            peak = max(1, max(abs(s) for s in mono))
            thr = peak * 0.012

            first = next((i for i, s in enumerate(mono) if abs(s) > thr), 0)
            last = next((i for i in range(len(mono) - 1, -1, -1) if abs(mono[i]) > thr), len(mono) - 1)
            lead_n = int(lead_ms * fr / 1000)
            tail_n = int(tail_ms * fr / 1000)
            start = max(0, first - lead_n)
            end = min(len(mono), last + tail_n + 1)
            if end - start < int(fr * 0.1):
                return path
            new_mono = mono[start:end]
            if nch == 2:
                out = []
                for s in new_mono:
                    out.extend([s, s])
                new_raw = struct.pack("<%dh" % len(out), *out)
            else:
                new_raw = struct.pack("<%dh" % len(new_mono), *new_mono)
            with wave.open(path, "wb") as w:
                w.setnchannels(nch)
                w.setsampwidth(sw)
                w.setframerate(fr)
                w.writeframes(new_raw)
            return path
        except Exception:
            return path

    def _wav_duration_ms(self, path):
        
        try:
            import wave
            with wave.open(path, "rb") as w:
                return int(w.getnframes() / float(w.getframerate()) * 1000)
        except Exception:
            return 2000

    def _ensure_pcm_wav(self, path):
        
        try:
            import wave
            with wave.open(path, "rb") as wf:
                sw = wf.getsampwidth()
                nch = wf.getnchannels()
                fr = wf.getframerate()

            if sw == 2 and nch in (1, 2) and fr in (8000, 11025, 16000, 22050, 44100, 48000):
                return path
        except Exception:
            pass
        try:
            import soundfile as sf
            import numpy as np
            data, sr = sf.read(path, dtype="float32", always_2d=True)
            if data.shape[1] > 2:
                data = data[:, :2]
            peak = float(np.max(np.abs(data))) or 1.0
            if peak == 0:
                return path
            data = np.clip(data / peak * 0.92, -1.0, 1.0)
            tmp = tempfile.mktemp(suffix=".wav")
            sf.write(tmp, data, sr, subtype="PCM_16")
            return tmp
        except Exception as e:
            print("PCM 转换失败:", e)
        return path

    def play_wav(self, path):
        
        if not path or not os.path.exists(path):
            print("play_wav: 文件不存在", path)
            return

        try:
            self.segment_playing.emit(path)
        except Exception:
            pass
        playable = self._ensure_pcm_wav(path)
        try:
            import winsound
            winsound.PlaySound(playable, winsound.SND_FILENAME | winsound.SND_ASYNC)
            print("播放 WAV:", os.path.basename(playable))
            return
        except Exception as e:
            print("winsound 播放失败，回退 QSound: %s" % e)
        try:
            QSound.play(playable)
            print("QSound 播放:", os.path.basename(playable))
        except Exception as e:
            print("QSound 播放失败: %s" % e)

    def play_preview(self, path):
        
        if not path or not os.path.exists(path):
            print("play_preview: 文件不存在", path)
            return

        self.reset_stream_session()
        self.play_wav(path)

    def on_speak_finished(self, token=None):
        
        self.is_speaking = False
        self.speaking_finished.emit()

    def _cleanup_stream_files(self):
        
        for path in list(getattr(self, "_stream_files", [])):
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
        self._stream_files = []

    def reset_stream_session(self):
        
        self._speak_token += 1
        self._tts_token += 1


        try:
            if getattr(self, "_tts_thread", None) is not None:
                self._tts_thread.interrupt(self._tts_token)
        except Exception:
            pass
        self._stop_char_reveal()
        old = getattr(self, "_synth_thread", None)
        if old is not None and old.isRunning():
            try:
                old.finish()
            except Exception:
                pass
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
        self._stream_queue = None
        self._stream_first_played = False
        self.is_speaking = False
        self._cleanup_stream_files()

    def stop(self):
        
        self.reset_stream_session()
        self.synth_status_signal.emit("")

    def _start_openvoice_warmup(self):
        
        import threading as _th
        _th.Thread(target=self._warmup_openvoice, daemon=True).start()

    def _warmup_openvoice(self):
        try:
            from voice_clone import VoiceCloner, load_cloned_voices
            vc = VoiceCloner.get_instance(device="cpu")
            vc._ensure_base_tts()
            voices = load_cloned_voices()
            if voices:
                se_path = voices[0]["se_path"]


                with self._synth_lock:
                    vc.synthesize("。", se_path, lang="zh")
            print("OpenVoice 预热完成")
        except Exception as e:
            print("OpenVoice 预热失败(可忽略):", e)


# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
def _guess_media_type(path):
    
    ext = os.path.splitext(path)[1].lower()
    mime, _ = mimetypes.guess_type(path)
    if mime:
        if mime.startswith("image/"):
            return "image"
        if mime.startswith("video/"):
            return "video"
        if mime.startswith("audio/"):
            return "audio"
    doc_exts = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".log",
                ".py", ".js", ".html", ".htm", ".xml", ".yaml", ".yml",
                ".pdf", ".doc", ".docx", ".xlsx", ".ppt", ".pptx", ".rtf"}
    if ext in doc_exts:
        return "file"
    if ext in {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v"}:
        return "video"
    if ext in {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac", ".wma"}:
        return "audio"
    return "file"


def _read_file_b64(path):
    
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")
    except Exception:
        return None


def _audio_format(path):
    
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if ext in {"wav", "mp3", "ogg", "flac", "aac", "m4a"}:
        return ext
    return "wav"


def _find_ffmpeg():
    
    candidates = ["ffmpeg.exe", "ffmpeg",
                  os.path.join(os.path.dirname(sys.executable), "ffmpeg.exe"),
                  r"D:\AI\ai-chat-agent\ffmpeg\ffmpeg.exe"]
    for c in candidates:
        try:

            if os.path.isfile(c):
                return c

            found = shutil.which(c)
            if found:
                return found
        except Exception:
            continue
    return None


def _extract_video_frames(path, max_frames=4):
    
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        return []
    try:
        out_dir = tempfile.mkdtemp(prefix="vidframe_")
        pattern = os.path.join(out_dir, "f%03d.jpg")

        cmd = [ffmpeg, "-loglevel", "error", "-i", path,
               "-vf", "fps=1/2,scale=320:-1",
               "-frames:v", str(max_frames), "-q:v", "4", pattern]

        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run(cmd, check=False, timeout=120,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
        frames = []
        for fn in sorted(os.listdir(out_dir)):
            if fn.lower().endswith(".jpg"):
                b64 = _read_file_b64(os.path.join(out_dir, fn))
                if b64:
                    frames.append(b64)
        shutil.rmtree(out_dir, ignore_errors=True)
        return frames
    except Exception:
        return []


def _read_doc_text(path, limit=8000):
    
    ext = os.path.splitext(path)[1].lower()
    name = os.path.basename(path)
    try:
        if ext in {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".log",
                   ".py", ".js", ".html", ".htm", ".xml", ".yaml", ".yml", ".rtf"}:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        elif ext == ".pdf":
            try:
                from pypdf import PdfReader
            except Exception:
                try:
                    from PyPDF2 import PdfReader
                except Exception:
                    return None
            reader = PdfReader(path)
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
        elif ext in {".docx", ".doc"}:
            try:
                import docx
            except Exception:
                return None
            d = docx.Document(path)
            text = "\n".join((para.text or "") for para in d.paragraphs)
        else:
            return None
        text = text.strip()
        if not text:
            return None
        if len(text) > limit:
            text = text[:limit] + "\n…（内容已截断，仅发送前 %d 字）" % limit
        return "文件《%s》的内容：\n%s" % (name, text)
    except Exception:
        return None




BRAIN_PERSONA = (
    "你是一个会思考、会聊天的智能伙伴，语气自然、像真人对话。\n"
    "当对话中提供了「屏幕/视频背景」信息，那是你私底下的内部知识，"
    "用来理解用户此刻所处的环境；请把它融入你自己的理解，只在相关时自然地用上，"
    "绝不要逐字复述屏幕内容、罗列画面细节，也不要写成「我看到……」这种播报稿——"
    "那样会像一个没有思考能力的机器人。\n"
    "如果屏幕/视频里的某些内容你不明白、或不确定用户想做什么，就自然地开口向用户提问，"
    "像聊天一样把话题接下去，而不是生硬地总结。\n"
    "原则：多用脑子思考，少做复读机。"
)


def _build_multimodal_messages(message, attachments, emotion=None):
    
    text_extra = []
    image_b64_list = []
    audio_b64 = None
    audio_fmt = None
    unsupported = []
    for att in (attachments or []):
        p = att.get("path")
        t = att.get("type", "file")
        if not p or not os.path.exists(p):
            continue
        if t == "image":
            b64 = _read_file_b64(p)
            if b64:
                image_b64_list.append(b64)
            else:
                unsupported.append(os.path.basename(p))
        elif t == "video":
            frames = _extract_video_frames(p)
            if frames:
                image_b64_list.extend(frames)
                text_extra.append("[已附上该视频的 %d 张关键帧图片，供你参考]" % len(frames))
            else:
                unsupported.append(os.path.basename(p) + "(视频抽帧失败)")
        elif t == "audio":
            b64 = _read_file_b64(p)
            if b64:
                audio_b64 = b64
                audio_fmt = _audio_format(p)
                text_extra.append("[已附上音频文件 %s，若你可以处理音频请识别，否则请说明]" % os.path.basename(p))
            else:
                unsupported.append(os.path.basename(p))
        elif t == "file":
            txt = _read_doc_text(p)
            if txt:
                text_extra.append(txt)
            else:
                unsupported.append(os.path.basename(p) + "(无法读取)")
    notes = ""
    if unsupported:
        notes = "\n（提示：以下附件当前模型或许无法直接识别：%s）" % "、".join(unsupported)
    full_text = message or ""
    if text_extra:
        full_text = full_text + "\n" + "\n".join(text_extra)
    full_text = full_text + notes



    sys_text = ""
    if emotion and isinstance(emotion, (tuple, list)) and emotion[0] not in ("中性", None, ""):
        label = emotion[0]
        score = emotion[1] if len(emotion) > 1 else None
        if score is not None:
            sys_text = ("[用户当前情绪：%s（置信度约 %.0f%%），请据此自然调整你的语气与共情程度，"
                        "但无需在回复里点明这一标注]" % (label, score * 100))
        else:
            sys_text = ("[用户当前情绪：%s，请据此自然调整你的语气与共情程度，"
                        "但无需在回复里点明这一标注]" % label)

    has_mm = bool(image_b64_list) or (audio_b64 is not None)
    if has_mm:
        content = []
        if full_text.strip():
            content.append({"type": "text", "text": full_text})
        for b64 in image_b64_list:
            content.append({"type": "image_url",
                            "image_url": {"url": "data:image/jpeg;base64," + b64}})
        if audio_b64 is not None:
            content.append({"type": "input_audio",
                            "input_audio": {"data": audio_b64, "format": audio_fmt}})
        user_msg = {"role": "user", "content": content}
    else:
        user_msg = {"role": "user", "content": full_text}

    openai_messages = [user_msg]
    ollama_messages = [user_msg]

    system_parts = [BRAIN_PERSONA]
    if sys_text:
        system_parts.append(sys_text)
    system_msg = {"role": "system", "content": "\n\n".join(system_parts)}
    openai_messages.insert(0, system_msg)
    ollama_messages.insert(0, system_msg)
    return openai_messages, ollama_messages, image_b64_list



_MULTIMODAL_KEYS = [
    "vl", "llava", "minicpm-v", "minicpm_v", "vision", "bakllava",
    "moondream", "internvl", "cogvlm", "deepseek-vl", "phi-3-vision",
    "phi3-vision", "smolvlm", "qwen-vl", "qwen2-vl", "qwen2.5-vl",
    "qwen3-vl", "glm-4v", "idefics", "fuyu",
]


def _detect_multimodal(name):
    
    n = (name or "").lower()
    return any(k in n for k in _MULTIMODAL_KEYS)





_ollama_tags_cache = {"names": [], "ts": 0.0, "ok": False}
_OLLAMA_TAGS_TTL = 8.0


def scan_ollama_model_names(force=False):
    
    import urllib.request
    now = time.monotonic()
    if not force and _ollama_tags_cache["ok"] and \
            (now - _ollama_tags_cache["ts"]) < _OLLAMA_TAGS_TTL:
        return _ollama_tags_cache["names"]
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags", method="GET")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        names = [(m.get("name") or m.get("model"))
                 for m in data.get("models", [])
                 if (m.get("name") or m.get("model"))]
        _ollama_tags_cache["names"] = names
        _ollama_tags_cache["ts"] = now
        _ollama_tags_cache["ok"] = True
        return names
    except Exception:


        if _ollama_tags_cache["ok"]:
            return _ollama_tags_cache["names"]
        return []


def _pick_local_model(model_names):
    
    if not model_names:
        return None
    mm = [n for n in model_names if _detect_multimodal(n)]
    if mm:
        for prefer in ("qwen2.5-vl", "qwen2-vl", "qwen-vl", "llava", "minicpm-v", "bakllava"):
            for n in mm:
                if prefer in n.lower():
                    return n
        return sorted(mm)[0]
    return model_names[0]


_VISION_HELPER_PROMPT = (
    "请用中文简要描述这张图片的内容，控制在 60 字以内。"
    "只需客观描述你看到了什么，不要推测用户意图，不要添加寒暄。"
)


def _local_vision_model_config():
    
    try:
        installed = scan_ollama_model_names()
        if not installed:
            return None
        picked = _pick_local_model(installed)
        if not picked or not _detect_multimodal(picked):
            return None
        return {
            "base_url": "http://127.0.0.1:11434/v1",
            "model": picked,
            "api_key": "",
            "is_local": True,
        }
    except Exception as e:
        print("[视觉兜底] 扫描本地视觉模型失败:", e)
        return None


def _describe_image_with_local_vision(image_path, context=""):
    
    cfg = _local_vision_model_config()
    if not cfg:
        return None
    prompt = context or _VISION_HELPER_PROMPT
    attachments = [{"path": image_path, "type": "image",
                    "name": os.path.basename(image_path)}]
    try:
        worker = ChatWorker(prompt, attachments=attachments)
        response = worker.call_api(cfg, prompt, attachments)
        if response:
            return response.strip()
    except Exception as e:
        print("[视觉兜底] 本地视觉模型描述失败:", e)
    return None


def _resolve_local_model(model):
    
    if not (model and model.get("is_local")):
        return model
    real_name = (model.get("model") or "").strip()
    installed = scan_ollama_model_names()
    if not real_name or real_name not in installed:
        picked = _pick_local_model(installed)
        if picked:
            model = dict(model)
            model["model"] = picked
    return model


def _build_endpoint_candidates(base, is_local):
    
    candidates = []
    is_ollama = (":11434" in base) or ("127.0.0.1:11434" in base)



    if is_ollama and base.rstrip("/").endswith("/v1"):
        base = base.rstrip("/")[:-3]
    if is_local and is_ollama:
        candidates.append(("ollama", base + "/api/chat"))
        candidates.append(("openai", base + "/v1/chat/completions"))
        candidates.append(("openai", base + "/chat/completions"))
    elif is_local:
        if base.endswith("/v1"):
            candidates.append(("openai", base + "/chat/completions"))
        else:
            candidates.append(("openai", base + "/v1/chat/completions"))
            candidates.append(("openai", base + "/chat/completions"))
    else:
        if base.endswith("/v1"):
            candidates.append(("openai", base + "/chat/completions"))
        else:
            candidates.append(("openai", base + "/v1/chat/completions"))
            candidates.append(("openai", base + "/chat/completions"))
    return candidates


class ChatWorker(QThread):
    

    response_ready = pyqtSignal(str, str, bool)

    partial_ready = pyqtSignal(str)
    gen_started = pyqtSignal()

    def __init__(self, message, attachments=None, emotion=None,
                 speak=False, cleanup_paths=None, tone_meta=""):
        super().__init__()
        self.message = message
        self.attachments = attachments or []
        self.emotion = emotion
        self.speak = speak
        self.cleanup_paths = cleanup_paths or []
        self.tone_meta = tone_meta or ""
        self.streamed = False

    def run(self):
        
        response = ""
        source_tag = "本地模拟"
        self._pending_action = None
        try:


            from tools_agent import maybe_handle as _maybe_tools
            _tool_reply, _pending = _maybe_tools(self.message)
            if _tool_reply is not None:
                response = _tool_reply
                source_tag = "本地工具"
                self._pending_action = _pending

                return
            model = get_active_ai_model()
            if model:

                model = _resolve_local_model(model)
                model_name = model.get("model") or model.get("name", "AI 模型")



                if self.attachments and not detect_model_capabilities(model).get("vision"):
                    fallback = self._vision_fallback_description(model, self.attachments)
                    if fallback:
                        self.message = (self.message or "") + "\n\n" + fallback
                        print("[视觉兜底] 已用本地视觉模型描述 %d 个图像附件" % len(self.attachments))
                    else:
                        self.message = (
                            (self.message or "")
                            + "\n\n（提示：当前模型不支持看图，本机也未安装可用的本地视觉模型，"
                            "无法识别附件中的图像内容。）")
                        print("[视觉兜底] 无本地视觉模型可用，已清空图像附件")
                    self.attachments = []

                has_key = bool(model.get("api_key"))
                is_local = bool(model.get("is_local"))
                if has_key or is_local:

                    try:
                        full = ""
                        stream_started = False
                        for delta in self._stream_api(model, self.message, self.attachments,
                                                      self.emotion, self.tone_meta):
                            full += delta
                            if not stream_started:
                                self.gen_started.emit()
                                stream_started = True
                            self.partial_ready.emit(delta)
                        if not full.strip():
                            raise RuntimeError("流式返回为空")
                        response = full
                        source_tag = model_name
                        self.streamed = True
                    except Exception as e:
                        err = str(e)
                        print("AI 模型流式调用失败，回退整段调用:", err)
                        try:
                            response = self.call_api(model, self.message, self.attachments,
                                                      self.emotion, self.tone_meta)
                            source_tag = model_name


                            if stream_started:
                                self.streamed = True
                        except Exception as e2:
                            err2 = str(e2)
                            print("AI 模型调用失败，回退本地模拟应答:", err2)
                            response = self.generate_response(self.message)
                            if is_local and self._is_local_unreachable(err2):

                                try:
                                    ok, _msg = launch_local_service(
                                        detect_local_svc_type(model), timeout=30)
                                except Exception as le:
                                    ok, _msg = False, str(le)
                                if ok:
                                    model = _resolve_local_model(model)
                                    try:
                                        response = self.call_api(model, self.message, self.attachments,
                                                                  self.emotion, self.tone_meta)
                                        source_tag = model_name + "（已自动启动本地服务）"
                                    except Exception as e3:
                                        err3 = str(e3)
                                        print("自动启动本地服务后仍调用失败:", err3)
                                        response = self.generate_response(self.message)
                                        source_tag = "本地AI启动后仍调用失败（%s）" % (
                                            err3 if len(err3) <= 50 else err3[:47] + "...")
                                else:
                                    source_tag = "本地AI服务未启动（已切回本地模拟应答）"
                            elif not has_key and not is_local:
                                source_tag = "本地模拟（未配置 API 密钥）"
                            else:

                                short = err2 if len(err2) <= 60 else err2[:57] + "..."
                                source_tag = "本地模拟（调用失败:%s）" % short
                else:

                    response = self.generate_response(self.message)
                    source_tag = "本地模拟（未配置 API 密钥）"
            else:
                response = self.generate_response(self.message)
                source_tag = "本地模拟（未选择模型）"
        except Exception as e:
            print("AI 模型调用异常:", e)
            response = self.generate_response(self.message)
            source_tag = "本地模拟（调用异常）"
        finally:

            for _p in self.cleanup_paths:
                try:
                    if os.path.exists(_p):
                        os.remove(_p)
                except Exception:
                    pass

        _do_speak = self.speak and not getattr(self, "streamed", False)
        self.response_ready.emit(response, source_tag, _do_speak)

        _pending = getattr(self, "_pending_action", None)
        if _pending:
            self._handle_pending_action(_pending)

    def _handle_pending_action(self, action):
        
        app = QApplication.instance()
        if action == "close_app":

            self.msleep(800)
            if app is not None:
                app.quit()
        elif action == "restart_app":
            self.msleep(800)
            if app is not None:
                app.quit()

            try:
                os.execv(sys.executable, [sys.executable] + sys.argv)
            except Exception as e:
                print("重启程序失败:", e)

    def _vision_fallback_description(self, current_model, attachments):
        
        cfg = _local_vision_model_config()
        if not cfg:
            return None
        parts = []
        for idx, att in enumerate(attachments or [], 1):
            t = att.get("type")
            if t not in ("image", "video"):
                continue
            path = att.get("path")
            if not path or not os.path.exists(path):
                continue
            if t == "video":
                prompt = ("请用中文简要描述这段视频关键帧呈现的内容，控制在 80 字以内。"
                          "只需客观描述画面，不要推测用户意图，不要添加寒暄。")
            else:
                prompt = _VISION_HELPER_PROMPT
            try:
                worker = ChatWorker(prompt, attachments=[att])
                desc = worker.call_api(cfg, prompt, [att])
                if desc:
                    label = "视频" if t == "video" else "图片"
                    parts.append(
                        "[附件%d：%s %s 的内容描述：%s]"
                        % (idx, label, os.path.basename(path), desc.strip()))
            except Exception as e:
                print("[视觉兜底] 描述附件 %s 失败: %s" % (att.get("name", path), e))
        return "\n".join(parts) if parts else None

    def call_api(self, model, message, attachments=None, emotion=None, tone_meta=""):
        
        import urllib.request
        import urllib.error
        base = (model.get("base_url", "") or "").rstrip('/')
        api_key = (model.get("api_key", "") or "").strip()
        model_name = (model.get("model", "") or "").strip()
        is_local = bool(model.get("is_local"))


        openai_messages, ollama_messages, image_b64_list = _build_multimodal_messages(
            message, attachments, emotion)

        payload = json.dumps({
            "model": model_name,
            "messages": openai_messages,
            "stream": False,
            "tone_meta": tone_meta or "",
        }).encode("utf-8")

        ollama_payload = json.dumps({
            "model": model_name,
            "messages": ollama_messages,
            "stream": False,
            "images": image_b64_list,
        }).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = "Bearer " + api_key


        candidates = _build_endpoint_candidates(base, is_local)

        timeout = 120 if is_local else 30
        last_err = None
        for kind, url in candidates:
            try:
                if kind == "ollama":
                    req = urllib.request.Request(
                        url, data=ollama_payload, method="POST", headers=headers)
                else:
                    req = urllib.request.Request(
                        url, data=payload, method="POST", headers=headers)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                content = self._extract_content(data)
                if content:
                    return content.strip() if isinstance(content, str) else str(content)
                last_err = RuntimeError("接口返回缺少文本内容: %s" % str(data)[:200])
            except urllib.error.HTTPError as he:
                last_err = RuntimeError("HTTP %s %s" % (he.code, he.reason))
            except Exception as e:
                last_err = e
        raise last_err or RuntimeError("未知调用错误")

    def _stream_api(self, model, message, attachments=None, emotion=None, tone_meta=""):
        
        import urllib.request
        import urllib.error
        base = (model.get("base_url", "") or "").rstrip('/')
        api_key = (model.get("api_key", "") or "").strip()
        model_name = (model.get("model", "") or "").strip()
        is_local = bool(model.get("is_local"))

        openai_messages, ollama_messages, image_b64_list = _build_multimodal_messages(
            message, attachments, emotion)

        payload = json.dumps({
            "model": model_name,
            "messages": openai_messages,
            "stream": True,
            "tone_meta": tone_meta or "",
        }).encode("utf-8")
        ollama_payload = json.dumps({
            "model": model_name,
            "messages": ollama_messages,
            "stream": True,
            "images": image_b64_list,
        }).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = "Bearer " + api_key

        candidates = _build_endpoint_candidates(base, is_local)

        timeout = 180 if is_local else 60
        last_err = None
        for kind, url in candidates:
            try:
                data = ollama_payload if kind == "ollama" else payload
                req = urllib.request.Request(url, data=data, method="POST", headers=headers)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    for raw in resp:
                        line = raw.decode("utf-8", "replace").strip()
                        if not line:
                            continue
                        if kind == "ollama":

                            try:
                                obj = json.loads(line)
                            except Exception:
                                continue
                            delta = obj.get("message", {}).get("content", "")
                            if delta:
                                yield delta
                            if obj.get("done"):
                                break
                        else:

                            if not line.startswith("data:"):
                                continue
                            payload_str = line[5:].strip()
                            if payload_str == "[DONE]":
                                break
                            try:
                                obj = json.loads(payload_str)
                            except Exception:
                                continue
                            choices = obj.get("choices") or []
                            if choices:
                                delta = choices[0].get("delta", {}).get("content", "")
                                if delta:
                                    yield delta
                return
            except Exception as e:
                last_err = e
        raise last_err or RuntimeError("流式调用失败")

    @staticmethod
    def _is_local_unreachable(err_text):
        
        if not err_text:
            return False
        low = err_text.lower()
        markers = [
            "10061", "10060", "111", "10057",
            "refused", "no connection", "could not connect",
            "actively refused", "连接被拒绝", "无法连接",
        ]
        return any(m in low for m in markers)

    @staticmethod
    def _extract_content(data):
        
        if not isinstance(data, dict):
            return None
        if "choices" in data and data["choices"]:
            c = data["choices"][0]
            if isinstance(c, dict):
                m = c.get("message") or {}
                if isinstance(m, dict) and m.get("content") is not None:
                    return m["content"]
                if c.get("content") is not None:
                    return c["content"]

                d = c.get("delta") or {}
                if isinstance(d, dict) and d.get("content") is not None:
                    return d["content"]

                if c.get("text") is not None:
                    return c["text"]
        if isinstance(data.get("message"), dict) and data["message"].get("content") is not None:
            return data["message"]["content"]
        if data.get("content") is not None:
            return data["content"]
        if data.get("response") is not None:
            return data["response"]
        return None

    def test_connection(self, model):
        
        import urllib.request
        base_url = (model.get("base_url", "") or "").rstrip('/')
        if not base_url:
            raise ValueError("未填写 API 地址")
        api_key = model.get("api_key", "") or ""
        if model.get("is_local"):

            url = base_url + "/models"
            req = urllib.request.Request(url, method="GET")
            if api_key:
                req.add_header("Authorization", "Bearer " + api_key)
            with urllib.request.urlopen(req, timeout=10) as resp:
                _ = resp.read()
            return True

        candidates = []
        if base_url.endswith("/v1"):
            candidates.append(base_url + "/chat/completions")
        else:
            candidates.append(base_url + "/v1/chat/completions")
            candidates.append(base_url + "/chat/completions")
        payload = json.dumps({
            "model": model.get("model", ""),
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
            "max_tokens": 5,
        }).encode("utf-8")
        last_err = None
        for url in candidates:
            try:
                req = urllib.request.Request(url, data=payload, method="POST")
                req.add_header("Content-Type", "application/json")
                if api_key:
                    req.add_header("Authorization", "Bearer " + api_key)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                if "choices" in data:
                    return True
                last_err = RuntimeError("接口返回异常: %s" % str(data)[:200])
            except Exception as e:
                last_err = e
        raise last_err or RuntimeError("连接测试失败")

    def generate_response(self, user_message):
        
        message_lower = user_message.lower()

        if "你好" in message_lower or "hello" in message_lower:
            responses = [
                "你好！我是AI助手，很高兴为你服务。",
                "嗨！有什么我可以帮助你的吗？",
                "你好！今天有什么想聊的吗？"
            ]
            return random.choice(responses)

        elif "你是谁" in message_lower or "介绍" in message_lower:
            return "我是一个AI智能体，可以和你聊天、回答问题！"

        elif "时间" in message_lower or "几点" in message_lower or "time" in message_lower:
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return f"现在是 {now}"

        elif "谢谢" in message_lower or "thanks" in message_lower:
            return "不客气！有其他问题随时问我。"

        elif "再见" in message_lower or "bye" in message_lower:
            return "再见！期待下次和你聊天！"

        elif "天气" in message_lower:
            return "抱歉，我暂时无法获取天气信息。建议你查看天气应用。"

        elif "名字" in message_lower:
            return "我叫AI聊天智能体，是你的桌面聊天助手！"

        elif "功能" in message_lower or "能做什么" in message_lower:
            return ("我可以：\n"
                   "• 和你聊天对话\n"
                   "• 告诉你当前时间\n"
                   "• 回答简单问题\n"
                   "• 进行日常交流\n"
                   "• 语音朗读回复\n"
                   "试试问我问题吧！")

        elif "帮助" in message_lower or "help" in message_lower:
            return ("我可以：\n"
                   "• 和你聊天对话\n"
                   "• 告诉你当前时间\n"
                   "• 回答简单问题\n"
                   "• 进行日常交流\n"
                   "• 语音朗读回复\n"
                   "试试说：你好、现在几点了、你是谁、帮助")

        else:
            default_responses = [
                f"我听到你说：'{user_message}'，这是个有趣的话题！",
                "嗯，让我想想...你可以告诉我更多细节吗？",
                "好的，我理解了。还有什么想聊的吗？",
                "这个话题很有意思，我们可以继续深入探讨。",
                f"关于'{user_message}'，你有什么想具体了解的吗？"
            ]
            return random.choice(default_responses)


class MessageBubble(QFrame):
    
    def __init__(self, text, is_user=True, source_tag=None, parent=None, typing_mode=False, attachments=None, max_text_width=600):
        super().__init__(parent)
        self.is_user = is_user
        self.source_tag = source_tag
        self.typing_mode = typing_mode
        self.attachments = attachments or []
        self.message_label = None
        self.source_label = None
        self._max_text_width = max_text_width
        self.setup_ui(text, self.attachments)

    def setup_ui(self, text, attachments=None):
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(5)


        time_label = QLabel(datetime.datetime.now().strftime("%H:%M:%S"))
        time_label.setFont(QFont("Microsoft YaHei", 11))
        time_label.setStyleSheet("color: #999999; border: none;")
        layout.addWidget(time_label)


        self.message_label = QLabel(text)
        self.message_label.setFont(QFont("Microsoft YaHei", 13))
        self.message_label.setWordWrap(True)
        self.message_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.message_label.setScaledContents(False)
        self.message_label.setStyleSheet("border: none;")

        self._fit_width(text)

        if self.is_user:

            self.setStyleSheet("""
                QFrame {
                    background-color: #667eea;
                    border-radius: 12px;
                }
            """)
            time_label.setStyleSheet("color: rgba(255, 255, 255, 0.8); border: none;")
            self.message_label.setStyleSheet("color: white; border: none;")
            layout.setAlignment(Qt.AlignRight)
        else:

            self.setStyleSheet("""
                QFrame {
                    background-color: white;
                    border-radius: 12px;
                    border: 1px solid #e0e0e0;
                }
            """)
            time_label.setStyleSheet("color: #999999; border: none;")
            if self.typing_mode:
                self.message_label.setStyleSheet("color: #888888; border: none; font-style: italic;")
            else:
                self.message_label.setStyleSheet("color: #333333; border: none;")
            layout.setAlignment(Qt.AlignLeft)


        if attachments:
            att_widget = self._build_attachments_widget(attachments)
            if att_widget:
                layout.addWidget(att_widget)

        layout.addWidget(self.message_label)


        if not self.is_user and self.source_tag:
            self.source_label = QLabel(self.source_tag)
            self.source_label.setFont(QFont("Microsoft YaHei", 10))
            self.source_label.setStyleSheet("color: #999999; border: none; padding-top: 2px;")
            layout.addWidget(self.source_label)


        self.adjustSize()

    def _fit_width(self, text):
        
        if not self.message_label:
            return
        if not self.is_user:
            self.message_label.setFixedWidth(self._max_text_width)
            return
        fm = self.message_label.fontMetrics()
        lines = text.split('\n') if text else ['']
        natural_w = max((fm.horizontalAdvance(line) for line in lines), default=0)
        if natural_w > self._max_text_width * 0.6:
            self.message_label.setFixedWidth(self._max_text_width)
        else:
            self.message_label.setMinimumWidth(200)
            self.message_label.setMaximumWidth(self._max_text_width)

    def set_text(self, text):
        
        if self.message_label:
            self.message_label.setText(text)
            self._fit_width(text)
            self.adjustSize()

    def append_text(self, text):
        
        if self.message_label:
            cur = self.message_label.text() or ""
            self.message_label.setText(cur + text)
            self._fit_width(cur + text)
            self.adjustSize()

    def set_source_tag(self, tag):
        
        self.source_tag = tag
        if self.source_label:
            self.source_label.setText(tag)
        else:
            if not self.is_user:
                self.source_label = QLabel(tag)
                self.source_label.setFont(QFont("Microsoft YaHei", 10))
                self.source_label.setStyleSheet("color: #999999; border: none; padding-top: 2px;")
                self.layout().addWidget(self.source_label)
        self.adjustSize()

    def set_typing_mode(self, typing_mode):
        
        self.typing_mode = typing_mode
        if not self.message_label:
            return
        if self.is_user:
            self.message_label.setStyleSheet("color: white; border: none;")
        elif typing_mode:
            self.message_label.setStyleSheet("color: #888888; border: none; font-style: italic;")
        else:
            self.message_label.setStyleSheet("color: #333333; border: none;")

    def _build_attachments_widget(self, attachments):
        
        if not attachments:
            return None
        box = QWidget()
        vlay = QVBoxLayout(box)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(6)
        for att in attachments:
            t = att.get("type", "file")
            name = att.get("name") or os.path.basename(att.get("path", ""))
            path = att.get("path", "")
            if t == "image" and path and os.path.exists(path):
                lab = QLabel()
                pix = QPixmap(path)
                if not pix.isNull():
                    pix = pix.scaled(140, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    lab.setPixmap(pix)
                    vlay.addWidget(lab)
                    continue

            icon = {"video": "🎬", "audio": "🎵", "file": "📄", "image": "🖼️"}.get(t, "📎")
            card = QLabel("%s %s" % (icon, name))
            card.setFont(QFont("Microsoft YaHei", 12))
            card.setStyleSheet(
                "background: rgba(255,255,255,0.18); border-radius: 8px; "
                "padding: 6px 10px; border: none;" if self.is_user
                else "background: #f2f2f7; border-radius: 8px; padding: 6px 10px; border: none;")
            card.setTextInteractionFlags(Qt.TextSelectableByMouse)
            vlay.addWidget(card)
        return box


class ChineseColorDialog(QDialog):
    
    def __init__(self, initial_color=None, parent=None):
        super().__init__(parent)
        self.current_color = initial_color if initial_color else QColor(255, 255, 255)
        self.hue = 0
        self.sat = 255
        self.val = 255
        self.setup_ui()
        self.update_from_color(self.current_color)
    
    def setup_ui(self):
        
        self.setWindowTitle("选择颜色")
        self.setFixedSize(650, 500)
        self.setStyleSheet("""
            QDialog {
                background-color: #f5f5f5;
            }
            QLabel {
                color: #333;
                font-size: 13px;
                font-family: "Microsoft YaHei";
            }
            QSpinBox {
                padding: 5px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background: white;
                font-size: 12px;
            }
            QLineEdit {
                padding: 5px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background: white;
                font-size: 12px;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px 30px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #5a7fd6, stop:1 #693d96);
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        

        content_layout = QHBoxLayout()
        

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(10)
        
        basic_label = QLabel("基本颜色")
        basic_label.setFont(QFont("Microsoft YaHei", 23, QFont.Bold))
        left_layout.addWidget(basic_label)
        

        basic_colors = [
            '#000000', '#808080', '#800000', '#808000', '#008000', '#008080', '#000080', '#800080',
            '#ffffff', '#c0c0c0', '#ff0000', '#ffff00', '#00ff00', '#00ffff', '#0000ff', '#ff00ff',
            '#ffc0cb', '#ffd700', '#00ced1', '#1e90ff', '#9370db', '#20b2aa', '#ff6347', '#7fff00',
        ]
        
        colors_grid = QWidget()
        grid_layout = QGridLayout(colors_grid)
        grid_layout.setSpacing(3)
        
        for i, color_hex in enumerate(basic_colors):
            color_btn = QPushButton()
            color_btn.setFixedSize(30, 30)
            color_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color_hex};
                    border: 1px solid #999;
                    border-radius: 3px;
                }}
                QPushButton:hover {{
                    border: 2px solid #667eea;
                }}
            """)
            color_btn.clicked.connect(lambda checked, c=color_hex: self.select_basic_color(c))
            grid_layout.addWidget(color_btn, i // 8, i % 8)
        
        left_layout.addWidget(colors_grid)
        

        custom_label = QLabel("自定义颜色")
        custom_label.setFont(QFont("Microsoft YaHei", 23, QFont.Bold))
        left_layout.addWidget(custom_label)
        
        self.custom_colors = ['#ffffff'] * 16
        custom_grid = QWidget()
        self.custom_grid_layout = QGridLayout(custom_grid)
        self.custom_grid_layout.setSpacing(3)
        self.custom_color_btns = []
        
        for i in range(16):
            color_btn = QPushButton()
            color_btn.setFixedSize(30, 30)
            color_btn.setStyleSheet("""
                QPushButton {
                    background-color: #ffffff;
                    border: 1px solid #999;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    border: 2px solid #667eea;
                }
            """)
            self.custom_color_btns.append(color_btn)
            self.custom_grid_layout.addWidget(color_btn, i // 8, i % 8)
        
        left_layout.addWidget(custom_grid)
        left_layout.addStretch()
        
        content_layout.addWidget(left_panel)
        

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(10)
        

        preview_label = QLabel("颜色预览")
        preview_label.setFont(QFont("Microsoft YaHei", 23, QFont.Bold))
        right_layout.addWidget(preview_label)
        
        self.color_preview = QLabel()
        self.color_preview.setFixedSize(100, 60)
        self.color_preview.setStyleSheet("background-color: white; border: 2px solid #999; border-radius: 5px;")
        right_layout.addWidget(self.color_preview)
        

        params_label = QLabel("颜色参数")
        params_label.setFont(QFont("Microsoft YaHei", 23, QFont.Bold))
        right_layout.addWidget(params_label)
        
        params_widget = QWidget()
        params_layout = QGridLayout(params_widget)
        params_layout.setSpacing(8)
        

        params_layout.addWidget(QLabel("色调(H):"), 0, 0)
        self.hue_spin = QSpinBox()
        self.hue_spin.setRange(0, 360)
        self.hue_spin.setSuffix("°")
        self.hue_spin.valueChanged.connect(self.update_from_hsv)
        params_layout.addWidget(self.hue_spin, 0, 1)
        

        params_layout.addWidget(QLabel("饱和度(S):"), 1, 0)
        self.sat_spin = QSpinBox()
        self.sat_spin.setRange(0, 255)
        self.sat_spin.valueChanged.connect(self.update_from_hsv)
        params_layout.addWidget(self.sat_spin, 1, 1)
        

        params_layout.addWidget(QLabel("明度(V):"), 2, 0)
        self.val_spin = QSpinBox()
        self.val_spin.setRange(0, 255)
        self.val_spin.valueChanged.connect(self.update_from_hsv)
        params_layout.addWidget(self.val_spin, 2, 1)
        

        params_layout.addWidget(QLabel("红(R):"), 3, 0)
        self.red_spin = QSpinBox()
        self.red_spin.setRange(0, 255)
        self.red_spin.valueChanged.connect(self.update_from_rgb)
        params_layout.addWidget(self.red_spin, 3, 1)
        
        params_layout.addWidget(QLabel("绿(G):"), 4, 0)
        self.green_spin = QSpinBox()
        self.green_spin.setRange(0, 255)
        self.green_spin.valueChanged.connect(self.update_from_rgb)
        params_layout.addWidget(self.green_spin, 4, 1)
        
        params_layout.addWidget(QLabel("蓝(B):"), 5, 0)
        self.blue_spin = QSpinBox()
        self.blue_spin.setRange(0, 255)
        self.blue_spin.valueChanged.connect(self.update_from_rgb)
        params_layout.addWidget(self.blue_spin, 5, 1)
        

        params_layout.addWidget(QLabel("HTML代码:"), 6, 0)
        self.html_edit = QLineEdit()
        self.html_edit.setMaxLength(7)
        self.html_edit.textChanged.connect(self.update_from_html)
        params_layout.addWidget(self.html_edit, 6, 1)
        
        right_layout.addWidget(params_widget)
        right_layout.addStretch()
        
        content_layout.addWidget(right_panel)
        
        layout.addLayout(content_layout)
        

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(ok_btn)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: #ccc;
                color: #333;
            }
            QPushButton:hover {
                background: #bbb;
            }
        """)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
    
    def select_basic_color(self, color_hex):
        
        color = QColor(color_hex)
        self.update_from_color(color)
    
    def update_from_color(self, color):
        
        self.current_color = color
        

        self.color_preview.setStyleSheet(f"background-color: {color.name()}; border: 2px solid #999; border-radius: 5px;")
        

        self.hue = color.hue()
        self.sat = color.saturation()
        self.val = color.value()
        

        self.hue_spin.blockSignals(True)
        self.sat_spin.blockSignals(True)
        self.val_spin.blockSignals(True)
        self.hue_spin.setValue(self.hue)
        self.sat_spin.setValue(self.sat)
        self.val_spin.setValue(self.val)
        self.hue_spin.blockSignals(False)
        self.sat_spin.blockSignals(False)
        self.val_spin.blockSignals(False)
        

        self.red_spin.blockSignals(True)
        self.green_spin.blockSignals(True)
        self.blue_spin.blockSignals(True)
        self.red_spin.setValue(color.red())
        self.green_spin.setValue(color.green())
        self.blue_spin.setValue(color.blue())
        self.red_spin.blockSignals(False)
        self.green_spin.blockSignals(False)
        self.blue_spin.blockSignals(False)
        

        self.html_edit.blockSignals(True)
        self.html_edit.setText(color.name())
        self.html_edit.blockSignals(False)
    
    def update_from_hsv(self):
        
        self.hue = self.hue_spin.value()
        self.sat = self.sat_spin.value()
        self.val = self.val_spin.value()
        
        color = QColor.fromHsv(self.hue, self.sat, self.val)
        self.current_color = color
        

        self.color_preview.setStyleSheet(f"background-color: {color.name()}; border: 2px solid #999; border-radius: 5px;")
        

        self.red_spin.blockSignals(True)
        self.green_spin.blockSignals(True)
        self.blue_spin.blockSignals(True)
        self.red_spin.setValue(color.red())
        self.green_spin.setValue(color.green())
        self.blue_spin.setValue(color.blue())
        self.red_spin.blockSignals(False)
        self.green_spin.blockSignals(False)
        self.blue_spin.blockSignals(False)
        

        self.html_edit.blockSignals(True)
        self.html_edit.setText(color.name())
        self.html_edit.blockSignals(False)
    
    def update_from_rgb(self):
        
        r = self.red_spin.value()
        g = self.green_spin.value()
        b = self.blue_spin.value()
        
        color = QColor(r, g, b)
        self.current_color = color
        

        self.color_preview.setStyleSheet(f"background-color: {color.name()}; border: 2px solid #999; border-radius: 5px;")
        

        self.hue_spin.blockSignals(True)
        self.sat_spin.blockSignals(True)
        self.val_spin.blockSignals(True)
        self.hue_spin.setValue(color.hue())
        self.sat_spin.setValue(color.saturation())
        self.val_spin.setValue(color.value())
        self.hue_spin.blockSignals(False)
        self.sat_spin.blockSignals(False)
        self.val_spin.blockSignals(False)
        

        self.html_edit.blockSignals(True)
        self.html_edit.setText(color.name())
        self.html_edit.blockSignals(False)
    
    def update_from_html(self, text):
        
        if text.startswith('#') and len(text) == 7:
            color = QColor(text)
            if color.isValid():
                self.current_color = color
                

                self.color_preview.setStyleSheet(f"background-color: {color.name()}; border: 2px solid #999; border-radius: 5px;")
                

                self.hue_spin.blockSignals(True)
                self.sat_spin.blockSignals(True)
                self.val_spin.blockSignals(True)
                self.hue_spin.setValue(color.hue())
                self.sat_spin.setValue(color.saturation())
                self.val_spin.setValue(color.value())
                self.hue_spin.blockSignals(False)
                self.sat_spin.blockSignals(False)
                self.val_spin.blockSignals(False)
                

                self.red_spin.blockSignals(True)
                self.green_spin.blockSignals(True)
                self.blue_spin.blockSignals(True)
                self.red_spin.setValue(color.red())
                self.green_spin.setValue(color.green())
                self.blue_spin.setValue(color.blue())
                self.red_spin.blockSignals(False)
                self.green_spin.blockSignals(False)
                self.blue_spin.blockSignals(False)
    
    def get_color(self):
        
        return self.current_color




#   [{"id","name","base_url","api_key","model","active"}]
def get_ai_models_path():
    
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(os.path.dirname(sys.executable), 'ai_models.json')
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ai_models.json')


def load_ai_models():
    
    p = get_ai_models_path()
    if os.path.exists(p):
        try:
            with open(p, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as e:
            print("读取 ai_models.json 失败:", e)
            return []
    return []


def save_ai_models(models):
    
    p = get_ai_models_path()
    try:
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(models, f, ensure_ascii=False, indent=2)
        print("AI 模型已保存:", [m.get("name") for m in models])
    except Exception as e:
        print("保存 AI 模型失败:", e)


def get_active_ai_model():
    
    for m in load_ai_models():
        if m.get("active"):
            return m
    return None






#





#




_CAP_KEYWORDS = {
    "emotion": ["情感", "情绪", "语气", "语调", "情感分析", "情感识别", "共情",
                "emotion", "sentiment", "mood", "emo", "tone", "affect",
                "feeling", "empathetic", "empath"],
    "vision": ["视觉", "看图", "多模态", "识图", "vision", "see", "mm",
               "multimodal", "vl", "llava", "qwen-vl", "internvl", "cogvlm",
               "moondream", "bakllava", "minicpm-v", "deepseek-vl", "phi-vision",
               "glm-4v", "idefics", "fuyu", "smolvlm"],
    "asr": ["听", "听觉", "听懂", "听到", "听音", "语音识别", "语音理解",
            "音频理解", "语音转写", "语音输入", "asr", "speech", "audio",
            "listen", "hear", "whisper", "voice", "omni"],
    "tts": [],
}
_CAP_FLAGS = {
    "emotion": "cap_emotion",
    "vision": "cap_vision",
    "tts": "cap_tts",
    "asr": "cap_asr",
}
_ALL_CAPS = ["emotion", "vision", "tts", "asr"]


def _is_builtin_model(model):
    
    if not model or not isinstance(model, dict):
        return False
    if model.get("builtin"):
        return True
    return model.get("model") == "qwen2.5vl:7b"


def detect_model_capabilities(model):
    
    caps = {c: False for c in _ALL_CAPS}
    if not model or not isinstance(model, dict):
        return caps

    raw = model.get("capabilities")
    if isinstance(raw, str):
        raw = [raw]
    if isinstance(raw, (list, tuple)):
        for c in raw:
            if c in caps:
                caps[c] = True

    for cap, flag in _CAP_FLAGS.items():
        if model.get(flag):
            caps[cap] = True

    blob = " ".join(str(model.get(k, "")) for k in
                    ("name", "model", "id", "base_url")).lower()
    for cap in ("emotion", "vision", "asr"):
        if any(k.lower() in blob for k in _CAP_KEYWORDS[cap]):
            caps[cap] = True


    if not caps["vision"] and _detect_multimodal(model.get("model", "")):
        caps["vision"] = True



    if _is_builtin_model(model):
        for cap in ("emotion", "tts", "asr"):
            caps[cap] = False
    return caps


def model_has_emotion_capability(model):
    
    return detect_model_capabilities(model).get("emotion", False)


def probe_local_model_capabilities(model):
    
    if not model or not model.get("is_local"):
        return None
    svc = detect_local_svc_type(model)
    if svc != "ollama":
        return None
    if not is_local_service_up(svc):
        return None
    model_name = (model.get("model") or model.get("name") or "").strip()
    if not model_name:
        return None
    import urllib.request
    import urllib.error
    try:
        url = "http://127.0.0.1:%d/api/show" % _LOCAL_PORTS[svc]
        req = urllib.request.Request(
            url,
            data=json.dumps({"name": model_name}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            info = json.loads(resp.read().decode("utf-8"))
        details = info.get("details") or {}
        families = details.get("families") or []
        if not families and details.get("family"):
            families = [details["family"]]
        fam = [str(x).lower() for x in families]
        joined = " ".join(fam)
        vision = any(k in joined for k in
                     ("clip", "vision", "vl", "mm", "multimodal"))
        return {"vision": vision}
    except Exception as e:
        print("模型能力探测失败（回退静态检测）:", e)
        return None





_LOCAL_PORTS = {"ollama": 11434}
_LOCAL_EXE_NAMES = {"ollama": "ollama"}



_launched_ollama = {}




_OLLAMA_CHILD_NAMES = {"ollama.exe", "llama-server.exe"}


def detect_local_svc_type(model):
    
    base = (model.get("base_url") or "").lower()

    for port in ("11434", "11435", "11436"):
        if (":%s" % port) in base:
            return "ollama"

    if "127.0.0.1:" in base or "localhost:" in base:
        if re.search(r":(11[4-9]\d{2})", base):
            return "ollama"
    return "unknown"


def _parse_host_port(base, default_port=11434):
    
    m = re.search(r"(?:https?://)?([\w.\-]+):(\d{2,5})", base or "")
    if m:
        return m.group(1), int(m.group(2))
    return "127.0.0.1", default_port


def is_ollama_up(host="127.0.0.1", port=11434, timeout=2):
    
    import urllib.request
    try:
        req = urllib.request.Request(
            "http://%s:%d/api/tags" % (host, port), method="GET")
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except Exception:
        return False


def is_local_service_up(svc_type, timeout=2):
    
    if svc_type == "ollama":
        return is_ollama_up("127.0.0.1", _LOCAL_PORTS.get(svc_type, 11434), timeout)
    return False


def _find_service_exe(svc_type):
    
    import shutil
    name = _LOCAL_EXE_NAMES.get(svc_type)
    if not name:
        return None
    exe = shutil.which(name)
    if exe:
        return exe
    if svc_type == "ollama":


        candidates = [
            os.path.join(_pkg_root(), "ollama", "ollama.exe"),
            os.path.join(_pkg_root(), "ollama", "ollama-windows-amd64", "ollama.exe"),
            r"D:\AI\ollama\ollama.exe",
            os.path.expandvars(r"C:\Users\%USERNAME%\AppData\Local\Programs\Ollama\ollama.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
            r"C:\Program Files\Ollama\ollama.exe",
            r"C:\Program Files (x86)\Ollama\ollama.exe",
        ]
        for cand in candidates:
            if os.path.exists(cand):
                return cand
    return None


def _service_launch_cmd(svc_type):
    
    exe = _find_service_exe(svc_type)
    if not exe:
        tips = {
            "ollama": "未找到 ollama 可执行文件。最简方案：把 Ollama 便携版解压到 D:\\AI\\ollama（见项目内 install_ollama_DAI.ps1），"
                       "或到 https://ollama.com 安装桌面版并运行；也可在终端执行 `ollama serve` 启动服务。"
                       "若已放到 D:\\AI\\ollama 仍提示找不到，请重启本软件使其重新探测。",
        }
        return None, "未找到 %s 可执行文件。%s" % (svc_type, tips.get(svc_type, ""))
    if svc_type == "ollama":
        return [exe, "serve"], None
    return None, "未知服务类型: %s" % svc_type


def launch_local_service(svc_type, timeout=30, host=None, port=None):
    
    if svc_type == "ollama":
        if host is None or port is None:
            host, port = "127.0.0.1", _LOCAL_PORTS.get("ollama", 11434)
    if host is None or port is None:
        return False, "未知服务类型: %s" % svc_type
    if is_ollama_up(host, port):
        return True, "服务已在运行"
    cmd, err = _service_launch_cmd(svc_type)
    if err:
        return False, err
    try:
        kwargs = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if sys.platform.startswith("win"):



            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        launch_env = os.environ.copy()
        if svc_type == "ollama":
            launch_env["OLLAMA_HOST"] = "%s:%d" % (host, port)
            launch_env["OLLAMA_MODELS"] = os.path.join(_pkg_root(), "ollama_models")
        proc = subprocess.Popen(cmd, env=launch_env, **kwargs)





        job = _create_kill_job_object()
        if job and _assign_pid_to_job(proc.pid, job):
            print("[Ollama] 已将本软件启动的实例绑定到退出清理 Job Object")
        elif job:
            _close_job_handle(job)
            job = None

        old_item = _launched_ollama.get((host, port))
        if isinstance(old_item, (list, tuple)) and len(old_item) > 2:
            _close_job_handle(old_item[2])
        _launched_ollama[(host, port)] = (proc, time.time(), job)
    except Exception as e:
        return False, "启动命令失败: %s" % e

    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_ollama_up(host, port):
            return True, "服务已启动"
        time.sleep(1)
    return False, "启动超时（%d 秒未就绪）" % timeout


def _kill_proc_tree(pid):
    
    if sys.platform.startswith("win"):
        try:
            subprocess.call(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except Exception:
            pass
    try:
        import signal
        os.kill(pid, signal.SIGTERM)
    except Exception:
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass


def _create_kill_job_object():
    
    if not sys.platform.startswith("win"):
        return None
    try:
        import win32job
        job = win32job.CreateJobObject(None, "")
        if not job:
            return None
        info = win32job.QueryInformationJobObject(
            job, win32job.JobObjectExtendedLimitInformation)
        info["BasicLimitInformation"]["LimitFlags"] |= (
            win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE)
        win32job.SetInformationJobObject(
            job, win32job.JobObjectExtendedLimitInformation, info)
        return job
    except Exception as e:
        print("[Ollama] 创建退出清理 Job Object 失败:", e)
        return None


def _assign_pid_to_job(pid, job):
    
    if not job or not sys.platform.startswith("win"):
        return False
    try:
        import win32job
        import win32api
        import win32con
        h = win32api.OpenProcess(
            win32con.PROCESS_TERMINATE | win32con.PROCESS_SET_QUOTA,
            False, int(pid))
        if not h:
            return False
        try:
            win32job.AssignProcessToJobObject(job, h)
            return True
        finally:
            win32api.CloseHandle(h)
    except Exception as e:
        print("[Ollama] 绑定 PID=%d 到 Job Object 失败:" % pid, e)
        return False


def _close_job_handle(job):
    
    if not job:
        return
    try:
        import win32api
        win32api.CloseHandle(job)
    except Exception:
        pass


def _pkg_root():
    
    if getattr(sys, "frozen", False):
        return os.path.abspath(os.path.join(os.path.dirname(sys.executable), "..", ".."))
    return os.path.abspath(os.path.dirname(__file__))


def _collect_ollama_pids_by_fingerprint(min_start_time=None):
    
    result = set()
    if not sys.platform.startswith("win"):
        return result
    try:
        import psutil
    except Exception:
        return result

    our_models_dir = os.path.join(_pkg_root(), "ollama_models").lower()
    for proc in psutil.process_iter(["pid", "name", "create_time", "cmdline", "cwd", "environ"]):
        try:
            info = proc.info or {}
            name = (info.get("name") or "").lower()
            if name not in _OLLAMA_CHILD_NAMES:
                continue
            pid = int(info.get("pid") or 0)
            if pid <= 4:
                continue
            create_time = info.get("create_time", 0)
            if min_start_time and create_time < min_start_time:
                continue

            env = info.get("environ") or {}
            if env and isinstance(env, dict):
                models_dir = (env.get("OLLAMA_MODELS") or "").lower()
                if models_dir and os.path.abspath(models_dir) == our_models_dir:
                    result.add(pid)
                    continue

            cmdline = info.get("cmdline") or []
            cmd_txt = " ".join(cmdline).lower() if isinstance(cmdline, list) else str(cmdline).lower()
            if our_models_dir in cmd_txt:
                result.add(pid)
                continue

            result.add(pid)
        except Exception:
            continue
    return result


def _collect_launched_descendant_pids(root_pids, min_start_time=None):
    
    root_pids = set(int(p) for p in root_pids if p)
    result = set()
    if not root_pids:
        return result


    try:
        import psutil
        for proc in psutil.process_iter(["pid", "ppid", "name", "create_time"]):
            try:
                info = proc.info or {}
                name = (info.get("name") or "").lower()
                if name not in _OLLAMA_CHILD_NAMES:
                    continue
                pid = int(info.get("pid") or 0)
                if pid in root_pids or pid <= 4:
                    continue

                if min_start_time and info.get("create_time", 0) < min_start_time:
                    continue

                p = proc.parent()
                seen = set()
                while p and p.pid not in seen:
                    seen.add(p.pid)
                    if p.pid in root_pids:
                        result.add(pid)
                        break
                    p = p.parent()
            except Exception:
                continue
        return result
    except Exception:
        pass


    if sys.platform.startswith("win"):
        try:

            import subprocess as _sp
            out = _sp.check_output(
                ["wmic", "process", "where",
                 "name='llama-server.exe' or name='ollama.exe'",
                 "get", "ProcessId,ParentProcessId,Name"],
                stderr=_sp.STDOUT, text=True, errors="ignore", timeout=10)
            candidates = []
            for line in out.splitlines():
                parts = line.strip().split()
                if len(parts) < 3:
                    continue
                try:
                    pid = int(parts[-3])
                    ppid = int(parts[-2])
                    name = parts[-1].lower()
                except ValueError:
                    continue
                if name in _OLLAMA_CHILD_NAMES and pid not in root_pids:
                    candidates.append((pid, ppid))

            if candidates:
                out2 = _sp.check_output(
                    ["wmic", "process", "get", "ProcessId,ParentProcessId"],
                    stderr=_sp.STDOUT, text=True, errors="ignore", timeout=10)
                parent_map = {}
                for line in out2.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        try:
                            parent_map[int(parts[-2])] = int(parts[-1])
                        except ValueError:
                            continue
                for pid, ppid in candidates:
                    cur = ppid
                    seen = set()
                    while cur and cur not in seen:
                        seen.add(cur)
                        if cur in root_pids:
                            result.add(pid)
                            break
                        cur = parent_map.get(cur)
        except Exception:
            pass
    return result


def stop_launched_ollama_instances():
    
    if not _launched_ollama:
        return
    stopped, skipped, killed_children = [], [], []
    root_pids = []
    min_start_time = None
    jobs_to_close = []
    known_children = set()



    for (host, port), item in list(_launched_ollama.items()):
        proc = item[0] if isinstance(item, (list, tuple)) else item
        start_time = item[1] if isinstance(item, (list, tuple)) and len(item) > 1 else None
        job = item[2] if isinstance(item, (list, tuple)) and len(item) > 2 else None
        if job is not None:
            jobs_to_close.append(job)
        if proc.poll() is None:
            if start_time and (min_start_time is None or start_time < min_start_time):
                min_start_time = start_time
            root_pids.append(proc.pid)
            try:
                children = _collect_launched_descendant_pids([proc.pid], min_start_time)
                known_children.update(children)
            except Exception as e:
                print("[退出] 收集 Ollama(%s:%d) 后代失败: %s" % (host, port, e))


    for cpid in known_children:
        try:
            _kill_proc_tree(cpid)
            killed_children.append(str(cpid))
        except Exception as e:
            print("[退出] 关闭 Ollama 子进程 PID=%d 失败: %s" % (cpid, e))


    for (host, port), item in list(_launched_ollama.items()):
        proc = item[0] if isinstance(item, (list, tuple)) else item
        try:
            if proc.poll() is None:
                _kill_proc_tree(proc.pid)
                stopped.append("%s:%d" % (host, port))
            else:
                skipped.append("%s:%d" % (host, port))
        except Exception as e:
            print("[退出] 关闭 Ollama(%s:%d) 失败: %s" % (host, port, e))
    _launched_ollama.clear()



    if min_start_time:
        time.sleep(0.5)
        survivors = _collect_ollama_pids_by_fingerprint(min_start_time)

        if root_pids:
            survivors.update(_collect_launched_descendant_pids(root_pids, min_start_time))
        for cpid in survivors:
            try:
                _kill_proc_tree(cpid)
                if str(cpid) not in killed_children:
                    killed_children.append(str(cpid))
            except Exception as e:
                print("[退出] 补刀 Ollama 进程 PID=%d 失败: %s" % (cpid, e))



    job_killed_count = 0
    for job in jobs_to_close:
        try:
            try:
                import win32job
                plist = win32job.QueryInformationJobObject(
                    job, win32job.JobObjectBasicProcessIdList)
                if isinstance(plist, dict):
                    job_killed_count += len(plist.get("ProcessIdList", []))
                elif isinstance(plist, (list, tuple)):
                    job_killed_count += len(plist)
            except Exception:
                pass
            _close_job_handle(job)
        except Exception as e:
            print("[退出] 关闭 Ollama Job Object 失败:", e)

    if stopped:
        print("[退出] 已自动关闭本软件启动的 Ollama：", ", ".join(stopped))
    if killed_children:
        print("[退出] 已同步关闭 Ollama 相关进程 PID：", ", ".join(killed_children))
    if job_killed_count:
        print("[退出] Job Object 兜底清理了 %d 个 Ollama 相关进程" % job_killed_count)
    if skipped:
        print("[退出] 跳过已退出的 Ollama：", ", ".join(skipped))


class OllamaAutoStartWorker(QThread):
    
    status = pyqtSignal(str)
    finished_up = pyqtSignal(bool, str)

    def __init__(self, model):
        super().__init__()
        self.model = model

    def run(self):
        model = self.model
        if not (model and model.get("is_local")
                and detect_local_svc_type(model) == "ollama"):
            self.finished_up.emit(True, "非本地模型，无需启动 Ollama")
            return
        host, port = _parse_host_port(model.get("base_url") or "", 11434)
        if is_ollama_up(host, port):
            self.status.emit("检测到 Ollama 已在运行，直接复用")
            self.finished_up.emit(True, "已在运行")
            return
        self.status.emit("本地 Ollama 未运行，正在启动界面自带 Ollama…")
        ok, msg = launch_local_service("ollama", timeout=40, host=host, port=port)
        if not ok:
            self.status.emit("界面自带 Ollama 启动失败：%s" % msg)
            self.finished_up.emit(False, msg)
            return

        needed = (model.get("model") or "").strip()

        installed = scan_ollama_model_names(force=True)
        if needed and needed not in installed:
            tip = ("Ollama 已启动，但缺少模型 %s（请在终端执行 ollama pull %s）"
                   % (needed, needed))
            self.status.emit(tip)
            self.finished_up.emit(True, "缺模型：" + needed)
            return
        self.status.emit("Ollama 已就绪（%s）" % (needed or "默认模型"))
        self.finished_up.emit(True, "已就绪")




AI_MODEL_PRESETS = {
    "custom": {
        "name": "自定义 OpenAI 兼容",
        "base_url": "",
        "model": "",
        "is_local": False,
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "is_local": False,
    },
    "qwen": {
        "name": "通义千问 Qwen",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "is_local": False,
    },
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "is_local": False,
    },
    "ollama": {
        "name": "本地 Ollama（qwen2.5vl：识图+聊天）",
        "base_url": "http://127.0.0.1:11434/v1",
        "model": "qwen2.5vl:7b",
        "is_local": True,
        "builtin": True,
    },
}


def get_preset_default(preset_key):
    
    return dict(AI_MODEL_PRESETS.get(preset_key, AI_MODEL_PRESETS["custom"]))


def get_default_ai_models():
    
    defaults = []
    for key, cfg in AI_MODEL_PRESETS.items():
        if key == "custom":
            continue
        item = dict(cfg)
        item["id"] = "preset:" + key
        item["preset_key"] = key
        item["active"] = (key == "ollama")
        item["api_key"] = ""
        defaults.append(item)
    return defaults


class AIModelEditDialog(QDialog):
    


    PRESET_LABELS = [
        ("自定义 / OpenAI 兼容（按需）", "custom"),
        ("DeepSeek（需 API 密钥）", "deepseek"),
        ("通义千问 Qwen（需 API 密钥）", "qwen"),
        ("OpenAI（需 API 密钥）", "openai"),
        ("本地 Ollama（qwen2.5vl：识图+聊天/免密钥）", "ollama"),
    ]

    def __init__(self, parent=None, edit_model=None):
        super().__init__(parent)
        self.edit_model = edit_model or {}
        self.setWindowTitle("编辑模型" if edit_model else "添加模型")
        self.resize(480, 380)
        self.fields = {}
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 15)
        layout.setSpacing(12)

        def add_field(label_text, key, default="", echo=None, width=300):
            row = QHBoxLayout()
            lab = QLabel(label_text)
            lab.setFixedWidth(92)
            lab.setStyleSheet("font-size: 20px; color:#555;")
            inp = QLineEdit(default)
            inp.setFixedWidth(width)
            if echo:
                inp.setEchoMode(echo)
            row.addWidget(lab)
            row.addWidget(inp)
            row.addStretch()
            layout.addLayout(row)
            self.fields[key] = inp

        add_field("名称", "name", self.edit_model.get("name", ""))
        add_field("模型名称", "model", self.edit_model.get("model", ""))


        prov_row = QHBoxLayout()
        plab = QLabel("服务商")
        plab.setFixedWidth(92)
        plab.setStyleSheet("font-size:20px; color:#555;")
        self.prov_combo = QComboBox()
        self.prov_combo.setFixedWidth(300)
        for label, key in self.PRESET_LABELS:
            self.prov_combo.addItem(label, key)
        self.prov_combo.currentTextChanged.connect(self._on_preset_changed)
        prov_row.addWidget(plab)
        prov_row.addWidget(self.prov_combo)
        prov_row.addStretch()
        layout.addLayout(prov_row)


        key_hint = QLabel(
            "说明：云端模型（DeepSeek / 通义千问 / OpenAI）必须填 API 密钥，"
            "相当于账号密码，没有就接不上；本地模型（Ollama）不用密钥，"
            "但你要先在自己电脑上把模型跑起来（开着本地服务）才能连。"
        )
        key_hint.setWordWrap(True)
        key_hint.setStyleSheet("color: #888; font-size: 14px; padding: 2px 0 2px 92px;")
        layout.addWidget(key_hint)

        add_field("API 地址", "base_url", self.edit_model.get("base_url", ""))
        add_field("API 密钥（云端必填）", "api_key", self.edit_model.get("api_key", ""),
                  echo=QLineEdit.Password)


        local_row = QHBoxLayout()
        self.local_checkbox = QCheckBox("本机 / 内网运行（不用密钥）")
        self.local_checkbox.setChecked(self.edit_model.get("is_local", False))
        self.local_checkbox.setStyleSheet("font-size: 20px; color:#555;")
        local_row.addWidget(self.local_checkbox)
        local_row.addStretch()
        layout.addLayout(local_row)


        cap_hint = QLabel("若该模型自身已内置以下能力，请勾选；界面将不再启动对应的本地实现：")
        cap_hint.setWordWrap(True)
        cap_hint.setStyleSheet("color: #888; font-size: 14px; padding: 6px 0 2px 92px;")
        layout.addWidget(cap_hint)
        self.cap_checks = {}
        cap_labels = {
            "emotion": "情感/语气识别",
            "vision": "看图/屏幕理解",
            "tts": "语音合成(自带声音)",
            "asr": "语音识别(自带听音)",
        }
        cap_row = QHBoxLayout()
        cap_row.addSpacing(92)
        for cap, label in cap_labels.items():
            cb = QCheckBox(label)
            cb.setChecked(bool(self.edit_model.get("cap_" + cap, False)))
            cb.setStyleSheet("font-size: 18px; color:#555;")
            self.cap_checks[cap] = cb
            cap_row.addWidget(cb)
        cap_row.addStretch()
        layout.addLayout(cap_row)

        layout.addStretch()


        btn = QHBoxLayout()
        btn.addStretch()
        ok = QPushButton("保存")
        ok.setFixedWidth(90)
        ok.clicked.connect(self.accept)
        cancel = QPushButton("取消")
        cancel.setFixedWidth(90)
        cancel.clicked.connect(self.reject)
        btn.addWidget(ok)
        btn.addWidget(cancel)
        layout.addLayout(btn)


        cur_key = self.edit_model.get("preset_key", "")
        cur_url = self.edit_model.get("base_url", "")
        target_index = 0
        for i in range(self.prov_combo.count()):
            key = self.prov_combo.itemData(i)
            if key == cur_key or (not cur_key and get_preset_default(key).get("base_url") == cur_url):
                target_index = i
                break
        self.prov_combo.setCurrentIndex(target_index)

        self._on_preset_changed(self.prov_combo.currentText())

    def _on_preset_changed(self, text):
        
        key = self.prov_combo.currentData()
        cfg = get_preset_default(key) if key else AI_MODEL_PRESETS["custom"]

        url_in = self.fields["base_url"].text().strip()
        model_in = self.fields["model"].text().strip()
        preset_url = cfg.get("base_url", "")
        preset_model = cfg.get("model", "")

        if not url_in and preset_url:
            self.fields["base_url"].setText(preset_url)
        if not model_in and preset_model:
            self.fields["model"].setText(preset_model)
        self.local_checkbox.setChecked(cfg.get("is_local", False))

    def accept(self):
        if not self.fields["name"].text().strip():
            QMessageBox.warning(self, "提示", "请填写模型名称")
            return
        super().accept()

    def get_data(self):
        key = self.prov_combo.currentData() or "custom"
        preset = get_preset_default(key)
        data = {
            "name": self.fields["name"].text().strip(),
            "base_url": self.fields["base_url"].text().strip().rstrip('/'),
            "api_key": self.fields["api_key"].text().strip(),
            "model": self.fields["model"].text().strip(),
            "is_local": self.local_checkbox.isChecked(),
            "preset_key": key,
        }

        for cap, cb in self.cap_checks.items():
            data["cap_" + cap] = cb.isChecked()
        return data


class SettingsDialog(QDialog):
    

    local_launch_done = pyqtSignal(bool, str)

    def __init__(self, parent=None, speech_engine=None):
        super().__init__(parent)
        self.speech_engine = speech_engine
        self.selected_image_path = ""
        self.color1 = "#667eea"
        self.color2 = "#764ba2"
        self._last_launch_svc = ""
        self._last_launch_discovered = []
        self.local_launch_done.connect(self._on_local_launch_done)
        self.setWindowTitle("设置")
        self.setMinimumSize(100, 500)
        self.resize(1500, 1080)
        self.setup_ui()
        self.load_settings()

        self._apply_model_caps_to_ui()

    def showEvent(self, event):
        
        super().showEvent(event)
        try:
            if hasattr(self, "voice_list"):
                self.refresh_voice_list()
        except Exception as e:
            print("[设置] showEvent 刷新音色列表失败:", e)

    def resizeEvent(self, event):
        
        super().resizeEvent(event)
        self.adjust_font_sizes()
    
    def adjust_font_sizes(self):
        

        base_width = 700
        scale = min(self.width() / base_width, 1.5)
        scale = max(scale, 0.8)
        

        base_font_size = 14
        scaled_size = int(base_font_size * scale)
        

        self.setStyleSheet(f"""
            QDialog {{
                background-color: #f5f5f5;
            }}
            QListWidget {{
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                outline: none;
            }}
            QListWidget::item {{
                padding: {int(15 * scale)}px {int(20 * scale)}px;
                border-bottom: 1px solid #f0f0f0;
                font-size: {int(13 * scale)}px;
            }}
            QListWidget::item:selected {{
                background-color: #667eea;
                color: white;
            }}
            QListWidget::item:hover:!selected {{
                background-color: #f0f0ff;
            }}
            QCheckBox {{
                spacing: 8px;
                font-size: {int(15 * scale)}px;
                font-weight: bold;
            }}
            QCheckBox::indicator {{
                width: {int(18 * scale)}px;
                height: {int(18 * scale)}px;
            }}
            QSlider::groove:horizontal {{
                height: {int(8 * scale)}px;
                background: #e0e0e0;
                border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                width: {int(18 * scale)}px;
                margin: -5px 0;
                background: #667eea;
                border-radius: 9px;
            }}
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white;
                border: none;
                border-radius: 5px;
                padding: {int(8 * scale)}px {int(25 * scale)}px;
                font-weight: bold;
                font-size: {int(15 * scale)}px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #5a7fd6, stop:1 #693d96);
            }}
            QLabel {{
                font-size: {int(15 * scale)}px;
                font-weight: bold;
            }}
            QRadioButton {{
                font-size: {int(15 * scale)}px;
                font-weight: bold;
            }}
            QComboBox {{
                padding: {int(8 * scale)}px {int(12 * scale)}px;
                font-size: {int(15 * scale)}px;
                font-weight: bold;
            }}
        """)
        

        if hasattr(self, 'detail_title'):
            title_size = int(15 * scale)
            self.detail_title.setFont(QFont("Microsoft YaHei", title_size, QFont.Bold))

    def _create_cap_yield_group(self, layout):
        
        group = QGroupBox("本地感官 · 能力让位")
        group.setStyleSheet("""
            QGroupBox {
                font-size: 14px; font-weight: bold; color: #444;
                border: 1px solid #e0e0e0; border-radius: 8px;
                margin-top: 10px; padding-top: 8px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }
        """)
        gl = QVBoxLayout(group)
        gl.setSpacing(6)

        self.cap_yield_rows = {}
        for key, name in (("tts", "语音朗读"), ("emotion", "情感语调"), ("asr", "语音听写")):
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(8)
            name_lbl = QLabel(name)
            name_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")
            rl.addWidget(name_lbl)
            rl.addStretch()
            status_lbl = QLabel("")
            status_lbl.setStyleSheet("font-size: 13px; font-weight: bold;")
            rl.addWidget(status_lbl)
            gl.addWidget(row)
            self.cap_yield_rows[key] = (name_lbl, status_lbl)

        tip = QLabel("模型自带某项能力时，界面本地实现自动让位（灰显）；"
                     "模型不带时由本机内置实现顶上（绿色）。视觉/听觉能力始终可用。")
        tip.setStyleSheet("color: #888; font-size: 12px;")
        tip.setWordWrap(True)
        gl.addWidget(tip)

        layout.addWidget(group)
        self._refresh_cap_yield_labels()

    def _refresh_cap_yield_labels(self):
        
        rows = getattr(self, "cap_yield_rows", None)
        if not rows:
            return
        caps = getattr(getattr(self, "parent", None), "model_caps", None) or {}
        for key, (name_lbl, status_lbl) in rows.items():
            in_model = bool(caps.get(key))
            if in_model:
                name_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #999;")
                status_lbl.setText("⊘ 模型自带 · 已让位")
                status_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #999;")
            else:
                name_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")
                status_lbl.setText("✓ 本地可用")
                status_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #52c41a;")

    def _apply_model_caps_to_ui(self):
        
        caps = getattr(getattr(self, "parent", None), "model_caps", None) or {}
        tts_in_model = bool(caps.get("tts"))
        vision = bool(caps.get("vision"))




        voice_widgets = [
            getattr(self, "voice_checkbox", None),
            getattr(self, "speed_slider", None),
            getattr(self, "volume_slider", None),
            getattr(self, "seamless_read_checkbox", None),
        ]
        for w in voice_widgets:
            if w is not None:
                w.setEnabled(not tts_in_model)
        vc = getattr(self, "voice_checkbox", None)
        if vc is not None:
            vc.setToolTip("当前模型自带语音输出，本地朗读已让位，无需本机 TTS"
                          if tts_in_model else "")


        sn = getattr(self, "screen_narrate_checkbox", None)
        if sn is not None:
            sn.setEnabled(True)
            sn.setToolTip("开启后，屏幕监控时 AI 会把对画面的理解朗读出来"
                          if vision
                          else "当前模型不支持看图，画面会经界面内置视觉模型理解后再朗读")


        self._refresh_cap_yield_labels()

    def setup_ui(self):
        
        self.setStyleSheet("""
            QDialog {
                background-color: #f5f5f5;
            }
            QListWidget {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                outline: none;
            }
            QListWidget::item {
                padding: 15px 20px;
                border-bottom: 1px solid #f0f0f0;
            }
            QListWidget::item:selected {
                background-color: #667eea;
                color: white;
            }
            QListWidget::item:hover:!selected {
                background-color: #f0f0ff;
            }
            QCheckBox {
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QSlider::groove:horizontal {
                height: 8px;
                background: #e0e0e0;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                width: 18px;
                margin: -5px 0;
                background: #667eea;
                border-radius: 9px;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 25px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #5a7fd6, stop:1 #693d96);
            }
        """)
        

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        

        left_panel = QWidget()
        left_panel.setFixedWidth(160)
        left_panel.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #f8f9fa, stop:1 #f0f0f0);
                border-right: 1px solid rgba(102, 126, 234, 0.2);
            }
        """)
        
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(12, 20, 12, 20)
        left_layout.setSpacing(8)
        

        title_label = QLabel("设置")
        title_label.setFont(QFont("Microsoft YaHei", 23, QFont.Bold))
        title_label.setStyleSheet("color: #667eea; padding: 8px 5px; letter-spacing: 2px;")
        title_label.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(title_label)
        

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 transparent, stop:0.5 #667eea, stop:1 transparent); max-height: 1px;")
        left_layout.addWidget(sep)
        
        left_layout.addSpacing(15)
        

        self.category_list = QListWidget()
        self.category_list.addItem("⚙️  通用")
        self.category_list.addItem("🔊  语音设置")
        self.category_list.addItem("🖥️  显示设置")
        self.category_list.addItem("🤖  AI 模型")
        self.category_list.addItem("🛡️  模型权限")
        self.category_list.setCurrentRow(0)
        self.category_list.currentRowChanged.connect(self.on_category_changed)
        self.category_list.setStyleSheet("""
            QListWidget {
                background-color: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item {
                padding: 12px 8px;
                border-radius: 8px;
                margin: 2px 0;
                color: #555;
                font-size: 23px;
            }
            QListWidget::item:hover {
                background-color: rgba(102, 126, 234, 0.08);
                color: #667eea;
            }
            QListWidget::item:selected {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(102, 126, 234, 0.15), stop:1 rgba(118, 75, 162, 0.15));
                color: #667eea;
                font-weight: bold;
            }
        """)
        left_layout.addWidget(self.category_list)
        
        left_layout.addStretch()
        
        main_layout.addWidget(left_panel)
        

        right_panel = QWidget()
        right_panel.setStyleSheet("background-color: white;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(20, 20, 20, 15)
        

        self.detail_title = QLabel("通用")
        self.detail_title.setFont(QFont("Microsoft YaHei", 23, QFont.Bold))
        self.detail_title.setStyleSheet("color: #667eea; padding-bottom: 10px;")
        right_layout.addWidget(self.detail_title)
        

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background-color: #e0e0e0;")
        separator.setFixedHeight(1)
        right_layout.addWidget(separator)
        
        right_layout.addSpacing(15)
        

        self.stack_widget = QWidget()
        self.stack_layout = QVBoxLayout(self.stack_widget)
        self.stack_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.stack_widget)
        

        self.general_page = self.create_general_page()
        self.voice_page = self.create_voice_page()
        self.display_page = self.create_display_page()
        self.ai_model_page = self.create_ai_model_page()
        self.permission_page = self.create_permission_page()

        self.stack_layout.addWidget(self.general_page)
        self.stack_layout.addWidget(self.voice_page)
        self.stack_layout.addWidget(self.display_page)
        self.stack_layout.addWidget(self.ai_model_page)
        self.stack_layout.addWidget(self.permission_page)


        self.voice_page.hide()
        self.display_page.hide()
        self.ai_model_page.hide()
        self.permission_page.hide()
        
        right_layout.addStretch()
        

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)
        
        right_layout.addLayout(button_layout)
        
        main_layout.addWidget(right_panel)
        

        self.adjust_font_sizes()
    
    def create_general_page(self):
        
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)


        bg_type_group = QWidget()
        bg_type_layout = QVBoxLayout(bg_type_group)
        bg_type_layout.setContentsMargins(0, 0, 0, 0)
        bg_type_layout.setSpacing(10)

        bg_type_title = QLabel("背景类型")
        bg_type_title.setStyleSheet("color: #666; font-weight: bold;")
        bg_type_layout.addWidget(bg_type_title)

        self.bg_type_group = QButtonGroup(self)

        self.bg_default_radio = QRadioButton("颜色")
        self.bg_image_radio = QRadioButton("背景图片")
        self.bg_default_radio.setChecked(True)

        self.bg_type_group.addButton(self.bg_default_radio, 0)
        self.bg_type_group.addButton(self.bg_image_radio, 1)

        self.bg_default_radio.setStyleSheet("font-size: 15px; font-weight: bold;")
        self.bg_image_radio.setStyleSheet("font-size: 15px; font-weight: bold;")

        bg_type_layout.addWidget(self.bg_default_radio)
        bg_type_layout.addWidget(self.bg_image_radio)

        self.bg_default_radio.toggled.connect(self.on_bg_type_changed)

        layout.addWidget(bg_type_group)


        self.color_settings = QWidget()
        color_layout = QVBoxLayout(self.color_settings)
        color_layout.setContentsMargins(0, 0, 0, 0)
        color_layout.setSpacing(15)


        color1_group = QWidget()
        color1_layout = QHBoxLayout(color1_group)
        color1_layout.setContentsMargins(0, 0, 0, 0)

        color1_label = QLabel("渐变起始色：")
        color1_label.setStyleSheet("color: #666;")
        self.color1_preview = QLabel()
        self.color1_preview.setFixedSize(40, 40)
        self.color1_preview.setStyleSheet("background-color: #667eea; border: 2px solid #999; border-radius: 5px;")
        self.color1_preview.setToolTip("点击预览框选择颜色")
        self.color1_preview.setCursor(Qt.PointingHandCursor)

        self.color1_preview.mousePressEvent = lambda event: self.choose_color(1)

        self.color1_btn = QPushButton("选择颜色")
        self.color1_btn.setFixedWidth(80)
        self.color1_btn.clicked.connect(lambda: self.choose_color(1))

        color1_layout.addWidget(color1_label)
        color1_layout.addSpacing(10)
        color1_layout.addWidget(self.color1_preview)
        color1_layout.addSpacing(10)
        color1_layout.addWidget(self.color1_btn)
        color1_layout.addStretch()

        color_layout.addWidget(color1_group)


        color2_group = QWidget()
        color2_layout = QHBoxLayout(color2_group)
        color2_layout.setContentsMargins(0, 0, 0, 0)

        color2_label = QLabel("渐变结束色：")
        color2_label.setStyleSheet("color: #666;")
        self.color2_preview = QLabel()
        self.color2_preview.setFixedSize(40, 40)
        self.color2_preview.setStyleSheet("background-color: #764ba2; border: 2px solid #999; border-radius: 5px;")
        self.color2_preview.setToolTip("点击预览框选择颜色")
        self.color2_preview.setCursor(Qt.PointingHandCursor)

        self.color2_preview.mousePressEvent = lambda event: self.choose_color(2)

        self.color2_btn = QPushButton("选择颜色")
        self.color2_btn.setFixedWidth(80)
        self.color2_btn.clicked.connect(lambda: self.choose_color(2))

        color2_layout.addWidget(color2_label)
        color2_layout.addSpacing(10)
        color2_layout.addWidget(self.color2_preview)
        color2_layout.addSpacing(10)
        color2_layout.addWidget(self.color2_btn)
        color2_layout.addStretch()

        color_layout.addWidget(color2_group)

        layout.addWidget(self.color_settings)


        self.image_settings = QWidget()
        image_layout = QVBoxLayout(self.image_settings)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.setSpacing(15)


        image_select_group = QWidget()
        image_select_layout = QVBoxLayout(image_select_group)
        image_select_layout.setContentsMargins(0, 0, 0, 0)
        image_select_layout.setSpacing(10)

        image_label = QLabel("背景图片：")
        image_label.setStyleSheet("color: #666;")
        image_select_layout.addWidget(image_label)


        self.select_image_btn = QPushButton("📁 点击选择背景图片")
        self.select_image_btn.setFixedHeight(40)
        self.select_image_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #5a7fd6, stop:1 #693d96);
            }
        """)
        self.select_image_btn.clicked.connect(self.select_background_image)
        image_select_layout.addWidget(self.select_image_btn)


        self.image_path_label = QLabel("")
        self.image_path_label.setStyleSheet("color: #667eea; font-size: 13px; font-weight: bold;")
        self.image_path_label.setWordWrap(True)
        image_select_layout.addWidget(self.image_path_label)

        image_layout.addWidget(image_select_group)

        self.image_settings.hide()

        layout.addWidget(self.image_settings)

        layout.addStretch()
        return page
    
    def on_bg_type_changed(self):
        
        if self.bg_default_radio.isChecked():
            self.color_settings.show()
            self.image_settings.hide()
        else:
            self.color_settings.hide()
            self.image_settings.show()
        

        self.auto_save_and_apply()
    
    def choose_color(self, color_num):
        

        if color_num == 1:
            current_color = QColor(self.color1_preview.styleSheet().split("background-color:")[1].split(";")[0].strip())
        else:
            current_color = QColor(self.color2_preview.styleSheet().split("background-color:")[1].split(";")[0].strip())


        dialog = ChineseColorDialog(current_color, self)
        if dialog.exec_() == QDialog.Accepted:
            color = dialog.get_color()
            if color.isValid():
                color_hex = color.name()
                if color_num == 1:
                    self.color1_preview.setStyleSheet(f"background-color: {color_hex}; border: 2px solid #999; border-radius: 5px;")
                    self.color1 = color_hex
                else:
                    self.color2_preview.setStyleSheet(f"background-color: {color_hex}; border: 2px solid #999; border-radius: 5px;")
                    self.color2 = color_hex


                self.auto_save_and_apply()
    
    def select_background_image(self):
        

        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "选择背景图片", 
            "", 
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"
        )
        
        if file_path:

            self.image_path_label.setText(os.path.basename(file_path))
            self.image_path_label.setStyleSheet("color: #667eea; font-weight: bold;")
            self.image_path_label.setToolTip(file_path)
            self.selected_image_path = file_path
            print(f"已选择背景图片: {file_path}")
            

            self.auto_save_and_apply()
    
    def auto_save_and_apply(self):
        

        self.save_settings()
        

        if self.parent():
            self.parent().load_settings()
            self.parent().apply_background()
        

        print("设置已自动保存并应用")
    
    def _create_voice_backend_group(self, layout):
        
        try:
            backend = get_tts_backend()
        except Exception:
            backend = "openvoice"

        tts_group = QGroupBox("语音合成模式")
        tts_group.setStyleSheet("QGroupBox { font-weight: bold; color: #444; }")
        tts_layout = QVBoxLayout(tts_group)
        tts_layout.setSpacing(8)

        rb_ov = QRadioButton("OpenVoice（实时，速度最快；支持系统音色 + .pt 克隆音色）")
        rb_cv = QRadioButton("CosyVoice（零样本克隆·音色清晰独属·需本地参考音频，CPU 较慢）")
        rb_ov.setStyleSheet("font-size: 14px;")
        rb_cv.setStyleSheet("font-size: 14px;")
        rb_ov.setChecked(backend == "openvoice")
        rb_cv.setChecked(backend == "cosyvoice")

        self._rb_tts_ov = rb_ov
        self._rb_tts_cv = rb_cv

        def _on_backend_toggled(checked):
            if not checked:
                return
            sel = "cosyvoice" if rb_cv.isChecked() else "openvoice"
            try:
                if self.speech_engine:
                    self.speech_engine.set_tts_backend(sel)
                else:
                    set_tts_backend(sel)
            except Exception as e:
                print("切换 TTS 后端失败:", e)
                return

            self._restore_voice_for_backend(sel)

            main_win = self.parent()
            if main_win is not None:
                _sync_tts_backend_ui(main_win, sel)

        rb_ov.toggled.connect(_on_backend_toggled)
        rb_cv.toggled.connect(_on_backend_toggled)



        tts_layout.addWidget(rb_ov)
        tts_layout.addWidget(rb_cv)
        tip = QLabel("切换模式后，下方音色列表只显示当前模式支持的音色；另一个模式的音色自动隐藏。")
        tip.setStyleSheet("color: #888; font-size: 12px;")
        tip.setWordWrap(True)
        tts_layout.addWidget(tip)
        layout.addWidget(tts_group)

    def _restore_voice_for_backend(self, backend):
        
        try:
            sel = self.load_selected_voice_for(backend)
            if sel:
                kind = sel.get("kind")
                name = sel.get("name", "")

                if kind == "cloned":
                    match_kind = "cloned_openvoice"
                elif kind == "cosyvoice":
                    match_kind = "cloned_cosyvoice"
                else:
                    match_kind = kind


                self.refresh_voice_list()


                items = getattr(self, "_voice_items", []) or []
                target_index = None
                for i, it in enumerate(items):
                    if not it:
                        continue
                    if it.get("kind") == match_kind and it.get("name") == name:
                        target_index = i
                        break

                if target_index is None and name:
                    for i, it in enumerate(items):
                        if not it:
                            continue
                        if it.get("kind") in ("cloned_openvoice", "cloned_cosyvoice") and \
                                it.get("name") == name:
                            target_index = i
                            break

                if target_index is not None and target_index < self.voice_list.count():
                    self.voice_list.setCurrentRow(target_index)
                    self._apply_voice_selection(self._voice_items[target_index])
                else:

                    self._reset_selected_voice_to_system()
            else:

                self.refresh_voice_list()
                self._reset_selected_voice_to_system()
        except Exception as e:
            print("恢复 %s 音色失败:" % backend, e)
            import traceback
            traceback.print_exc()
            try:
                self.refresh_voice_list()
            except Exception:
                pass

    def create_voice_page(self):
        
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)


        self.voice_checkbox = QCheckBox("启用语音朗读")
        self.voice_checkbox.setChecked(True)
        self.voice_checkbox.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(self.voice_checkbox)


        self._create_cap_yield_group(layout)


        self._create_voice_backend_group(layout)


        voice_group = QWidget()
        voice_layout = QVBoxLayout(voice_group)
        voice_layout.setContentsMargins(0, 0, 0, 0)
        voice_layout.setSpacing(12)

        voice_title = QLabel("音色选择")
        voice_title.setStyleSheet("color: #666; font-weight: bold;")
        voice_layout.addWidget(voice_title)


        self.voice_trigger_btn = QPushButton("🎙️ 点击选择音色…")
        self.voice_trigger_btn.setMinimumHeight(40)
        self.voice_trigger_btn.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding: 8px 14px;
                border: 1px solid #ccc;
                border-radius: 6px;
                background: white;
                font-size: 15px;
                font-weight: bold;
                color: #333;
            }
            QPushButton:hover { border-color: #667eea; }
            QPushButton:pressed { background: #f5f5ff; }
        """)
        self.voice_trigger_btn.clicked.connect(self._toggle_voice_popup)
        voice_layout.addWidget(self.voice_trigger_btn)


        self._create_voice_popup()





        voice_file_widget = QWidget()
        voice_file_layout = QHBoxLayout(voice_file_widget)
        voice_file_layout.setContentsMargins(0, 0, 0, 0)

        self.select_voice_btn = QPushButton("📁 从文件选择音色")
        self.select_voice_btn.setFixedHeight(36)
        self.select_voice_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #5a7fd6, stop:1 #693d96);
            }
        """)
        self.select_voice_btn.clicked.connect(self.select_voice_file)
        voice_file_layout.addWidget(self.select_voice_btn)

        voice_layout.addWidget(voice_file_widget)


        cache_row = QWidget()
        cache_row_layout = QHBoxLayout(cache_row)
        cache_row_layout.setContentsMargins(0, 0, 0, 0)
        cache_row_layout.setSpacing(8)
        self.clear_cache_btn = QPushButton("🧹 清空合成缓存（不影响音色）")
        self.clear_cache_btn.setFixedHeight(34)
        self.clear_cache_btn.setStyleSheet("""
            QPushButton {
                background: #eef0f7; color: #555; border: 1px solid #d6d9e6;
                border-radius: 5px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background: #e2e6f3; }
        """)
        self.clear_cache_btn.clicked.connect(self._clear_synth_cache)
        cache_row_layout.addWidget(self.clear_cache_btn)
        cache_row_layout.addStretch(1)
        voice_layout.addWidget(cache_row)


        self.current_voice_label = QLabel("当前音色：未选择")
        self.current_voice_label.setStyleSheet("color: #667eea; font-size: 13px; font-weight: bold;")
        voice_layout.addWidget(self.current_voice_label)


        voice_hint = QLabel(
            "提示：点击上方「选择音色」按钮会弹出浮层——系统音色直接点击选中，"
            "专属音色（克隆音色）左侧打勾后可批量删除。把音频 / 视频拖入主界面，"
            "会按当前 TTS 模式生成对应专属音色。\n"
            "「清空合成缓存」仅删除临时合成结果（md5 命名的 .wav），不影响任何音色与朗读，"
            "下次合成会自动重建。")
        voice_hint.setStyleSheet("color: #888; font-size: 12px; line-height: 1.5;")
        voice_hint.setWordWrap(True)
        voice_layout.addWidget(voice_hint)

        layout.addWidget(voice_group)


        speaker_group = QWidget()
        speaker_layout = QVBoxLayout(speaker_group)
        speaker_layout.setContentsMargins(0, 0, 0, 0)
        speaker_layout.setSpacing(8)

        speaker_title = QLabel("说话人识别（你的音色）")
        speaker_title.setStyleSheet("color: #666; font-weight: bold;")
        speaker_layout.addWidget(speaker_title)

        self.speaker_status_label = QLabel("尚未建档：多说几次话即可自动记录你的音色")
        self.speaker_status_label.setStyleSheet("color: #333; font-size: 13px; font-weight: bold;")
        speaker_layout.addWidget(self.speaker_status_label)

        speaker_btn = QPushButton("🔄 重新校准我的音色")
        speaker_btn.setFixedHeight(36)
        speaker_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white; border: none; border-radius: 5px;
                font-size: 14px; font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #5a7fd6, stop:1 #693d96);
            }
        """)
        speaker_btn.clicked.connect(self._reset_speaker_profile)
        speaker_layout.addWidget(speaker_btn)

        speaker_tip = QLabel(
            "系统会记住你的「底音 / 音色」，放视频或旁人说话时不会误当成你。"
            "若换麦克风或声音变化较大，点上面的按钮重新校准。")
        speaker_tip.setStyleSheet("color: #000000; font-size: 18px; font-weight: bold;")
        speaker_tip.setWordWrap(True)
        speaker_layout.addWidget(speaker_tip)

        layout.addWidget(speaker_group)


        memory_btn = QPushButton("🧠 编辑记忆库（根基 / 记忆 / 思考 / 情绪 / 人设）")
        memory_btn.setFixedHeight(36)
        memory_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #11998e, stop:1 #38ef7d);
                color: white; border: none; border-radius: 5px;
                font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0f8a7e, stop:1 #2fd86d); }
        """)
        memory_btn.clicked.connect(self._open_memory_editor)
        layout.addWidget(memory_btn)


        speed_group = QWidget()
        speed_layout = QVBoxLayout(speed_group)
        speed_layout.setContentsMargins(0, 0, 0, 0)
        speed_layout.setSpacing(8)

        speed_title = QLabel("语速")
        speed_title.setStyleSheet("color: #666; font-weight: bold;")
        speed_layout.addWidget(speed_title)

        speed_control = QWidget()
        speed_h_layout = QHBoxLayout(speed_control)
        speed_h_layout.setContentsMargins(0, 0, 0, 0)

        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(50, 300)
        self.speed_slider.setValue(150)
        self.speed_slider.setMinimumWidth(300)
        self.speed_value = QLabel("150")
        self.speed_value.setMinimumWidth(50)
        self.speed_value.setStyleSheet("color: #667eea; font-weight: bold;")

        speed_h_layout.addWidget(self.speed_slider)
        speed_h_layout.addWidget(self.speed_value)
        self.speed_slider.valueChanged.connect(lambda v: self.speed_value.setText(str(v)))

        speed_layout.addWidget(speed_control)
        layout.addWidget(speed_group)


        volume_group = QWidget()
        volume_layout = QVBoxLayout(volume_group)
        volume_layout.setContentsMargins(0, 0, 0, 0)
        volume_layout.setSpacing(8)

        volume_title = QLabel("音量")
        volume_title.setStyleSheet("color: #666; font-weight: bold;")
        volume_layout.addWidget(volume_title)

        volume_control = QWidget()
        volume_h_layout = QHBoxLayout(volume_control)
        volume_h_layout.setContentsMargins(0, 0, 0, 0)

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setMinimumWidth(300)
        self.volume_value = QLabel("100%")
        self.volume_value.setMinimumWidth(50)
        self.volume_value.setStyleSheet("color: #667eea; font-weight: bold;")

        volume_h_layout.addWidget(self.volume_slider)
        volume_h_layout.addWidget(self.volume_value)
        self.volume_slider.valueChanged.connect(lambda v: self.volume_value.setText(f"{v}%"))

        volume_layout.addWidget(volume_control)
        layout.addWidget(volume_group)


        self.refresh_voice_list()

        layout.addStretch()
        return page

    def _refresh_speaker_status(self):
        
        try:
            st = speaker_profile_status()
        except Exception:
            st = None
        if not st:
            self.speaker_status_label.setText(
                "尚未建档：多说几次话即可自动记录你的音色")
        else:
            cnt, f0 = st
            extra = "（底音约 %.0fHz）" % f0 if f0 else ""
            if cnt < 3:
                self.speaker_status_label.setText(
                    "校准中：已采集 %d/3 次%s" % (cnt, extra))
            else:
                self.speaker_status_label.setText(
                    "已记录你的音色：已采集 %d 次%s" % (cnt, extra))

    def _reset_speaker_profile(self):
        
        try:
            ok = reset_speaker_profile()
        except Exception as e:
            QMessageBox.warning(self, "校准失败", "无法重置音色档案：%s" % e)
            return
        if ok:
            self._refresh_speaker_status()
            QMessageBox.information(
                self, "已重置",
                "已清空你的音色档案。下次开始说话时会重新记录，"
                "前几次为校准期，请正常对话即可。")
        else:
            QMessageBox.warning(self, "重置失败", "未找到音色档案，无需重置。")

    def _open_memory_editor(self):
        
        dlg = MemoryEditorDialog(self)
        dlg.exec_()

    def _create_voice_popup(self):
        
        pop = QWidget(self, Qt.Popup | Qt.FramelessWindowHint)
        pop.setAttribute(Qt.WA_TranslucentBackground, True)
        self.voice_popup = pop


        container = QWidget(pop)
        container.setObjectName("voice_popup_container")
        container.setStyleSheet(
            "background: white; border-radius: 10px; "
            "border: 1px solid rgba(0,0,0,0.08);")
        shadow = QGraphicsDropShadowEffect(container)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 110))
        container.setGraphicsEffect(shadow)

        cl = QVBoxLayout(pop)
        cl.setContentsMargins(10, 10, 10, 10)
        cl.addWidget(container)

        vlay = QVBoxLayout(container)
        vlay.setContentsMargins(10, 10, 10, 10)
        vlay.setSpacing(8)

        title = QLabel("音色选择")
        title.setStyleSheet("color:#666; font-weight:bold; font-size:14px;")
        vlay.addWidget(title)

        self.voice_list = QListWidget(container)
        self.voice_list.setSelectionMode(QListWidget.SingleSelection)
        self.voice_list.setMinimumHeight(120)
        self.voice_list.setMaximumHeight(280)
        self.voice_list.setStyleSheet("""
            QListWidget {
                background: white;
                border: 1px solid #eee;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                outline: none;
            }
            QListWidget::item {
                padding: 7px 8px;
                min-height: 32px;
                border-bottom: 1px solid #f3f3f3;
                color: #333;
            }
            QListWidget::item:hover { background-color: rgba(102,126,234,0.08); }
            QListWidget::item:selected {
                background-color: rgba(102,126,234,0.16);
                color: #667eea;
                border-left: 4px solid #667eea;
            }
            QListWidget::item:disabled { color: #999; }
        """)
        self.voice_list.currentRowChanged.connect(self.on_voice_row_changed)
        vlay.addWidget(self.voice_list)


        btn_row = QWidget(container)
        btn_row_layout = QHBoxLayout(btn_row)
        btn_row_layout.setContentsMargins(0, 0, 0, 0)
        btn_row_layout.setSpacing(10)

        self.voice_select_all_btn = QPushButton("☐ 全选")
        self.voice_select_all_btn.setFixedHeight(30)
        self.voice_select_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #e6f0ff; color: #1d39c4;
                border: 1px solid #adc6ff; border-radius: 5px;
                font-size: 13px; font-weight: bold; padding: 0 12px;
            }
            QPushButton:hover { background-color: #bae0ff; }
            QPushButton:disabled { background-color: #f5f5f5; color: #bbb; border-color: #d9d9d9; }
        """)
        self.voice_select_all_btn.clicked.connect(self._toggle_select_all_clones)
        btn_row_layout.addWidget(self.voice_select_all_btn)

        self.voice_delete_btn = QPushButton("🗑️ 删除选中")
        self.voice_delete_btn.setFixedHeight(30)
        self.voice_delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff4d4f; color: white; border: none;
                border-radius: 5px; font-size: 13px; font-weight: bold; padding: 0 12px;
            }
            QPushButton:hover { background-color: #ff7875; }
            QPushButton:disabled { background-color: #d9d9d9; color: #999; }
        """)
        self.voice_delete_btn.clicked.connect(self._delete_selected_clone_voices)
        btn_row_layout.addWidget(self.voice_delete_btn)
        btn_row_layout.addStretch()
        vlay.addWidget(btn_row)

        pop.hide()

    def _toggle_voice_popup(self):
        
        if self.voice_popup.isVisible():
            self.voice_popup.hide()
        else:
            self._show_voice_popup()

    def _show_voice_popup(self):
        
        try:
            self.refresh_voice_list()
        except Exception as e:
            print("[音色浮层] 刷新失败:", e)
        self._position_voice_popup()
        self.voice_popup.show()

    def _position_voice_popup(self):
        
        btn = self.voice_trigger_btn
        pw = max(btn.width(), 320)
        self.voice_popup.setFixedWidth(pw)
        self.voice_popup.adjustSize()
        ph = self.voice_popup.height()
        global_pos = btn.mapToGlobal(btn.rect().bottomLeft())
        try:
            screen = QApplication.screenAt(global_pos)
        except Exception:
            screen = None
        if not screen:
            try:
                screen = QApplication.primaryScreen()
            except Exception:
                screen = None
        if screen:
            avail = screen.availableGeometry()
        else:
            avail = QApplication.desktop().availableGeometry()
        if global_pos.y() + ph > avail.bottom():
            top = btn.mapToGlobal(btn.rect().topLeft()).y()
            global_pos.setY(top - ph)
        if global_pos.x() + pw > avail.right():
            global_pos.setX(avail.right() - pw)
        self.voice_popup.move(global_pos)

    def on_voice_row_changed(self, row):
        
        items = getattr(self, "_voice_items", None)
        if not items or row < 0 or row >= len(items):
            return
        item = items[row]
        if not item:
            return
        self._apply_voice_selection(item)

    def refresh_voice_list(self):
        
        try:
            print("[音色列表] 开始刷新...")
            try:
                backend = get_tts_backend()
            except Exception:
                backend = "openvoice"
            print("[音色列表] 当前后端:", backend)


            sys_voices = []
            voices_path = self.get_voices_path()
            if os.path.exists(voices_path):
                try:
                    with open(voices_path, 'r', encoding='utf-8') as f:
                        cfg = json.load(f)
                    sys_voices = cfg.get('voices', [])
                except Exception as e:
                    print("[音色列表] 读取 voices.json 失败:", e)
                    sys_voices = []
            print("[音色列表] 系统音色数量:", len(sys_voices))

            self.voice_list.blockSignals(True)
            self.voice_list.clear()
            self._voice_items = []
            self._clone_voice_items = []


            for v in sys_voices:
                name = v.get('name', '系统音色')
                vid = v.get('id')
                it = QListWidgetItem(name)
                it.setFlags(it.flags() & ~Qt.ItemIsUserCheckable)
                it.setData(Qt.UserRole, len(self._voice_items))
                self.voice_list.addItem(it)
                self._voice_items.append({"kind": "system", "id": vid, "name": name})


            clone_items = []
            if backend == "openvoice":
                from voice_clone import load_cloned_voices
                clones = load_cloned_voices() or []
                print("[音色列表] OpenVoice 克隆数量:", len(clones))
                for v in clones:
                    name = v.get('name', '克隆音色')
                    clone_items.append({
                        "kind": "cloned_openvoice",
                        "name": name,
                        "se_path": v.get("se_path"),
                        "lang": v.get("lang", "zh"),
                        "label": "🎙️ " + name,
                    })
            else:  # cosyvoice
                from cosyvoice_tts import load_tts_config
                cfg = load_tts_config()
                prompt_wav = cfg.get("cosyvoice_prompt_wav")
                print("[音色列表] CosyVoice prompt_wav:", prompt_wav)

                _bad = (not prompt_wav or not os.path.exists(prompt_wav)
                        or "openvoice_cache" in prompt_wav
                        or "cosyvoice_cache" in prompt_wav
                        or re.fullmatch(r"[0-9a-fA-F]{32}",
                                        os.path.splitext(os.path.basename(prompt_wav))[0] or ""))
                if not _bad:
                    name = os.path.splitext(os.path.basename(prompt_wav))[0]
                    clone_items.append({
                        "kind": "cloned_cosyvoice",
                        "name": name,
                        "prompt_wav": prompt_wav,
                        "prompt_text": cfg.get("cosyvoice_prompt_text", ""),
                        "label": "🎙️ " + name,
                    })

            if clone_items:
                sep = QListWidgetItem("—— 专属音色 ——")
                sep.setFlags(sep.flags() & ~Qt.ItemIsSelectable & ~Qt.ItemIsUserCheckable)
                sep.setForeground(QColor("#999999"))
                sep.setData(Qt.UserRole, len(self._voice_items))
                self.voice_list.addItem(sep)
                self._voice_items.append(None)
                for d in clone_items:
                    it = QListWidgetItem(d["label"])
                    it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                    it.setCheckState(Qt.Unchecked)
                    it.setData(Qt.UserRole, len(self._voice_items))
                    self.voice_list.addItem(it)
                    self._voice_items.append(d)
                    self._clone_voice_items.append(d)

            print("[音色列表] 专属音色数量:", len(clone_items),
                  "系统音色数量:", len(sys_voices),
                  "最终列表项数:", self.voice_list.count())


            sel = self.load_selected_voice()
            target_index = None
            if sel:
                saved_backend = sel.get("backend")
                if not saved_backend:

                    saved_backend = backend
                if saved_backend == backend:
                    match_kind = sel.get("kind")

                    if match_kind == "cloned":
                        match_kind = "cloned_openvoice"
                    elif match_kind == "cosyvoice":
                        match_kind = "cloned_cosyvoice"
                    sel_name = sel.get("name")
                    for i, it in enumerate(self._voice_items):
                        if not it:
                            continue
                        if it.get("kind") == match_kind and it.get("name") == sel_name:
                            target_index = i
                            break

                    if target_index is None and sel_name:
                        for i, it in enumerate(self._voice_items):
                            if not it:
                                continue
                            if it.get("kind") in ("cloned_openvoice", "cloned_cosyvoice") \
                                    and it.get("name") == sel_name:
                                target_index = i
                                break


            if target_index is None and self.voice_list.count() > 0:
                target_index = 0

            if target_index is not None and target_index < self.voice_list.count():
                self.voice_list.setCurrentRow(target_index)
                self._apply_voice_selection(self._voice_items[target_index])
            self.voice_list.blockSignals(False)


            self._refresh_clone_manage_ui()
            print("[音色列表] 刷新完成")
        except Exception as e:
            print("刷新音色列表失败: %s" % e)
            import traceback
            traceback.print_exc()
            try:
                self.voice_list.blockSignals(False)
            except Exception:
                pass

    def _apply_voice_selection(self, item):
        
        try:
            if not item or item.get("kind") is None:
                return

            se = self.speech_engine
            kind = item.get("kind")
            name = item.get("name", "未知音色")

            if kind == "system":
                vid = item.get("id")
                if se:
                    if vid:
                        se.zh_voice_id = vid
                        se.en_voice_id = vid
                    se.set_active_voice({"type": "system", "id": vid})
                self.current_voice_label.setText("当前音色：%s" % name)
                self.current_voice_label.setStyleSheet(
                    "color: #667eea; font-size: 13px; font-weight: bold;")
                self.save_selected_voice({
                    "kind": "system", "id": vid, "name": name,
                    "backend": get_tts_backend()})

            elif kind == "cloned_openvoice":
                se_path = item.get("se_path")
                if se:
                    se.set_active_voice({
                        "type": "cloned",
                        "name": name,
                        "se_path": se_path,
                        "lang": item.get("lang", "zh"),
                    })
                self.current_voice_label.setText("当前音色：%s（OpenVoice 克隆）" % name)
                self.current_voice_label.setStyleSheet(
                    "color: #667eea; font-size: 13px; font-weight: bold;")
                self.save_selected_voice({
                    "kind": "cloned", "name": name, "backend": "openvoice"})

            elif kind == "cloned_cosyvoice":

                if get_tts_backend() != "cosyvoice":
                    set_tts_backend("cosyvoice")
                    if se:
                        se.set_tts_backend("cosyvoice")
                if se:
                    se.set_active_voice({
                        "type": "cosyvoice",
                        "name": name,
                        "prompt_wav": item.get("prompt_wav"),
                        "prompt_text": item.get("prompt_text", ""),
                    })
                self.current_voice_label.setText("当前音色：%s（CosyVoice 克隆）" % name)
                self.current_voice_label.setStyleSheet(
                    "color: #667eea; font-size: 13px; font-weight: bold;")
                self.save_selected_voice({
                    "kind": "cosyvoice", "name": name, "backend": "cosyvoice"})


            if hasattr(self, "voice_trigger_btn"):
                tag = "🎙️ " if kind != "system" else ""
                self.voice_trigger_btn.setText("%s%s" % (tag, name))

            print("已切换音色: %s (%s)" % (name, kind))
        except Exception as e:
            print("应用音色选择失败: %s" % e)
            import traceback
            traceback.print_exc()

    def _refresh_clone_manage_ui(self):
        
        try:
            has_clone = bool(getattr(self, "_clone_voice_items", []))
            if hasattr(self, "voice_delete_btn"):
                self.voice_delete_btn.setEnabled(has_clone)
            if hasattr(self, "voice_select_all_btn"):
                self.voice_select_all_btn.setEnabled(has_clone)
                self.voice_select_all_btn.setText("☐ 全选")
        except Exception as e:
            print("刷新专属音色管理区失败:", e)

    def _toggle_select_all_clones(self):
        
        try:
            count = self.voice_list.count()
            if count == 0:
                return
            total = checked = 0
            for i in range(count):
                it = self.voice_list.item(i)
                if it.flags() & Qt.ItemIsUserCheckable:
                    total += 1
                    if it.checkState() == Qt.Checked:
                        checked += 1
            all_checked = (total > 0 and checked == total)
            target = Qt.Unchecked if all_checked else Qt.Checked
            self.voice_list.blockSignals(True)
            for i in range(count):
                it = self.voice_list.item(i)
                if it.flags() & Qt.ItemIsUserCheckable:
                    it.setCheckState(target)
            self.voice_list.blockSignals(False)
            self.voice_select_all_btn.setText("☑ 全选" if target == Qt.Checked else "☐ 全选")
        except Exception as e:
            print("切换全选失败:", e)

    def _delete_selected_clone_voices(self):
        
        try:
            selected = []
            for i in range(self.voice_list.count()):
                it = self.voice_list.item(i)
                if it.checkState() == Qt.Checked:
                    idx = it.data(Qt.UserRole)
                    if isinstance(idx, int) and 0 <= idx < len(self._voice_items):
                        d = self._voice_items[idx]
                        if d and d.get("kind") in ("cloned_openvoice", "cloned_cosyvoice"):
                            selected.append(d)
            if not selected:
                QMessageBox.information(self, "提示", "请先勾选要删除的专属音色。")
                return

            names = "、".join(d.get("name", "?") for d in selected)
            reply = QMessageBox.question(
                self, "批量删除音色",
                "确定删除以下 %d 个专属音色并移入回收站吗？\n%s\n\n（系统音色不会被删除，删除后可随时从回收站恢复）"
                % (len(selected), names),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No)
            if reply != QMessageBox.Yes:
                return

            ok_count = 0
            fail_names = []
            deleted_names = set()
            for d in selected:
                kind = d.get("kind")
                name = d.get("name", "?")
                try:
                    if kind == "cloned_openvoice":
                        if self._delete_openvoice_clone(d, silent=True):
                            ok_count += 1
                            deleted_names.add(name)
                        else:
                            fail_names.append(name)
                    else:  # cloned_cosyvoice
                        if self._delete_cosyvoice_clone(d, silent=True):
                            ok_count += 1
                            deleted_names.add(name)
                        else:
                            fail_names.append(name)
                except Exception as e:
                    print("批量删除音色失败:", e)
                    fail_names.append(name)

            msg = "已删除 %d 个专属音色并移入回收站。" % ok_count
            if fail_names:
                msg += "\n以下删除失败（可能文件被占用）：%s" % "、".join(fail_names)
            QMessageBox.information(self, "批量删除完成", msg)


            try:
                sel = self.load_selected_voice()
                if sel and sel.get("name") in deleted_names \
                        and sel.get("kind") in ("cloned", "cloned_openvoice", "cosyvoice"):
                    self._reset_selected_voice_to_system()
            except Exception as e:
                print("删除后检查当前音色失败:", e)

            self.refresh_voice_list()
        except Exception as e:
            print("批量删除音色异常:", e)
            QMessageBox.warning(self, "错误", "批量删除过程中出现异常：%s" % e)

    def _send_to_recycle_bin(self, path):
        
        if not path or not os.path.exists(path):
            return False
        if os.name != "nt":
            return False
        try:
            import ctypes
            from ctypes.wintypes import HWND, UINT, LPCWSTR, BOOL, WORD

            class SHFILEOPSTRUCTW(ctypes.Structure):
                _fields_ = [
                    ("hwnd", HWND),
                    ("wFunc", UINT),
                    ("pFrom", LPCWSTR),
                    ("pTo", LPCWSTR),
                    ("fFlags", WORD),
                    ("fAnyOperationsAborted", BOOL),
                    ("hNameMappings", ctypes.c_void_p),
                    ("lpszProgressTitle", LPCWSTR),
                ]

            FO_DELETE = 0x0003
            FOF_ALLOWUNDO = 0x0040
            FOF_NOCONFIRMATION = 0x0010
            FOF_SILENT = 0x0004
            FOF_NOERRORUI = 0x0400

            s = SHFILEOPSTRUCTW()
            s.hwnd = None
            s.wFunc = FO_DELETE
            s.pFrom = str(path) + "\0\0"
            s.pTo = None
            s.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
            s.fAnyOperationsAborted = False
            s.hNameMappings = None
            s.lpszProgressTitle = None
            ret = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(s))
            return ret == 0
        except Exception as e:
            print("送回收站失败:", e)
            return False

    def _clear_cosyvoice_cache(self):
        
        try:
            from cosyvoice_tts import _app_base
            cache_dir = os.path.join(_app_base(), "cosyvoice_cache")
            if not os.path.isdir(cache_dir):
                return
            for fn in os.listdir(cache_dir):
                fp = os.path.join(cache_dir, fn)
                try:
                    if os.path.isfile(fp):
                        os.remove(fp)
                except Exception:
                    pass
        except Exception as e:
            print("清理合成缓存失败:", e)

    def _clear_synth_cache(self):
        
        try:
            from voice_clone import _app_base as _base
        except Exception:
            _base = None
        base = _base() if _base else os.path.dirname(os.path.abspath(__file__))
        cleared = 0
        for sub in ("openvoice_cache", "cosyvoice_cache"):
            d = os.path.join(base, sub)
            if not os.path.isdir(d):
                continue
            for fn in os.listdir(d):
                if not fn.endswith(".wav"):
                    continue
                fp = os.path.join(d, fn)
                try:
                    if os.path.isfile(fp):
                        os.remove(fp)
                        cleared += 1
                except Exception:
                    pass
        if cleared:
            QMessageBox.information(
                self, "缓存已清理",
                "已清理 %d 个合成缓存文件（md5 命名的临时 .wav，非音色）。\n"
                "下次合成会自动重建，不影响任何音色与朗读。" % cleared)
        else:
            QMessageBox.information(self, "缓存已清理", "当前没有需要清理的合成缓存文件。")

    def _get_first_system_voice(self):
        
        try:
            voices_path = self.get_voices_path()
            if os.path.exists(voices_path):
                with open(voices_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                voices = cfg.get('voices', [])
                if voices:
                    return voices[0]
        except Exception as e:
            print("读取系统音色失败:", e)
        return None

    def _reset_selected_voice_to_system(self):
        
        try:
            sys_voice = self._get_first_system_voice()
            vid = sys_voice.get('id') if sys_voice else None
            name = sys_voice.get('name', '系统音色') if sys_voice else '系统音色'
            self.save_selected_voice({"kind": "system", "id": vid, "name": name,
                                      "backend": "openvoice"})
            if self.speech_engine:
                if vid:
                    self.speech_engine.zh_voice_id = vid
                    self.speech_engine.en_voice_id = vid
                self.speech_engine.set_active_voice({"type": "system", "id": vid})
            self.current_voice_label.setText("当前音色：%s" % name)
            self.current_voice_label.setStyleSheet(
                "color: #667eea; font-size: 13px; font-weight: bold;")
            if hasattr(self, "voice_trigger_btn"):
                self.voice_trigger_btn.setText(name)
        except Exception as e:
            print("回退系统音色 UI 失败:", e)

    def _delete_openvoice_clone(self, item, silent=False):
        
        from voice_clone import load_cloned_voices, save_cloned_voices
        name = item.get("name")
        se_path = item.get("se_path")


        voices = [v for v in (load_cloned_voices() or [])
                  if v.get("name") != name or v.get("se_path") != se_path]
        save_cloned_voices(voices)


        ok = True
        if se_path and os.path.exists(se_path):
            ok = self._send_to_recycle_bin(se_path)
        if not ok:
            if not silent:
                QMessageBox.warning(self, "删除失败", "无法将音色文件移入回收站，请检查文件是否被占用。")
            return False


        if self.speech_engine:
            av = self.speech_engine.active_voice or {}
            if av.get("type") == "cloned" and av.get("name") == name:
                sys_voice = self._get_first_system_voice()
                sys_id = sys_voice.get('id') if sys_voice else self.speech_engine.zh_voice_id
                self.speech_engine.set_active_voice({"type": "system", "id": sys_id})



        cfg_path = self.get_config_path()
        try:
            cfg = {}
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
            sel = cfg.get('selected_voice') or {}
            if (sel.get('kind') in ('cloned', 'cloned_openvoice')
                    and sel.get('name') == name):
                sys_voice = self._get_first_system_voice()
                sys_id = sys_voice.get('id') if sys_voice else None
                sys_name = sys_voice.get('name', '系统音色') if sys_voice else '系统音色'
                cfg['selected_voice'] = {"kind": "system", "id": sys_id,
                                         "name": sys_name, "backend": "openvoice"}
                with open(cfg_path, 'w', encoding='utf-8') as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("回退系统音色配置失败:", e)

        if not silent:
            QMessageBox.information(self, "删除成功", "OpenVoice 专属音色「%s」已删除并移入回收站。" % name)
        return True

    def _delete_cosyvoice_clone(self, item, silent=False):
        
        from cosyvoice_tts import load_tts_config, save_tts_config
        cfg = load_tts_config()
        prompt_wav = cfg.get("cosyvoice_prompt_wav")
        if not prompt_wav or not os.path.exists(prompt_wav):
            self._refresh_clone_manage_ui()
            return False

        ok = self._send_to_recycle_bin(prompt_wav)
        if not ok:
            if not silent:
                QMessageBox.warning(self, "删除失败", "无法将音色文件移入回收站，请检查文件是否被占用。")
            return False

        cfg.pop("cosyvoice_prompt_wav", None)
        cfg.pop("cosyvoice_prompt_text", None)
        save_tts_config(cfg)


        try:
            cfg_path = self.get_config_path()
            s_cfg = {}
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    s_cfg = json.load(f)
            sel = s_cfg.get('selected_voice') or {}
            if sel.get('kind') == 'cosyvoice':
                sys_voice = self._get_first_system_voice()
                sys_id = sys_voice.get('id') if sys_voice else None
                sys_name = sys_voice.get('name', '系统音色') if sys_voice else '系统音色'
                s_cfg['selected_voice'] = {"kind": "system", "id": sys_id,
                                           "name": sys_name, "backend": "openvoice"}
                with open(cfg_path, 'w', encoding='utf-8') as f:
                    json.dump(s_cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("CosyVoice 删除后回退配置失败:", e)


        try:
            if self.speech_engine:
                sys_voice = self._get_first_system_voice()
                sys_id = sys_voice.get('id') if sys_voice else self.speech_engine.zh_voice_id
                self.speech_engine.set_active_voice({"type": "system", "id": sys_id})
        except Exception as e:
            print("CosyVoice 删除后切回系统音色失败:", e)


        self._clear_cosyvoice_cache()


        try:
            set_tts_backend("openvoice")
            if self.speech_engine:
                self.speech_engine.set_tts_backend("openvoice")
        except Exception as e:
            print("切回系统音色失败:", e)

        if not silent:
            QMessageBox.information(self, "删除成功", "CosyVoice 专属音色已删除并移入回收站，已切换为系统音色。")
        return True

    def load_selected_voice(self):
        
        return self.load_selected_voice_for(get_tts_backend())

    def load_selected_voice_for(self, backend):
        
        try:
            cfg_path = self.get_config_path()
            if not os.path.exists(cfg_path):
                return None
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            sv = cfg.get('selected_voices') or {}
            if backend in sv and sv[backend]:
                return sv[backend]

            legacy = cfg.get('selected_voice')
            if legacy and legacy.get('backend') == backend:
                return legacy
            return None
        except Exception as e:
            print("读取 %s 选中音色失败:" % backend, e)
        return None

    def save_selected_voice(self, desc):
        
        try:
            backend = desc.get('backend') or get_tts_backend()
            cfg_path = self.get_config_path()
            cfg = {}
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
            sv = cfg.setdefault('selected_voices', {})
            sv[backend] = desc

            cfg['selected_voice'] = desc
            with open(cfg_path, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("保存所选音色失败: %s" % e)

    def select_voice_file(self):
        

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择音色配置文件",
            "",
            "JSON文件 (*.json);;所有文件 (*.*)"
        )

        if file_path:
            try:

                with open(file_path, 'r', encoding='utf-8') as f:
                    voice_config = json.load(f)


                if 'voices' in voice_config and isinstance(voice_config['voices'], list):

                    self.save_voice_config(file_path, voice_config)


                    self.refresh_voice_list()
                    print("已加载音色配置")
                else:
                    self.current_voice_label.setText("错误：无效的音色配置文件")
                    self.current_voice_label.setStyleSheet("color: red; font-size: 13px; font-weight: bold;")

            except Exception as e:
                self.current_voice_label.setText(f"错误：{str(e)}")
                self.current_voice_label.setStyleSheet("color: red; font-size: 13px; font-weight: bold;")
                print(f"加载音色配置失败: {e}")

    def save_voice_config(self, file_path, voice_config):
        
        try:

            if 'default_voice' not in voice_config:
                voice_config['default_voice'] = 0


            voices_path = self.get_voices_path()
            with open(voices_path, 'w', encoding='utf-8') as f:
                json.dump(voice_config, f, ensure_ascii=False, indent=2)
            print(f"音色配置已保存到: {voices_path}")
        except Exception as e:
            print(f"保存音色配置失败: {e}")

    def get_voices_path(self):
        
        if hasattr(sys, '_MEIPASS'):
            return os.path.join(os.path.dirname(sys.executable), 'voices.json')
        else:
            return os.path.join(os.path.dirname(__file__), 'voices.json')

    def sync_voice_to_main(self, voice_config):
        
        try:

            if self.parent() and hasattr(self.parent(), 'speech_engine'):
                speech_engine = self.parent().speech_engine


                if voice_config.get('voices'):
                    speech_engine.voices = []
                    speech_engine.zh_voice_id = None
                    speech_engine.en_voice_id = None


                    speech_engine.initialize_engine()


                    if voice_config['voices']:
                        first_voice = voice_config['voices'][0]
                        voice_id = first_voice.get('id')
                        if voice_id:

                            default_index = voice_config.get('default_voice', 0)
                            if default_index < len(voice_config['voices']):
                                selected_voice = voice_config['voices'][default_index]
                                voice_id = selected_voice.get('id')


                            speech_engine.zh_voice_id = voice_id

                print("音色已同步到主界面")
        except Exception as e:
            print(f"同步音色到主界面失败: {e}")
    
    def create_display_page(self):
        
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)
        

        self.auto_scroll_checkbox = QCheckBox("自动滚动到最新消息")
        self.auto_scroll_checkbox.setChecked(True)
        self.auto_scroll_checkbox.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(self.auto_scroll_checkbox)


        self.screen_narrate_checkbox = QCheckBox("屏幕监控时朗读 AI 的理解")
        self.screen_narrate_checkbox.setChecked(True)
        self.screen_narrate_checkbox.setStyleSheet("font-size: 15px; font-weight: bold;")
        self.screen_narrate_checkbox.setToolTip(
            "开启后，屏幕监控会按 AI 对画面的理解轻声念一句（不是逐字念屏幕文字）。"
            "需选中模型支持看图（视觉能力）才会生效。")
        layout.addWidget(self.screen_narrate_checkbox)


        self.seamless_read_checkbox = QCheckBox("无缝朗读（整段合成后连续播放，句间无停顿）")
        self.seamless_read_checkbox.setChecked(True)
        self.seamless_read_checkbox.setStyleSheet("font-size: 15px; font-weight: bold;")
        self.seamless_read_checkbox.setToolTip(
            "开启后，AI 回复会等整段语音合成完毕再一口气连续读出，句与句之间不再有"
            "「等待克隆模型合成」的空档（更连贯）；代价是开头要等整段合成完才出声。"
            "关闭则回到「边生成边读」（首句快，但句间可能停顿）。")
        layout.addWidget(self.seamless_read_checkbox)

        layout.addStretch()
        return page
    
    def create_ai_model_page(self):
        
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)


        info = QLabel(
            "这个软件自己不带 AI 大脑，得由你接一个才能聊天。\n"
            "怎么接？点下面的「+ 自定义 API」填一下就行，选好服务商它会自动帮你填好地址。\n\n"
            "· 云端模型（DeepSeek / 通义千问 / OpenAI 等）：必须填「API 密钥」，\n"
            "  这相当于账号密码，没有就接不上（去官网注册就能拿到，大多很便宜甚至免费）。\n"
            "· 本地模型（Ollama）：不用密钥，\n"
            "  但你要先在自己电脑上把模型跑起来（打开对应的本地服务）才能连。"
        )
        info.setWordWrap(True)
        info.setContentsMargins(12, 10, 12, 10)
        info.setStyleSheet("""
            QLabel {
                background-color: #fff8e1;
                border: 1px solid #ffe08a;
                border-radius: 8px;
                color: #000000;
                font-size: 20px;
                font-weight: bold;
                line-height: 1.55;
            }
        """)
        layout.addWidget(info)


        preset_title = QLabel("添加模型配置（点 + 自定义 API，选好服务商后会自动填好地址）")
        preset_title.setStyleSheet("color: #666; font-size: 23px; font-weight: bold;")
        layout.addWidget(preset_title)

        custom_btn = QPushButton("+ 自定义 API")
        custom_btn.setCursor(Qt.PointingHandCursor)
        custom_btn.setToolTip("添加自定义 / 本地部署模型（选好服务商自动填地址）")
        custom_btn.setStyleSheet("""
            QPushButton {
                background-color: #667eea;
                color: white;
                border: none;
                border-radius: 14px;
                padding: 5px 14px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #5a7fd6; }
        """)
        custom_btn.clicked.connect(lambda: self._add_or_edit_ai_model())
        layout.addWidget(custom_btn)


        self.ai_model_list = QListWidget()
        self.ai_model_list.setSelectionMode(QListWidget.SingleSelection)
        self.ai_model_list.setStyleSheet("""
            QListWidget {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                outline: none;
                padding: 4px;
            }
            QListWidget::item {
                padding: 10px 12px;
                border-bottom: 1px solid #f0f0f0;
                border-radius: 6px;
                font-size: 20px;
            }
            QListWidget::item:selected {
                background-color: #667eea;
                color: white;
            }
            QListWidget::item:hover:!selected {
                background-color: #f0f0ff;
            }
        """)

        self.ai_model_list.itemClicked.connect(self._on_ai_model_item_clicked)
        self.ai_model_list.itemDoubleClicked.connect(self._on_ai_model_item_double_clicked)
        self.ai_model_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ai_model_list.customContextMenuRequested.connect(self._on_ai_model_menu)
        layout.addWidget(self.ai_model_list)


        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        scan_btn = QPushButton("🔄 扫描本地")
        scan_btn.setToolTip("自动扫描本机正在运行的 Ollama 模型并加载")
        scan_btn.setFixedHeight(36)
        scan_btn.setCursor(Qt.PointingHandCursor)
        scan_btn.setStyleSheet("""
            QPushButton {
                background-color: #ed8936;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 0 16px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #dd7724; }
            QPushButton:disabled { background-color: #f6c28b; }
        """)
        scan_btn.clicked.connect(self._on_scan_local_models)

        self.ai_test_btn = QPushButton("测试连接")
        self.ai_test_btn.setFixedHeight(36)
        self.ai_test_btn.setCursor(Qt.PointingHandCursor)
        self.ai_test_btn.setStyleSheet("""
            QPushButton {
                background-color: #48bb78;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 0 16px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #38a169; }
            QPushButton:disabled { background-color: #9ae6b4; }
        """)
        self.ai_test_btn.clicked.connect(self._on_test_ai_model)

        self.ai_delete_btn = QPushButton("删除")
        self.ai_delete_btn.setFixedHeight(36)
        self.ai_delete_btn.setCursor(Qt.PointingHandCursor)
        self.ai_delete_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #e74c3c, stop:1 #c0392b);
                color: white;
                border: none;
                border-radius: 8px;
                padding: 0 22px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background: #c0392b; }
            QPushButton:disabled { background: #f0a0a0; }
        """)
        self.ai_delete_btn.clicked.connect(self._on_delete_ai_model)

        btn_row.addWidget(scan_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.ai_test_btn)
        btn_row.addSpacing(8)
        btn_row.addWidget(self.ai_delete_btn)
        layout.addLayout(btn_row)

        layout.addStretch()
        self._update_ai_model_buttons()
        return page

    def create_permission_page(self):
        
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)


        tip = QLabel(
            "开启对应权限后，AI 可通过本地指令执行下列操作（无需模型自带工具能力）。\n"
            "所有权限默认关闭，请仅在信任当前使用场景时开启。危险操作有标注。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#666; font-size:14px; line-height:1.6;")
        layout.addWidget(tip)


        self.perm_enabled = QCheckBox("启用模型工具权限（总开关）")
        self.perm_enabled.setStyleSheet("font-size:17px; font-weight:bold; color:#333;")
        layout.addWidget(self.perm_enabled)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background-color:#e0e0e0;")
        sep.setFixedHeight(1)
        layout.addWidget(sep)


        def _make_perm(key_attr, title, desc, danger=False):
            box = QCheckBox(title)
            box.setStyleSheet("font-size:16px; font-weight:bold; color:%s;" % (
                "#c0392b" if danger else "#333"))
            sub = QLabel(desc)
            sub.setWordWrap(True)
            sub.setStyleSheet("color:#888; font-size:13px; padding-left:28px; line-height:1.5;")
            return box, sub

        self.perm_read, sub_read = _make_perm(
            "perm_read", "📖  文件读取",
            "允许 AI 读取你指定路径的文本/代码文件内容。")
        self.perm_write, sub_write = _make_perm(
            "perm_write", "📝  文件写入 / 创建",
            "允许 AI 创建新文件或修改已有文件内容。")
        self.perm_delete, sub_delete = _make_perm(
            "perm_delete", "🗑️  文件删除  ⚠️ 危险",
            "允许 AI 删除你指定路径的文件。删除后不可恢复，请谨慎开启。", danger=True)
        self.perm_system, sub_system = _make_perm(
            "perm_system", "⚡  系统 / 程序控制  ⚠️ 高危",
            "允许 AI 执行关机、重启电脑、关闭或重启本程序。误触发会导致数据丢失，请谨慎开启。",
            danger=True)

        for box, sub in [(self.perm_read, sub_read), (self.perm_write, sub_write),
                         (self.perm_delete, sub_delete), (self.perm_system, sub_system)]:
            layout.addWidget(box)
            layout.addWidget(sub)


        for box in (self.perm_enabled, self.perm_read, self.perm_write,
                    self.perm_delete, self.perm_system):
            box.stateChanged.connect(self.save_settings)

        layout.addStretch()
        return page

    def refresh_ai_model_list(self):
        
        self.ai_model_list.clear()
        models = load_ai_models()
        active = get_active_ai_model()
        active_id = active.get("id") if active else None
        self._ai_model_items = []
        for m in models:
            name = m.get("name", "未命名")
            is_active = m.get("id") == active_id
            is_preset = bool(m.get("preset_key"))
            badge = "【内置】" if is_preset else "【自定义】"
            star = "★ " if is_active else ""
            label = star + name + " " + badge
            self.ai_model_list.addItem(label)

            item = self.ai_model_list.item(self.ai_model_list.count() - 1)
            item.setToolTip(
                f"API: {m.get('base_url', '-')}\n"
                f"模型: {m.get('model', '-')}\n"
                f"类型: {'本地部署' if m.get('is_local') else '在线服务'}"
            )
            self._ai_model_items.append(m)
        self._update_ai_model_buttons()

    def _update_ai_model_buttons(self):
        has = self.ai_model_list.count() > 0
        has_sel = self.ai_model_list.currentRow() >= 0
        self.ai_test_btn.setEnabled(has_sel)
        self.ai_delete_btn.setEnabled(has_sel)

    def _get_selected_model(self):
        
        row = self.ai_model_list.currentRow()
        items = getattr(self, "_ai_model_items", [])
        if 0 <= row < len(items):
            return items[row]
        return None

    def _on_ai_model_item_clicked(self, item):
        
        self._set_active_by_item(item)

    def _set_active_by_item(self, item):
        model = self._get_selected_model()
        if model:
            self._set_active_by_name(model.get("name", ""))

    def _on_ai_model_item_double_clicked(self, item):
        
        model = self._get_selected_model()
        if model:
            self._add_or_edit_ai_model(model.get("name"))

    def _on_ai_model_menu(self, pos):
        item = self.ai_model_list.itemAt(pos)
        if item is None:
            return
        model = self._get_selected_model()
        if not model:
            return
        name = model.get("name", "")
        self.ai_model_list.setCurrentItem(item)
        self.ai_model_list.setFocus()
        QApplication.processEvents()
        menu = QMenu(self)
        if model.get("preset_key"):
            act_reset = QAction("🔄 重置「%s」为默认" % name, self)
            act_reset.triggered.connect(lambda: self._reset_preset_model(model))
            menu.addAction(act_reset)
        act_del = QAction("🗑 删除「%s」" % name, self)
        act_del.triggered.connect(lambda: self._delete_ai_model_by_name(name))
        menu.addAction(act_del)
        menu.exec_(self.ai_model_list.mapToGlobal(pos))

    def _add_or_edit_ai_model(self, name=None):
        
        models = load_ai_models()
        edit = None
        if name:
            target = name.lstrip("★ ").strip()
            for m in models:
                if m.get("name") == target:
                    edit = m
                    break
        dlg = AIModelEditDialog(self, edit_model=edit)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            if edit:

                old_id = edit.get("id")
                old_active = edit.get("active")
                edit.update(data)
                edit["id"] = old_id
                edit["active"] = old_active
            else:
                data["id"] = str(uuid.uuid4())
                data["active"] = False
                models.append(data)
            save_ai_models(models)
            self.refresh_ai_model_list()

    def _on_set_active_ai_model(self):
        
        item = self.ai_model_list.currentItem()
        if item is None:
            return
        self._set_active_by_item(item)

    def _set_active_by_name(self, name):
        name = name.lstrip("★ ").strip()
        models = load_ai_models()
        changed = False
        target = None
        for m in models:
            is_active = (m.get("name") == name)
            if m.get("active") != is_active:
                m["active"] = is_active
                changed = True
            if is_active:
                target = m
        if changed:
            save_ai_models(models)
        self.refresh_ai_model_list()

        if target and target.get("is_local"):
            self._auto_launch_local(target)

        self._notify_main_sync_caps()


    def _notify_main_sync_caps(self, live=None):
        
        mw = self.parent()
        if mw is not None and hasattr(mw, "_sync_model_capabilities"):
            mw._sync_model_capabilities(live=live)



    def _auto_launch_local(self, model):
        
        svc = detect_local_svc_type(model)
        if svc == "unknown":
            return

        def _work():
            ok, msg = launch_local_service(svc, timeout=30)

            current_info = {
                "name": model.get("name", "当前模型"),
                "model_id": (model.get("model") or "").strip(),
                "installed": False,
            }
            if ok and svc == "ollama":
                try:
                    names = scan_ollama_model_names(force=True)
                    current_info["installed"] = bool(current_info["model_id"]) and \
                                                (current_info["model_id"] in names)
                except Exception as e:
                    print("检查当前模型安装状态失败:", e)

            self._last_launch_svc = svc
            self._last_launch_current = current_info
            self.local_launch_done.emit(ok, msg)

        import threading
        threading.Thread(target=_work, daemon=True).start()

    def _on_local_launch_done(self, ok, msg):
        
        svc = self._last_launch_svc
        cur = getattr(self, "_last_launch_current", {})
        name = cur.get("name", "当前模型")
        model_id = cur.get("model_id", "")
        installed = cur.get("installed", False)
        if ok:
            self.refresh_ai_model_list()

            self._notify_main_sync_caps(live=True)
            if installed:
                QMessageBox.information(
                    self, "本地服务已启动",
                    "已自动启动 %s 服务。\n\n当前模型「%s」已可用，"
                    "可直接返回聊天使用。" % (svc, name))
            else:
                pull_tip = ""
                if model_id:
                    pull_tip = "\n\n如需使用该模型，请在终端执行：\nollama pull %s" % model_id
                QMessageBox.information(
                    self, "本地服务已启动",
                    "已自动启动 %s 服务。\n\n当前模型「%s」尚未安装。%s"
                    "\n\n或者点击「扫描本地」查看本机所有可用模型。"
                    % (svc, name, pull_tip))
        else:
            QMessageBox.warning(
                self, "本地服务启动失败",
                "无法自动启动 %s：\n%s\n\n"
                "请手动启动该服务后重试：\n"
                "• Ollama：运行 Ollama 桌面应用，或在终端执行 `ollama serve`"
                % (svc, msg))
            self.refresh_ai_model_list()

    def _on_test_ai_model(self):
        
        model = self._get_selected_model()
        if not model:
            return
        self.ai_test_btn.setEnabled(False)
        self.ai_test_btn.setText("测试中…")

        def _test():
            try:
                worker = ChatWorker("test")
                worker.test_connection(model)
                return (True, "连接成功")
            except Exception as e:
                return (False, str(e))
        def _done(result):
            ok, msg = result
            self.ai_test_btn.setEnabled(True)
            self.ai_test_btn.setText("测试连接")
            if ok:

                self._notify_main_sync_caps(live=True)
                QMessageBox.information(self, "连接成功", "「%s」连接正常。" % model.get("name", ""))
            else:
                QMessageBox.warning(self, "连接失败", "「%s」连接失败：\n%s" % (model.get("name", ""), msg))
        import threading
        threading.Thread(target=lambda: _done(_test()), daemon=True).start()

    def _on_scan_local_models(self):
        
        sender = self.sender()
        if sender is not None:
            sender.setEnabled(False)
            sender.setText("扫描中…")
        import threading

        def _scan():
            try:
                return self._scan_local_models()
            except Exception as e:
                print("扫描本地模型异常:", e)
                return []

        def _done(found):
            if sender is not None:
                sender.setEnabled(True)
                sender.setText("🔄 扫描本地")
            if not found:


                models = load_ai_models()
                dirty = False
                for m in models:
                    if m.get("active") and m.get("is_local"):
                        m["active"] = False
                        dirty = True
                if dirty:
                    save_ai_models(models)
                    self.refresh_ai_model_list()
                QMessageBox.information(
                    self, "扫描完成",
                    "未发现本地运行的模型服务。\n请先启动 Ollama，"
                    "并确保其 OpenAI 兼容接口已开启\n（默认端口 11434）。"
                )
                return
            names = "\n".join("• " + f["name"] for f in found)
            QMessageBox.information(
                self, "扫描完成",
                "已加载 %d 个本地模型：\n%s\n\n默认已设为当前模型，可直接返回聊天使用。"
                % (len(found), names)
            )
            self.refresh_ai_model_list()

        threading.Thread(target=lambda: _done(_scan()), daemon=True).start()

    def _scan_local_models(self):
        
        import urllib.request
        targets = [


            ("Ollama", "http://127.0.0.1:11434", "/api/tags", "ollama"),
        ]
        discovered = []
        for svc_name, base, path, svc_type in targets:
            try:
                req = urllib.request.Request(base + path, method="GET")
                req.add_header("Accept", "application/json")
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                print("扫描 %s 跳过: %s" % (svc_name, e))
                continue
            models_here = []
            if svc_type == "ollama":
                for m in data.get("models", []):
                    nm = m.get("name") or m.get("model")
                    if nm:
                        models_here.append((nm, nm))
            else:
                for m in data.get("data", []):
                    mid = m.get("id") or m.get("name")
                    if mid:
                        models_here.append((mid, mid))
            v1_base = base + "/v1"
            for label, model_id in models_here:
                discovered.append({
                    "name": "%s · %s" % (svc_name, label),
                    "base_url": v1_base,
                    "api_key": "",
                    "model": model_id,
                    "is_local": True,
                })
        if discovered:
            self._merge_discovered_models(discovered)
        return discovered

    def _merge_discovered_models(self, discovered):
        
        models = load_ai_models()
        existing_keys = {(m.get("base_url", ""), m.get("model", "")) for m in models}
        added = 0
        for d in discovered:
            key = (d.get("base_url", ""), d.get("model", ""))
            if key in existing_keys:
                continue
            d["id"] = "local:" + str(uuid.uuid4())[:8]
            d["active"] = False
            models.append(d)
            existing_keys.add(key)
            added += 1

        if added > 0 and not any(m.get("active") for m in models):
            local = [m for m in models if m.get("is_local")]
            chosen = None
            for m in local:
                if _detect_multimodal(m.get("model", "")):
                    chosen = m
                    break
            if chosen is None and local:
                chosen = local[0]
            if chosen is not None:
                chosen["active"] = True
        save_ai_models(models)

    def _reset_preset_model(self, model):
        
        key = model.get("preset_key")
        if not key:
            return
        cfg = get_preset_default(key)
        reply = QMessageBox.question(
            self, "重置预设",
            "确定要将「%s」恢复为默认配置吗？\n当前填写的 API 密钥与模型名将保留。" % model.get("name", ""),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        models = load_ai_models()
        for m in models:
            if m.get("preset_key") == key:

                m["name"] = cfg["name"]
                m["base_url"] = cfg["base_url"]
                m["model"] = cfg["model"]
                m["is_local"] = cfg["is_local"]
                break
        save_ai_models(models)
        self.refresh_ai_model_list()

    def _on_delete_ai_model(self):
        item = self.ai_model_list.currentItem()
        if item is None:
            return
        model = self._get_selected_model()
        if model and model.get("preset_key"):
            self._reset_preset_model(model)
            return
        self._delete_ai_model_by_name(model.get("name", "") if model else "")

    def _delete_ai_model_by_name(self, name):
        name = name.lstrip("★ ").strip()
        if not name:
            return
        reply = QMessageBox.question(
            self, "确认删除",
            "确定要删除模型「%s」吗？" % name,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        models = load_ai_models()
        models = [m for m in models if m.get("name") != name]
        save_ai_models(models)
        self.refresh_ai_model_list()

    def on_category_changed(self, index):
        
        if index == 0:

            self.general_page.show()
            self.voice_page.hide()
            self.display_page.hide()
            self.ai_model_page.hide()
            self.permission_page.hide()
            self.detail_title.setText("通用")
        elif index == 1:

            self.general_page.hide()
            self.voice_page.show()
            self.display_page.hide()
            self.ai_model_page.hide()
            self.permission_page.hide()
            self.detail_title.setText("语音设置")
        elif index == 2:

            self.general_page.hide()
            self.voice_page.hide()
            self.display_page.show()
            self.ai_model_page.hide()
            self.permission_page.hide()
            self.detail_title.setText("显示设置")
        elif index == 3:

            self.general_page.hide()
            self.voice_page.hide()
            self.display_page.hide()
            self.ai_model_page.show()
            self.permission_page.hide()
            self.detail_title.setText("AI 模型")
        elif index == 4:

            self.general_page.hide()
            self.voice_page.hide()
            self.display_page.hide()
            self.ai_model_page.hide()
            self.permission_page.show()
            self.detail_title.setText("模型权限")
    
    def load_settings(self):
        
        config_path = self.get_config_path()
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.voice_checkbox.setChecked(config.get('voice_enabled', True))
                    self.speed_slider.setValue(config.get('voice_speed', 150))
                    self.volume_slider.setValue(int(config.get('voice_volume', 1.0) * 100))
                    self.auto_scroll_checkbox.setChecked(config.get('auto_scroll', True))
                    self.screen_narrate_checkbox.setChecked(config.get('screen_narrate', True))
                    self.seamless_read_checkbox.setChecked(config.get('seamless_read', True))


                    if config.get('background_type') == 'image':
                        self.bg_image_radio.setChecked(True)
                    else:
                        self.bg_default_radio.setChecked(True)

                    self.color1 = config.get('color1', '#667eea')
                    self.color2 = config.get('color2', '#764ba2')


                    self.color1_preview.setStyleSheet(f"background-color: {self.color1}; border: 2px solid #999; border-radius: 5px;")
                    self.color2_preview.setStyleSheet(f"background-color: {self.color2}; border: 2px solid #999; border-radius: 5px;")


                    if config.get('background_image'):
                        self.selected_image_path = config.get('background_image')
                        self.image_path_label.setText(os.path.basename(self.selected_image_path))
                        self.image_path_label.setStyleSheet("color: #667eea; font-size: 13px; font-weight: bold;")


                    perms = config.get('permissions', {})
                    self.perm_enabled.setChecked(perms.get('enabled', False))
                    self.perm_read.setChecked(perms.get('read', False))
                    self.perm_write.setChecked(perms.get('write', False))
                    self.perm_delete.setChecked(perms.get('delete', False))
                    self.perm_system.setChecked(perms.get('system', False))
        except:
            pass


        self.load_current_voice()


        try:
            self.refresh_ai_model_list()
        except Exception as e:
            print("加载 AI 模型列表失败:", e)

    def load_current_voice(self):
        
        try:
            self.refresh_voice_list()
        except Exception as e:
            print(f"加载音色信息失败: {e}")
            self.current_voice_label.setText("当前音色：未选择")
            self.current_voice_label.setStyleSheet("color: #667eea; font-size: 13px; font-weight: bold;")

    def save_settings(self):
        
        config = {
            'voice_enabled': self.voice_checkbox.isChecked(),
            'voice_speed': self.speed_slider.value(),
            'voice_volume': self.volume_slider.value() / 100.0,
            'auto_scroll': self.auto_scroll_checkbox.isChecked(),
            'screen_narrate': self.screen_narrate_checkbox.isChecked(),
            'seamless_read': self.seamless_read_checkbox.isChecked(),
            'background_type': 'color' if self.bg_default_radio.isChecked() else 'image',
            'color1': self.color1,
            'color2': self.color2,
            'background_image': self.selected_image_path,
            'permissions': {
                'enabled': self.perm_enabled.isChecked(),
                'read': self.perm_read.isChecked(),
                'write': self.perm_write.isChecked(),
                'delete': self.perm_delete.isChecked(),
                'system': self.perm_system.isChecked(),
            },
        }

        config_path = self.get_config_path()
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)


            if self.speech_engine and self.speech_engine.engine:
                self.speech_engine.engine.setProperty('rate', config['voice_speed'])
                self.speech_engine.engine.setProperty('volume', config['voice_volume'])
                self.speech_engine.voice_speed = config['voice_speed']
                self.speech_engine.seamless_read = config.get('seamless_read', True)

            print("设置已保存:", config)

        except Exception as e:
            print(f"保存设置失败: {e}")
    
    def get_config_path(self):
        
        if hasattr(sys, '_MEIPASS'):
            return os.path.join(os.path.dirname(sys.executable), 'settings.json')
        else:
            return os.path.join(os.path.dirname(__file__), 'settings.json')


# ============================================================================

# ============================================================================
_MEMORY_EDIT_FILES = ["根基.md", "记忆.md", "思考记录.md", "情绪.md", "人设.md"]


def _local_brain_base_url():
    
    try:
        m = get_active_ai_model()
    except Exception:
        return None
    if not m:
        return None
    base = (m.get("base_url", "") or "").rstrip("/")
    if "127.0.0.1:8000" not in base and "localhost:8000" not in base:
        return None
    return base


def _api_get_json(url, timeout=5):
    import urllib.request
    req = urllib.request.Request(url, method="GET",
                                 headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _api_post_json(url, body, timeout=5):
    import urllib.request
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json",
                 "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class MemoryEditorDialog(QDialog):
    

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🧠 记忆库编辑（本地大脑）")
        self.setMinimumSize(860, 620)
        self._base = _local_brain_base_url()
        layout = QHBoxLayout(self)


        left = QVBoxLayout()
        self.file_list = QListWidget()
        self.file_list.addItems(_MEMORY_EDIT_FILES)
        self.file_list.currentTextChanged.connect(self._load_file)
        left.addWidget(QLabel("记忆库文件"))
        left.addWidget(self.file_list, 1)
        layout.addLayout(left, 0)


        right = QVBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color:#888;")
        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont("Microsoft YaHei", 11))
        btns = QHBoxLayout()
        self.btn_refresh = QPushButton("🔄 刷新")
        self.btn_save = QPushButton("💾 保存")
        self.btn_close = QPushButton("关闭")
        self.btn_refresh.clicked.connect(self._load_selected)
        self.btn_save.clicked.connect(self._save)
        self.btn_close.clicked.connect(self.reject)
        btns.addWidget(self.btn_refresh)
        btns.addWidget(self.btn_save)
        btns.addStretch(1)
        btns.addWidget(self.btn_close)
        right.addWidget(self.status_label)
        right.addWidget(self.editor, 1)
        right.addLayout(btns)
        layout.addLayout(right, 1)

        if not self._base:
            self.status_label.setText(
                "⚠️ 请先选中本地 8000 模型再编辑记忆库。")
            self.editor.setReadOnly(True)
            self.btn_save.setEnabled(False)
            self.btn_refresh.setEnabled(False)
        else:
            self._load_selected()

    def _current_file(self):
        return self.file_list.currentItem().text() if self.file_list.currentItem() else ""

    def _load_selected(self):
        self._load_file(self._current_file())

    def _load_file(self, fname):
        if not fname or not self._base:
            return
        try:
            data = _api_get_json(self._base + "/v1/memory?file=" +
                                 urllib.parse.quote(fname), timeout=5)
            if data.get("ok"):
                self.editor.setPlainText(data.get("content", ""))
                self.status_label.setText("已加载 %s（%d 字）"
                                          % (fname, len(data.get("content", ""))))
            else:
                self.status_label.setText("加载失败：%s" % data.get("error", ""))
        except Exception as e:
            self.status_label.setText("加载失败：%s" % e)

    def _save(self):
        fname = self._current_file()
        if not fname or not self._base:
            return
        content = self.editor.toPlainText()
        try:
            data = _api_post_json(self._base + "/v1/memory",
                                  {"file": fname, "content": content}, timeout=5)
            if data.get("ok"):
                self.status_label.setText("✅ 已保存 %s（%d 字）"
                                          % (fname, len(content)))
            else:
                self.status_label.setText("保存失败：%s" % data.get("error", ""))
        except Exception as e:
            self.status_label.setText("保存失败：%s" % e)


class AIChatWindow(QMainWindow):
    
    def __init__(self):
        super().__init__()
        self.speech_engine = SpeechEngine()
        try:
            self.speech_engine.synth_status_signal.connect(self.on_synth_status)

            self.speech_engine.stream_reveal.connect(self._on_stream_reveal)
            self.speech_engine.speaking_finished.connect(self._reveal_all_text)
        except Exception:
            pass
        self._revealed_len = 0
        self.voice_enabled = True
        self.auto_scroll = True
        self.screen_narrate = True
        self.background_type = 'color'
        self.color1 = '#667eea'
        self.color2 = '#764ba2'
        self.gradient_angle = 0
        self.background_image = ''
        self.load_settings()
        self.setup_ui()
        self.worker = None
        self._screen_worker = None


        self._proactive_timer = QTimer(self)
        self._proactive_timer.timeout.connect(self._poll_proactive)
        self._proactive_timer.start(5000)
        self.typing_bubble = None
        self.typing_container = None
        self.apply_background()


        self.emotion_analyzer = EmotionAnalyzer()
        self.model_caps = detect_model_capabilities(get_active_ai_model())
        self._sync_model_capabilities()



        QTimer.singleShot(1500, self._autostart_local_ollama)


        self.screen_monitor = None
        self._screen_busy = False
        self._screen_context = ""
        self._screen_last_spoken = ""
        self._screen_last_spoken_ts = 0.0
        self._screen_last_shown = ""
        self._screen_last_shown_ts = 0.0



        if get_tts_backend() == "cosyvoice":
            QTimer.singleShot(2500, self._warmup_cosyvoice)


    def _warmup_cosyvoice(self):
        
        try:
            from cosyvoice_tts import CosyVoiceCloner
            CosyVoiceCloner.get_instance().warm_up()
        except Exception as e:
            print("CosyVoice 预热启动失败（首次合成时会重试）:", e)

    def _sync_model_capabilities(self, live=None):
        
        active = get_active_ai_model()

        caps = detect_model_capabilities(active)

        if live is None:
            live = bool(active and active.get("is_local")
                        and detect_local_svc_type(active) == "ollama"
                        and is_local_service_up("ollama"))
        if live:
            probe = probe_local_model_capabilities(active)
            if probe:
                for k, v in probe.items():
                    if v is not None:
                        caps[k] = v



        if _is_builtin_model(active):
            for cap in ("emotion", "tts", "asr"):
                caps[cap] = False
        self.model_caps = caps
        name = active.get("name", "") if active else "（未选择模型）"

        # emotion
        if self.model_caps["emotion"]:
            print("情感识别：当前模型「%s」已内置情感识别，已停用内置情感分析器" % name)
        else:
            print("情感识别：启用内置轻量情感分析器（当前模型无内置情感能力）")


        if getattr(self, "speech_engine", None) is not None:
            self.speech_engine.emotion_enabled = not self.model_caps.get("emotion", False)
            print("情绪语调：%s" % ("已停用（模型自带情感）"
                                    if self.model_caps.get("emotion") else "已启用内置情绪语调"))




        self._apply_capability_ui()


        if self.model_caps["tts"]:
            print("语音合成：当前模型自带语音输出，已停用本地 TTS 朗读")
        if self.model_caps["asr"]:
            print("语音识别：当前模型自带听音，已停用本地 whisper 转写"
                  "（录音将直接作为附件发给模型）")
            print("          silero-vad 端点检测保留：它与「识别」解耦，"
                  "负责判断何时开始/停止录音，模型能力检测体系里无此对应项，"
                  "故不能随 ASR 一并关闭（否则无法判断用户何时说完）")
        if not (self.model_caps["tts"] or self.model_caps["asr"]):
            print("语音：启用本地 TTS / whisper（当前模型无对应内置能力）")
        if not self.model_caps["asr"]:
            print("端点检测：启用本地 silero-vad 人声检测"
                  "（区分人声/环境声，判断录音起止）")
        if self.model_caps["vision"]:
            print("屏幕监控：当前模型支持看图，画面直接作为附件发送")
        else:
            print("屏幕监控：当前模型不支持看图，已启用界面内置本地视觉模型兜底")


        self._update_cap_status_label()


        fl = getattr(self, "floating", None)
        if fl is not None and getattr(fl, "listener", None) is not None:
            fl.listener.model_handles_asr = self.model_caps["asr"]

    def _apply_capability_ui(self):
        
        caps = getattr(self, "model_caps", {}) or {}
        vision = bool(caps.get("vision"))


        screen_btn = getattr(self, "screen_btn", None)
        if screen_btn is not None:
            screen_btn.setEnabled(True)
            if vision:
                screen_btn.setToolTip("开启/关闭屏幕实时监控（自动截屏并发给 AI，当前模型支持看图）")
            else:
                screen_btn.setToolTip("当前模型不支持看图，已启用界面内置视觉模型为屏幕监控兜底")
        screen_pick = getattr(self, "screen_pick_btn", None)
        if screen_pick is not None:
            screen_pick.setEnabled(True)
            screen_pick.setToolTip("选择要共享的屏幕或窗口" if vision
                                   else "选择共享源，画面将由界面内置视觉模型先理解再传给 AI")


        dlg = getattr(self, "settings_dialog", None)
        if dlg is not None:
            dlg._apply_model_caps_to_ui()


    def _autostart_local_ollama(self):
        
        active = get_active_ai_model()
        if not (active and active.get("is_local")
                and detect_local_svc_type(active) == "ollama"):
            return
        self._ollama_starter = OllamaAutoStartWorker(active)
        self._ollama_starter.status.connect(self._on_ollama_start_status)
        self._ollama_starter.finished_up.connect(self._on_ollama_start_done)
        self._ollama_starter.start()

    def _on_ollama_start_status(self, msg):
        
        if getattr(self, "cap_status_label", None) is not None:
            self.cap_status_label.setText("Ollama：%s" % msg)
            self.cap_status_label.setToolTip(msg)

    def _on_ollama_start_done(self, ok, msg):
        
        if ok:
            print("[启动] 界面自带 Ollama：", msg)
        else:
            print("[启动] 界面自带 Ollama 启动失败：", msg)
        if getattr(self, "cap_status_label", None) is not None:
            self._update_cap_status_label()
        if ok:
            self._sync_model_capabilities(live=True)


    def _update_cap_status_label(self):
        
        if getattr(self, "cap_status_label", None) is None:
            return
        caps = getattr(self, "model_caps", {}) or {}
        active = get_active_ai_model()
        is_builtin = _is_builtin_model(active)

        items = [
            ("视觉", caps.get("vision")),
            ("听音", caps.get("asr")),
            ("朗读", caps.get("tts")),
            ("情感", caps.get("emotion")),
        ]
        parts = []
        for label, in_model in items:
            if in_model:
                parts.append("%s·模型" % label)
            else:
                parts.append("%s·本地" % label)
        prefix = "内置7B " if is_builtin else ""
        self.cap_status_label.setText(prefix + "  ".join(parts))
        self.cap_status_label.setToolTip(
            ("当前为界面内置的 7B 模型：始终使用内置本地实现"
             "（情感词典 / 本地 TTS / 本地 whisper），不触发「让位」逻辑；\n"
             if is_builtin else "")
            + "能力检测：模型自带的项由模型自己处理（界面不重复实现）；"
            "「本地」项由本软件的内置实现提供。\n"
            + "\n".join("• %s：%s" % (l, "模型内置" if b else "本机内置")
                        for l, b in items))


    def _detect_emotion(self, text):
        
        if self.model_caps.get("emotion"):
            return None
        return self.emotion_analyzer.analyze(text)


    def setup_ui(self):
        

        self.setWindowTitle("AI聊天智能体 - 桌面版")
        self.setMinimumSize(800, 600)
        

        window_width = 1100
        window_height = 800
        self.resize(window_width, window_height)
        

        screen = QApplication.primaryScreen()
        if screen:
            screen_geometry = screen.availableGeometry()
            x = (screen_geometry.width() - window_width) // 2
            y = (screen_geometry.height() - window_height) // 2
            self.move(x, y)


        self.central_widget = QWidget()
        self.central_widget.setObjectName("central_widget")
        self.setCentralWidget(self.central_widget)


        self.bg_label = QLabel(self.central_widget)
        self.bg_label.setObjectName("bg_label")
        self.bg_label.setScaledContents(True)
        self.bg_label.setAlignment(Qt.AlignCenter)
        self.bg_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.bg_label.lower()
        self.bg_label.hide()


        main_layout = QVBoxLayout(self.central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)


        header = self.create_header()
        main_layout.addWidget(header)


        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.5);
                border-radius: 5px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)


        self.chat_container = QWidget()
        self.chat_container.setStyleSheet("background-color: transparent;")
        self.chat_container.setAutoFillBackground(False)
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(10, 10, 10, 10)
        self.chat_layout.setSpacing(0)
        self.chat_layout.addStretch()

        self.chat_scroll.setWidget(self.chat_container)
        main_layout.addWidget(self.chat_scroll)


        input_area = self.create_input_area()
        main_layout.addWidget(input_area)



        self.drop_overlay = QWidget(self.central_widget)
        self.drop_overlay.setObjectName("drop_overlay")
        self.drop_overlay.setStyleSheet(
            "background-color: rgba(20,20,30,0.72);")
        self.drop_overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.drop_overlay.setGeometry(self.central_widget.rect())
        ov_layout = QVBoxLayout(self.drop_overlay)
        ov_layout.setContentsMargins(40, 40, 40, 40)
        ov_layout.setSpacing(18)
        ov_layout.addSpacing(20)


        self.drop_progress = QLabel("")
        self.drop_progress.setObjectName("drop_progress")
        self.drop_progress.setStyleSheet(
            "color: #ffe9a8; font-size: 18px; font-weight: bold; "
            "background: transparent;")
        self.drop_progress.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.drop_progress.setWordWrap(True)
        self.drop_progress.hide()
        ov_layout.addWidget(self.drop_progress)

        ov_layout.addStretch(1)


        self.drop_hint = QLabel("松开以加载专属音色\n（拖入任意音频 / 视频，自动降噪）")
        self.drop_hint.setStyleSheet(
            "color: white; font-size: 24px; font-weight: bold; "
            "background: transparent;")
        self.drop_hint.setAlignment(Qt.AlignCenter)
        ov_layout.addWidget(self.drop_hint)

        ov_layout.addStretch(2)
        self.drop_overlay.hide()


        self.listen_area = self.create_listen_area()
        main_layout.addWidget(self.listen_area)



        self.setAcceptDrops(True)


        QTimer.singleShot(500, lambda: self.add_message(
            "欢迎使用AI聊天智能体桌面版！\n\n"
            "我可以：\n"
            "• 和你聊天对话\n"
            "• 告诉你当前时间\n"
            "• 回答简单问题\n"
            "• 进行日常交流\n"
            "• 语音朗读回复\n\n"
            "试试说：你好、现在几点了、你是谁、帮助", False))

    def create_header(self):
        
        self.header_frame = QFrame()
        self.header_frame.setFixedHeight(60)

        layout = QHBoxLayout(self.header_frame)
        layout.setContentsMargins(15, 0, 15, 0)


        self.settings_button = QPushButton("⚙️")
        self.settings_button.setFixedSize(40, 40)
        self.settings_button.setCursor(Qt.PointingHandCursor)
        self.settings_button.setToolTip("打开设置")
        self.settings_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.2);
                color: white;
                border: 2px solid rgba(255, 255, 255, 0.4);
                border-radius: 20px;
                font-size: 18px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.35);
                border: 2px solid rgba(255, 255, 255, 0.6);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.45);
            }
        """)
        self.settings_button.clicked.connect(self.open_settings)
        layout.addWidget(self.settings_button)


        self.cap_status_label = QLabel("")
        self.cap_status_label.setFont(QFont("Microsoft YaHei", 10))
        self.cap_status_label.setStyleSheet(
            "color: rgba(255,255,255,0.92); background: transparent; "
            "padding: 0 6px;")
        layout.addWidget(self.cap_status_label)


        self.float_button = QPushButton("悬浮")
        self.float_button.setFixedSize(44, 40)
        self.float_button.setCursor(Qt.PointingHandCursor)
        self.float_button.setToolTip("显示/隐藏悬浮窗")
        self.float_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.2);
                color: white;
                border: 2px solid rgba(255, 255, 255, 0.4);
                border-radius: 20px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.35);
                border: 2px solid rgba(255, 255, 255, 0.6);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.45);
            }
        """)
        self.float_button.clicked.connect(self.toggle_floating)
        layout.addWidget(self.float_button)

        layout.addStretch()

        return self.header_frame

    def toggle_floating(self):
        
        floating = getattr(self, 'floating', None)
        if floating is None:
            return
        if self.isVisible():
            self.hide()
            if floating:
                floating.show()
                floating.raise_()
                floating.activateWindow()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def open_settings(self):
        
        dialog = SettingsDialog(self, self.speech_engine)
        self.settings_dialog = dialog
        if dialog.exec_() == QDialog.Accepted:

            self.load_settings()

            self.apply_background()

    def refresh_voice_list(self):
        
        try:
            dlg = getattr(self, 'settings_dialog', None)
            if dlg is not None and dlg.isVisible():
                dlg.refresh_voice_list()
        except Exception as e:
            print("刷新设置音色列表失败: %s" % e)
    
    def load_settings(self):
        
        config_path = self.get_settings_path()
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.voice_enabled = config.get('voice_enabled', True)
                    self.auto_scroll = config.get('auto_scroll', True)
                    self.screen_narrate = config.get('screen_narrate', True)
                    self.background_type = config.get('background_type', 'color')
                    self.color1 = config.get('color1', '#667eea')
                    self.color2 = config.get('color2', '#764ba2')
                    self.background_image = config.get('background_image', '')


                    if self.speech_engine and self.speech_engine.engine:
                        self.speech_engine.engine.setProperty('rate', config.get('voice_speed', 150))
                        self.speech_engine.engine.setProperty('volume', config.get('voice_volume', 1.0))
                        self.speech_engine.voice_speed = config.get('voice_speed', 150)
                        self.speech_engine.seamless_read = config.get('seamless_read', True)


                    sel = config.get('selected_voice')
                    if sel and self.speech_engine:
                        backend = sel.get('backend', 'openvoice')

                        if sel.get('kind') == 'cloned' and not sel.get('backend'):
                            backend = 'openvoice'

                        if backend != get_tts_backend():
                            self.speech_engine.set_tts_backend(backend)

                        if sel.get('kind') == 'cloned':

                            self.speech_engine.restore_cloned_voice(sel)
                        elif sel.get('kind') == 'cosyvoice':

                            self.speech_engine.set_active_voice({
                                "type": "cosyvoice",
                                "name": sel.get("name", ""),
                            })
                        else:
                            vid = sel.get('id')
                            if vid:
                                self.speech_engine.zh_voice_id = vid
                                self.speech_engine.en_voice_id = vid
                            self.speech_engine.set_active_voice({"type": "system", "id": vid})
        except:
            self.voice_enabled = True
            self.auto_scroll = True
            self.screen_narrate = True
    
    def get_settings_path(self):
        
        if hasattr(sys, '_MEIPASS'):
            return os.path.join(os.path.dirname(sys.executable), 'settings.json')
        else:
            return os.path.join(os.path.dirname(__file__), 'settings.json')
    
    def apply_background(self):
        
        try:
            print("\n=== 开始应用背景 ===")
            print(f"背景类型: {self.background_type}")
            print(f"颜色1: {self.color1}, 颜色2: {self.color2}")
            print(f"背景图片路径: '{self.background_image}'")


            c1 = self.color1
            c2 = self.color2
            c1_dark = self._darken_color(c1, 0.75)
            c2_dark = self._darken_color(c2, 0.75)
            c1_darker = self._darken_color(c1, 0.55)
            c2_darker = self._darken_color(c2, 0.55)

            if self.background_type == 'color':

                self.bg_label.hide()
                self.central_widget.setAutoFillBackground(False)
                palette = self.central_widget.palette()
                palette.setBrush(QPalette.Background, QBrush())
                self.central_widget.setPalette(palette)

                gradient_style = (
                    f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
                    f"stop:0 {c1}, stop:1 {c2});"
                )
                self.central_widget.setStyleSheet(f"QWidget#central_widget {{ {gradient_style} }}")
                print(f"✓ 已应用颜色背景: {c1} -> {c2}")


                self.header_frame.setStyleSheet(f"""
                    QFrame {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 {c1_dark}, stop:1 {c2_dark});
                    }}
                """)
                print("✓ 标题栏已同步")


                self.input_frame.setStyleSheet("""
                    QFrame {{
                        background-color: rgba(255, 255, 255, 0.88);
                        border-top: 1px solid rgba(0, 0, 0, 0.08);
                    }}
                """)
                print("✓ 输入区已同步")


                self.send_button.setStyleSheet(f"""
                    QPushButton {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 {c1}, stop:1 {c2});
                        color: white;
                        border: none;
                        border-radius: 22px;
                    }}
                    QPushButton:hover {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 {c1_dark}, stop:1 {c2_dark});
                    }}
                    QPushButton:pressed {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 {c1_darker}, stop:1 {c2_darker});
                    }}
                    QPushButton:disabled {{
                        background: #cccccc;
                    }}
                """)
                print("✓ 发送按钮已同步")

            elif self.background_type == 'image' and self.background_image:
                print("检查图片路径是否存在...")
                if os.path.exists(self.background_image):
                    print(f"✓ 图片文件存在: {self.background_image}")
                    pixmap = QPixmap(self.background_image)
                    print(f"图片加载结果: isNull={pixmap.isNull()}, 尺寸: {pixmap.width()}x{pixmap.height()}")

                    if not pixmap.isNull():
                        print("✓ 图片加载成功")
                        print(f"窗口尺寸: {self.central_widget.width()}x{self.central_widget.height()}")

                        self.central_widget.setStyleSheet("")
                        scaled_pixmap = self._scale_bg_to_widget(pixmap)
                        print(f"缩放后尺寸: {scaled_pixmap.width()}x{scaled_pixmap.height()}")


                        self.bg_label.setPixmap(scaled_pixmap)
                        self.bg_label.setGeometry(self.central_widget.rect())
                        self.bg_label.show()
                        self.bg_label.lower()
                        self.central_widget.update()
                        print("✓ 已应用图片背景")


                        self.header_frame.setStyleSheet("""
                            QFrame {
                                background-color: rgba(0, 0, 0, 0.25);
                            }
                        """)
                        self.input_frame.setStyleSheet("""
                            QFrame {
                                background-color: rgba(255, 255, 255, 0.9);
                                border-top: 1px solid rgba(0, 0, 0, 0.08);
                            }
                        """)
                        self.send_button.setStyleSheet(f"""
                            QPushButton {{
                                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 {c1}, stop:1 {c2});
                                color: white; border: none; border-radius: 22px;
                            }}
                            QPushButton:hover {{
                                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 {c1_dark}, stop:1 {c2_dark});
                            }}
                            QPushButton:pressed {{
                                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 {c1_darker}, stop:1 {c2_darker});
                            }}
                            QPushButton:disabled {{ background: #cccccc; }}
                        """)
                        print("✓ 标题栏/输入区/按钮已同步（图片模式）")
                    else:
                        print(f"✗ 图片加载失败: {self.background_image}")
                        self.apply_default_background()
                else:
                    print(f"✗ 图片文件不存在: {self.background_image}")
                    self.apply_default_background()
            else:
                print("使用默认背景")
                self.apply_default_background()

            print("=== 背景应用完成 ===\n")
        except Exception as e:
            print(f"✗ 应用背景失败: {e}")
            import traceback
            traceback.print_exc()
            self.apply_default_background()

    def _darken_color(self, hex_color, factor=0.75):
        
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        r = max(0, min(255, int(r * factor)))
        g = max(0, min(255, int(g * factor)))
        b = max(0, min(255, int(b * factor)))
        return f"#{r:02x}{g:02x}{b:02x}"
    
    def apply_default_background(self):
        
        self.bg_label.hide()
        c1, c2 = '#667eea', '#764ba2'
        c1_d = self._darken_color(c1, 0.75)
        c2_d = self._darken_color(c2, 0.75)
        self.central_widget.setStyleSheet(f"""
            QWidget#central_widget {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {c1}, stop:1 {c2});
            }}
        """)
        self.central_widget.setAutoFillBackground(False)

        if hasattr(self, 'header_frame'):
            self.header_frame.setStyleSheet(f"""
                QFrame {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {c1_d}, stop:1 {c2_d});
                }}
            """)

        if hasattr(self, 'input_frame'):
            self.input_frame.setStyleSheet("""
                QFrame {
                    background-color: rgba(255, 255, 255, 0.88);
                    border-top: 1px solid rgba(0, 0, 0, 0.08);
                }
            """)

        if hasattr(self, 'send_button'):
            self.send_button.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {c1}, stop:1 {c2});
                    color: white; border: none; border-radius: 22px;
                }}
                QPushButton:hover {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {c1_d}, stop:1 {c2_d});
                }}
                QPushButton:pressed {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {self._darken_color(c1, 0.55)}, stop:1 {self._darken_color(c2, 0.55)});
                }}
                QPushButton:disabled {{ background: #cccccc; }}
            """)
    
    def _scale_bg_to_widget(self, pixmap):
        
        if pixmap.isNull():
            return QPixmap()
        dpr = self.devicePixelRatioF()
        dw = max(1, int(self.central_widget.width() * dpr))
        dh = max(1, int(self.central_widget.height() * dpr))

        expanded = pixmap.scaled(dw, dh, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)

        sx = max(0, (expanded.width() - dw) // 2)
        sy = max(0, (expanded.height() - dh) // 2)
        cropped = expanded.copy(sx, sy, dw, dh)
        cropped.setDevicePixelRatio(dpr)
        return cropped

    def resizeEvent(self, event):
        
        super().resizeEvent(event)


        if self.background_type == 'image' and self.background_image:
            if os.path.exists(self.background_image):

                    pixmap = QPixmap(self.background_image)
                    if not pixmap.isNull():

                        scaled_pixmap = self._scale_bg_to_widget(pixmap)

                    self.bg_label.setPixmap(scaled_pixmap)
                    self.bg_label.setGeometry(self.central_widget.rect())
                    self.bg_label.lower()
                    self.central_widget.update()


        if getattr(self, "drop_overlay", None) is not None:
            self.drop_overlay.setGeometry(self.central_widget.rect())



    def showEvent(self, event):




        super().showEvent(event)
        if getattr(self, "_drop_setup_done", False):
            return
        self._drop_setup_done = True
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self.setAcceptDrops(True)

    def eventFilter(self, obj, event):
        et = event.type()
        if et in (QEvent.DragEnter, QEvent.DragMove, QEvent.Drop):

            win = getattr(obj, "window", lambda: None)()
            print("[DROP-DEBUG] type=%s obj=%s win=%s is_self=%s is_cw=%s"
                  % (et, type(obj).__name__,
                     type(win).__name__ if win else None,
                     obj is self, obj is self.central_widget))


            belongs = (obj is self or obj is self.central_widget or
                       (isinstance(obj, QWidget) and win is self))
            if belongs:
                if et == QEvent.DragEnter:
                    self.dragEnterEvent(event)
                elif et == QEvent.DragMove:
                    self.dragMoveEvent(event)
                else:  # Drop
                    self.dropEvent(event)
                print("[DROP-DEBUG] handled, accepted=%s" % event.isAccepted())
                return event.isAccepted()
        return super().eventFilter(obj, event)

    def _is_supported_media(self, path):


        return bool(path) and os.path.isfile(path)

    def dragEnterEvent(self, event):
        md = event.mimeData()
        if md.hasUrls() and any(self._is_supported_media(u.toLocalFile()) for u in md.urls()):
            event.acceptProposedAction()
            if getattr(self, "drop_overlay", None):
                self.drop_hint.setText("松开以加载专属音色\n（拖入任意音频 / 视频，自动降噪）")
                self.drop_progress.hide()
                self.drop_overlay.show()
                self.drop_overlay.raise_()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        md = event.mimeData()
        if md.hasUrls() and any(self._is_supported_media(u.toLocalFile()) for u in md.urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):

        if getattr(self, "_voice_worker", None) and self._voice_worker.isRunning():
            return
        if getattr(self, "drop_overlay", None):
            self.drop_overlay.hide()

    def dropEvent(self, event):
        md = event.mimeData()
        for u in md.urls():
            p = u.toLocalFile()
            if self._is_supported_media(p):
                self._start_voice_setup(p)
                break
        event.acceptProposedAction()


    def _start_voice_setup(self, src):
        if getattr(self, "_voice_worker", None) and self._voice_worker.isRunning():
            return

        if getattr(self, "drop_overlay", None):
            self.drop_hint.setText("正在生成专属音色，请稍候…")
            self.drop_progress.show()
            self.drop_progress.setText("准备中…")
            self.drop_overlay.show()
            self.drop_overlay.raise_()
        self.listen_area.show()
        self.listen_status.setText("正在自动降噪并生成专属音色，请稍候（首次约 1~2 分钟）…")
        self.listen_play_src.setEnabled(False)
        self.listen_play_synth.setEnabled(False)
        self.listen_result.setText("")
        self._src_audio = src
        self._synth_wav = None
        worker = CosyVoicePromptWorker(src, self)
        self._voice_worker = worker
        worker.status_signal.connect(self._on_voice_status)
        worker.finished_signal.connect(self._on_voice_finished)
        worker.error_signal.connect(self._on_voice_error)
        worker.start()

    def _on_voice_status(self, msg):
        self.listen_status.setText(msg)
        if getattr(self, "drop_progress", None):
            self.drop_progress.setText(msg)

    def _on_voice_error(self, msg):
        self.listen_status.setText("❌ " + msg)
        if getattr(self, "drop_progress", None):
            self.drop_progress.setText("❌ " + msg)
        if getattr(self, "drop_overlay", None):
            self.drop_overlay.hide()

    def _on_voice_finished(self, src, synth_wav, prompt_text, transcribe, clear, voice_info):
        self._synth_wav = synth_wav
        self.listen_play_src.setEnabled(bool(src and os.path.exists(src)))
        self.listen_play_synth.setEnabled(
            bool(synth_wav and os.path.exists(synth_wav)))
        verdict = "✅ 清晰" if clear else "⚠️ 不清晰（建议换一段更干净的人声）"
        self.listen_result.setText(
            "参考文字稿：%s\n合成转写：%s\n清晰度：%s"
            % (prompt_text, transcribe, verdict))
        self.listen_status.setText("专属音色已就绪，朗读将自动使用该音色。")
        if getattr(self, "drop_overlay", None):
            self.drop_overlay.hide()


        if voice_info:
            backend = voice_info.get("backend")
            name = voice_info.get("name")
            try:
                if backend == "openvoice":
                    self.speech_engine.set_active_voice({
                        "type": "cloned",
                        "name": name,
                        "se_path": voice_info.get("se_path"),
                        "lang": "zh",
                    })
                else:  # cosyvoice
                    if get_tts_backend() != "cosyvoice":
                        from cosyvoice_tts import set_tts_backend
                        set_tts_backend("cosyvoice")
                    self.speech_engine.set_active_voice({
                        "type": "cosyvoice",
                        "name": name,
                        "prompt_wav": voice_info.get("prompt_wav"),
                        "prompt_text": voice_info.get("prompt_text"),
                    })

                cfg_path = self.get_settings_path()
                cfg = {}
                if os.path.exists(cfg_path):
                    with open(cfg_path, 'r', encoding='utf-8') as f:
                        cfg = json.load(f)
                if backend == "openvoice":
                    cfg['selected_voice'] = {"kind": "cloned", "name": name,
                                             "backend": "openvoice"}
                else:
                    cfg['selected_voice'] = {"kind": "cosyvoice", "name": name,
                                             "backend": "cosyvoice"}
                with open(cfg_path, 'w', encoding='utf-8') as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print("激活克隆音色失败:", e)

            try:
                dlg = getattr(self, "settings_dialog", None)
                if dlg is not None:
                    if hasattr(dlg, "refresh_voice_list"):
                        dlg.refresh_voice_list()
                    label = getattr(dlg, "current_voice_label", None)
                    if label is not None:
                        label.setText("当前音色：%s" % name)
                        label.setStyleSheet(
                            "color: #667eea; font-size: 13px; font-weight: bold;")
            except Exception as e:
                print("刷新设置音色标签失败:", e)

    def _listen_btn_style(self):
        return """
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #667eea,stop:1 #764ba2);
                color: white; border: none; border-radius: 5px;
                font-size: 14px; font-weight: bold; padding: 8px 16px;
            }
            QPushButton:disabled { background: #bbb; }
            QPushButton:hover:!disabled {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #5a7fd6,stop:1 #693d96);
            }
        """

    def create_listen_area(self):
        area = QWidget()
        area.setObjectName("listen_area")
        area.setStyleSheet(
            "QWidget#listen_area { background: rgba(255,255,255,0.94);"
            " border-top: 2px solid #764ba2; }")
        vbox = QVBoxLayout(area)
        vbox.setContentsMargins(16, 12, 16, 12)
        vbox.setSpacing(8)

        title = QLabel("🎧 音色试听与清晰度自检")
        title.setStyleSheet("font-weight: bold; font-size: 15px; color: #444;")
        vbox.addWidget(title)



        rec = QLabel("💡 想让长文本朗读更清晰？照念这段（四声齐全）录 10~15 秒清晰人声，"
                     "再拖入提取音色：\n" + RECOMMENDED_VOICE_TEXT)
        rec.setStyleSheet("color: #5b4bbd; font-size: 12px; background: #f3f0ff; "
                          "padding: 6px 8px; border-radius: 6px;")
        rec.setWordWrap(True)
        vbox.addWidget(rec)

        self.listen_status = QLabel("把音频拖入主界面即可生成专属音色。")
        self.listen_status.setStyleSheet("color: #666; font-size: 13px;")
        self.listen_status.setWordWrap(True)
        vbox.addWidget(self.listen_status)

        btn_row = QWidget()
        hbox = QHBoxLayout(btn_row)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(10)
        self.listen_play_src = QPushButton("▶ 播放原始音频")
        self.listen_play_synth = QPushButton("▶ 播放合成试听")
        self.listen_play_src.setStyleSheet(self._listen_btn_style())
        self.listen_play_synth.setStyleSheet(self._listen_btn_style())
        self.listen_play_src.setEnabled(False)
        self.listen_play_synth.setEnabled(False)
        self.listen_play_src.clicked.connect(self._play_source_audio)
        self.listen_play_synth.clicked.connect(self._play_synth_audio)
        hbox.addWidget(self.listen_play_src)
        hbox.addWidget(self.listen_play_synth)
        hbox.addStretch()
        vbox.addWidget(btn_row)

        self.listen_result = QLabel("")
        self.listen_result.setStyleSheet("color: #333; font-size: 13px;")
        self.listen_result.setWordWrap(True)
        vbox.addWidget(self.listen_result)
        area.hide()
        return area

    def _play_source_audio(self, checked=None):
        src = getattr(self, "_src_audio", None)
        if not src or not os.path.exists(src):
            return
        try:
            if src.lower().endswith(".wav"):
                self.speech_engine.play_preview(src)
            else:
                os.startfile(src)
        except Exception as e:
            print("播放原始音频失败:", e)

    def _play_synth_audio(self, checked=None):
        wav = getattr(self, "_synth_wav", None)
        if not wav or not os.path.exists(wav):
            return
        try:
            self.speech_engine.play_preview(wav)
        except Exception as e:
            print("播放合成试听失败:", e)

    def create_input_area(self):
        
        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(2)


        self.synth_status_label = QLabel("")
        self.synth_status_label.setFont(QFont("Microsoft YaHei", 10))
        self.synth_status_label.setStyleSheet(
            "color: #7a7a9d; padding: 2px 22px 0 22px;"
        )
        vbox.addWidget(self.synth_status_label)


        self.attachments = []
        self.attach_preview = QWidget()
        self.attach_preview.setVisible(False)
        self.attach_preview.setStyleSheet("background: transparent;")
        preview_layout = QHBoxLayout(self.attach_preview)
        preview_layout.setContentsMargins(20, 4, 20, 4)
        preview_layout.setSpacing(8)
        self.attach_preview_layout = preview_layout
        vbox.addWidget(self.attach_preview)

        self.input_frame = QFrame()
        self.input_frame.setMinimumHeight(80)

        layout = QHBoxLayout(self.input_frame)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(10)


        self.input_field = QTextEdit()
        self.input_field.setFont(QFont("Microsoft YaHei", 13))
        self.input_field.setPlaceholderText("输入消息...")
        self.input_field.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.input_field.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.input_field.setAcceptRichText(False)

        self.input_field.setMinimumHeight(45)
        self.input_field.setMaximumHeight(150)
        self.input_field.setStyleSheet("""
            QTextEdit {
                padding: 10px 15px;
                border: 2px solid #e0e0e0;
                border-radius: 25px;
                background-color: white;
                selection-background-color: #d0d0f0;
            }
            QTextEdit:focus {
                border-color: #667eea;
            }
        """)

        self.input_field.keyPressEvent = self._input_key_press

        self.attach_btn = QPushButton("📎")
        self.attach_btn.setFixedSize(45, 45)
        self.attach_btn.setCursor(Qt.PointingHandCursor)
        self.attach_btn.setToolTip("添加图片 / 视频 / 音频 / 文档")
        self.attach_btn.clicked.connect(self._pick_attachments)
        self.attach_btn.setStyleSheet("""
            QPushButton {
                background: #f0f0f5;
                color: #667eea;
                border: none;
                border-radius: 22px;
                font-size: 18px;
            }
            QPushButton:hover { background: #e2e2ee; }
        """)
        layout.addWidget(self.attach_btn)


        self.screen_btn = QPushButton("🖥️")
        self.screen_btn.setFixedSize(45, 45)
        self.screen_btn.setCursor(Qt.PointingHandCursor)
        self.screen_btn.setToolTip("开启/关闭屏幕实时监控（自动截屏并发给 AI）")
        self.screen_btn.clicked.connect(self.toggle_screen_monitor)
        self.screen_btn.setStyleSheet("""
            QPushButton {
                background: #f0f0f5;
                color: #667eea;
                border: none;
                border-radius: 22px;
                font-size: 18px;
            }
            QPushButton:hover { background: #e2e2ee; }
            QPushButton#screen_active {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white;
            }
        """)
        layout.addWidget(self.screen_btn)


        self.screen_pick_btn = QPushButton("🎯")
        self.screen_pick_btn.setFixedSize(30, 30)
        self.screen_pick_btn.setCursor(Qt.PointingHandCursor)
        self.screen_pick_btn.setToolTip("选择要共享的屏幕或窗口")
        self.screen_pick_btn.clicked.connect(self.open_screen_share_dialog)
        self.screen_pick_btn.setStyleSheet("""
            QPushButton {
                background: #f0f0f5;
                color: #667eea;
                border: none;
                border-radius: 15px;
                font-size: 13px;
            }
            QPushButton:hover { background: #e2e2ee; }
        """)
        layout.addWidget(self.screen_pick_btn)

        layout.addWidget(self.input_field)


        self.send_button = QPushButton("发送")
        self.send_button.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        self.send_button.setFixedSize(100, 45)
        self.send_button.setCursor(Qt.PointingHandCursor)
        self.send_button.clicked.connect(self.send_message)
        self.send_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {COLOR1}, stop:1 {COLOR2});
                color: white;
                border: none;
                border-radius: 22px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {COLOR1_DARK}, stop:1 {COLOR2_DARK});
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {COLOR1_DARKER}, stop:1 {COLOR2_DARKER});
            }
            QPushButton:disabled {
                background: #cccccc;
            }
        """)
        layout.addWidget(self.send_button)

        vbox.addWidget(self.input_frame)
        return container

    def _capture_screen_attachment(self):
        
        try:
            from PIL import ImageGrab
        except ImportError:
            QMessageBox.warning(self, "缺少依赖",
                                "屏幕共享需要 Pillow，请先安装：\n"
                                "pip install Pillow")
            return
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(tempfile.gettempdir(),
                                f"screen_share_{timestamp}.png")
        try:
            img = ImageGrab.grab()
            img.save(filename, "PNG")
            self.attachments.append({
                "path": filename,
                "type": "image",
                "name": os.path.basename(filename)
            })
            self._refresh_attach_preview()
        except Exception as e:
            QMessageBox.warning(self, "截图失败", str(e))


    def toggle_screen_monitor(self, source=None):
        

        if self.screen_monitor is not None and self.screen_monitor.running:
            self.screen_monitor.stop()
            return
        self.start_screen_monitor(source)

    def start_screen_monitor(self, source=None):
        

        capture_audio = bool(self.model_caps.get("asr")) or _whisper_available()
        self.screen_monitor = ScreenMonitor(
            self, capture_audio=capture_audio, source=source)
        self.screen_source = source
        self.screen_monitor.frame_ready.connect(self.on_screen_frame)
        self.screen_monitor.error.connect(
            lambda e: QMessageBox.warning(self, "屏幕监控", e))
        self.screen_monitor.state_changed.connect(self._on_monitor_state)
        self.screen_monitor.start()

    def open_screen_share_dialog(self):
        
        dlg = ScreenShareDialog(self)
        if dlg.exec_() == QDialog.Accepted and dlg._selected:

            if self.screen_monitor is not None and self.screen_monitor.running:
                self.screen_monitor.stop()
            self.start_screen_monitor(dlg._selected)

    def _on_monitor_state(self, state):
        
        src_name = ""
        if getattr(self, "screen_source", None) and self.screen_source.get("name"):
            src_name = "（%s）" % self.screen_source["name"]
        if state == "monitoring":
            self.screen_btn.setObjectName("screen_active")
            self.screen_btn.style().polish(self.screen_btn)
            self.synth_status_label.setText(
                "🖥️ 屏幕实时监控中%s…（自动截屏并发给 AI）" % src_name)
        elif state == "audio_unavailable":
            self.synth_status_label.setText(
                "🖥️ 屏幕监控中%s：系统音频不可用，仅发送画面" % src_name)
        elif state == "stopped":
            self.screen_btn.setObjectName("")
            self.screen_btn.style().polish(self.screen_btn)
            self.synth_status_label.setText("屏幕监控已停止")
            self.screen_monitor = None
            self._screen_context = ""
            self._screen_last_spoken = ""
            self._screen_last_spoken_ts = 0.0
            self._screen_last_shown = ""
            self._screen_last_shown_ts = 0.0

    def on_screen_frame(self, image_path, audio_path):
        
        if self._screen_busy:

            for p in (image_path, audio_path):
                if p:
                    try:
                        os.remove(p)
                    except Exception:
                        pass
            return
        self._screen_busy = True
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self.synth_status_label.setText(
            "🖥️ 已截屏，正在发送给 AI（%s）" % now)
        attachments = [{"path": image_path, "type": "image",
                        "name": os.path.basename(image_path)}]
        message = (
            "（这是当前实时屏幕画面）请用你自己的话，简短说出你对「用户此刻在做什么、"
            "关注什么」的理解，就像你作为助手在旁边轻声嘀咕一句。\n"
            "要求：\n"
            "1）不要逐字念屏幕上的文字、字幕或界面文字，要基于你看到的画面做出你自己的"
            "判断和归纳（例如看到代码编辑器加报错，不是念报错内容，而是说「你这段代码报错了，"
            "正在查原因」）；\n"
            "2）用 1 句自然口语（尽量不超过 30 字），像聊天一样，不要写成播报稿或要点列表；\n"
            "3）如果画面和上一次相比没有实质变化，请只回复「（无变化）」四个字，不要重复说同样的话。"
        )

        if audio_path:
            if self.model_caps.get("asr"):
                attachments.append({"path": audio_path, "type": "audio",
                                     "name": os.path.basename(audio_path)})
                message += "\n（另附当前屏幕正在播放的音频，请一并理解其中的语音/内容。）"
            else:
                text = _transcribe_audio_file(audio_path)
                try:
                    os.remove(audio_path)
                except Exception:
                    pass
                if text:
                    message += "\n（屏幕音频本地转写：%s）" % text

        cleanup_paths = [image_path]
        if audio_path and self.model_caps.get("asr"):
            cleanup_paths.append(audio_path)

        self._screen_worker = ChatWorker(message, attachments, emotion=None,
                                         cleanup_paths=cleanup_paths)
        self._screen_worker.response_ready.connect(self.on_screen_response_ready)
        self._screen_worker.start()

    def on_screen_response_ready(self, response, source_tag, speak=False):
        
        self._screen_busy = False
        resp = (response or "").strip()
        if not resp:
            return

        if resp in ("（无变化）", "无变化", "(无变化)"):
            self.synth_status_label.setText("🖥️ 屏幕无变化，继续监控…")
            return

        self._screen_context = resp
        src_name = ""
        if getattr(self, "screen_source", None) and self.screen_source.get("name"):
            src_name = "（%s）" % self.screen_source["name"]
        self.synth_status_label.setText(
            "🖥️ 屏幕理解已更新%s：%s" % (src_name, resp[:40]))

        now = datetime.datetime.now().timestamp()
        is_new = (resp != self._screen_last_shown
                  and (now - self._screen_last_shown_ts) >= 4.0)
        if is_new:
            self._screen_last_shown = resp
            self._screen_last_shown_ts = now








        if (is_new
                and getattr(self, "screen_narrate", True)
                and getattr(self, "voice_enabled", False)
                and getattr(self, "speech_engine", None)
                and self.speech_engine.engine
                and not self.model_caps.get("tts")):
            self._screen_last_spoken = resp
            self._screen_last_spoken_ts = now
            QTimer.singleShot(80, lambda: self.speech_engine.speak(resp))

    def _pick_attachments(self):
        
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择要发送的文件", "",
            "全部支持 (*.png *.jpg *.jpeg *.bmp *.gif *.webp "
            "*.mp4 *.mov *.avi *.mkv *.webm *.flv *.wmv *.m4v "
            "*.mp3 *.wav *.ogg *.m4a *.aac *.flac "
            "*.txt *.md *.pdf *.doc *.docx *.csv *.json *.log);;"
            "图片 (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;"
            "视频 (*.mp4 *.mov *.avi *.mkv *.webm *.flv *.wmv *.m4v);;"
            "音频 (*.mp3 *.wav *.ogg *.m4a *.aac *.flac);;"
            "文档 (*.txt *.md *.pdf *.doc *.docx *.csv *.json *.log);;"
            "所有文件 (*.*)")
        existing = [a["path"] for a in self.attachments]
        for f in files:
            if not f or f in existing:
                continue
            t = _guess_media_type(f)
            self.attachments.append({"path": f, "type": t, "name": os.path.basename(f)})
        self._refresh_attach_preview()

    def _refresh_attach_preview(self):
        
        while self.attach_preview_layout.count():
            item = self.attach_preview_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        if not self.attachments:
            self.attach_preview.setVisible(False)
            return
        self.attach_preview.setVisible(True)
        for idx, att in enumerate(self.attachments):
            t = att.get("type", "file")
            name = att.get("name", "")
            path = att.get("path", "")
            cell = QWidget()
            h = QHBoxLayout(cell)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(4)
            if t == "image" and path and os.path.exists(path):
                thumb = QLabel()
                pix = QPixmap(path).scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                thumb.setPixmap(pix)
                h.addWidget(thumb)
            else:
                icon = {"video": "🎬", "audio": "🎵", "file": "📄", "image": "🖼️"}.get(t, "📎")
                il = QLabel(icon)
                il.setFont(QFont("Microsoft YaHei", 18))
                h.addWidget(il)
            nl = QLabel(name)
            nl.setFont(QFont("Microsoft YaHei", 11))
            nl.setStyleSheet("color: #444; border: none;")
            nl.setMaximumWidth(160)
            nl.setWordWrap(True)
            h.addWidget(nl)
            del_btn = QPushButton("✕")
            del_btn.setFixedSize(20, 20)
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.setToolTip("移除")
            del_btn.clicked.connect(lambda _checked=False, i=idx: self._remove_attachment(i))
            del_btn.setStyleSheet(
                "QPushButton { background: #e74c3c; color: white; border: none;"
                " border-radius: 10px; font-size: 11px; }"
                "QPushButton:hover { background: #c0392b; }")
            h.addWidget(del_btn)
            self.attach_preview_layout.addWidget(cell)

    def _remove_attachment(self, index):
        
        if 0 <= index < len(self.attachments):
            self.attachments.pop(index)
            self._refresh_attach_preview()

    def add_message(self, text, is_user=True, source_tag=None, attachments=None):
        

        try:
            avail = self.chat_scroll.viewport().width() - 60
        except Exception:
            avail = 600
        max_w = max(220, min(600, avail))
        bubble = MessageBubble(text, is_user, source_tag=source_tag,
                               attachments=attachments, max_text_width=max_w)


        container = QFrame()
        container.setStyleSheet("background: transparent; border: none;")
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(0, 5, 0, 5)
        container_layout.setSpacing(0)

        if is_user:

            container_layout.addStretch()
            container_layout.addWidget(bubble)
            container_layout.addSpacing(20)
        else:

            container_layout.addSpacing(20)
            container_layout.addWidget(bubble)
            container_layout.addStretch()

        self.chat_layout.insertWidget(self.chat_layout.count() - 1, container, 0)


        if self.auto_scroll:
            QTimer.singleShot(100, lambda: self.chat_scroll.verticalScrollBar().setValue(
                self.chat_scroll.verticalScrollBar().maximum()))
        return bubble, container

    def add_typing_indicator(self):
        

        self._remove_typing_indicator()
        try:
            avail = self.chat_scroll.viewport().width() - 60
        except Exception:
            avail = 600
        max_w = max(220, min(600, avail))
        bubble = MessageBubble("AI 正在输入…", is_user=False, typing_mode=True,
                               max_text_width=max_w)
        bubble.setStyleSheet("""
            QFrame {
                background-color: #f8f8f8;
                border-radius: 12px;
                border: 1px solid #e0e0e0;
            }
        """)

        container = QFrame()
        container.setStyleSheet("background: transparent; border: none;")
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(0, 5, 0, 5)
        container_layout.setSpacing(0)
        container_layout.addSpacing(20)
        container_layout.addWidget(bubble)
        container_layout.addStretch()

        self.chat_layout.insertWidget(self.chat_layout.count() - 1, container, 0)
        self.typing_bubble = bubble
        self.typing_container = container


        if self.auto_scroll:
            QTimer.singleShot(50, lambda: self.chat_scroll.verticalScrollBar().setValue(
                self.chat_scroll.verticalScrollBar().maximum()))
        return bubble, container

    def _remove_typing_indicator(self):
        
        if self.typing_container is not None:
            try:
                self.chat_layout.removeWidget(self.typing_container)
                self.typing_container.deleteLater()
            except Exception:
                pass
            self.typing_container = None
            self.typing_bubble = None

    def _input_key_press(self, event):
        
        if event.key() == Qt.Key_Return and not event.modifiers() & Qt.ShiftModifier:
            self.send_message()
            return

        QTextEdit.keyPressEvent(self.input_field, event)

    def send_message(self):
        



        if self.worker is not None and self.worker.isRunning():
            print("⚠️ 已有消息正在生成，忽略本次发送（避免并发冲突）")
            return
        message = self.input_field.toPlainText().strip()
        attachments = list(self.attachments)
        if not message and not attachments:
            return


        self.input_field.clear()
        self.attachments = []
        self._refresh_attach_preview()


        self.add_message(message, True, attachments=attachments)


        self.send_button.setEnabled(False)
        self.add_typing_indicator()



        model_message = message
        screen_ctx = getattr(self, "_screen_context", "")
        if screen_ctx:
            model_message = (
                message + "\n\n[屏幕背景（这是你已经掌握的内部信息，只在相关时自然用上，"
                "不要在回复里复述或朗读屏幕内容）]\n" + screen_ctx)


        emotion = self._detect_emotion(message)
        self.worker = ChatWorker(model_message, attachments, emotion=emotion,
                                 speak=True)
        self.worker.response_ready.connect(self.on_response_ready)
        self.worker.partial_ready.connect(self.on_partial)
        self.worker.gen_started.connect(self.on_gen_started)
        self.worker.start()

    def _poll_proactive(self):
        
        try:
            model = self._get_selected_model()
            if not model:
                return
            base = (model.get("base_url", "") or "").rstrip("/")
            if "127.0.0.1:8000" not in base and "localhost:8000" not in base:
                return
            if self.worker is not None and self.worker.isRunning():
                return
            import urllib.request
            url = base + "/主动消息"
            req = urllib.request.Request(url, method="GET",
                                         headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            msgs = data.get("messages") or []
            for m in msgs:
                if m and m.strip():
                    self.add_message(m.strip(), False, source_tag="本地主动")
        except Exception:
            pass

    def on_response_ready(self, response, source_tag, speak=False):
        

        if getattr(self, "_streaming", False):
            if self.voice_enabled and getattr(self, "speech_engine", None) \
                    and self.speech_engine.engine and not self.model_caps.get("tts"):
                try:
                    self.speech_engine.finish_stream_session()
                except Exception:
                    pass
            self._streaming = False


            if self.typing_bubble:
                self._update_streaming_bubble()
                if self.auto_scroll:
                    self.chat_scroll.verticalScrollBar().setValue(
                        self.chat_scroll.verticalScrollBar().maximum())
            self.send_button.setEnabled(True)
            return
        bubble = self.typing_bubble
        container = self.typing_container
        self.typing_bubble = None
        self.typing_container = None


        if bubble is None or container is None:
            self.add_message(response, False, source_tag=source_tag)
            if speak and self.voice_enabled and self.speech_engine.engine and \
                    not self.model_caps.get("tts"):
                QTimer.singleShot(100, lambda: self.speech_engine.speak(response))
            self.send_button.setEnabled(True)
            return


        bubble.set_typing_mode(False)
        bubble.set_text("")
        if source_tag:
            bubble.set_source_tag(source_tag)


        self._typing_text = response
        self._typing_index = 0
        self._typing_bubble = bubble

        def _type_next():
            if not self._typing_bubble:
                return
            idx = self._typing_index
            text = self._typing_text
            if idx < len(text):
                ch = text[idx]
                self._typing_bubble.append_text(ch)
                self._typing_index = idx + 1

                if ch in "。，！？、；：,.!?;:":
                    delay = 120
                elif '\u4e00' <= ch <= '\u9fff':
                    delay = 28
                else:
                    delay = 18
                QTimer.singleShot(delay, _type_next)

                if self.auto_scroll:
                    self.chat_scroll.verticalScrollBar().setValue(
                        self.chat_scroll.verticalScrollBar().maximum())
            else:

                if speak and self.voice_enabled and self.speech_engine.engine and \
                        not self.model_caps.get("tts"):
                    QTimer.singleShot(100, lambda: self.speech_engine.speak(response))
                self.send_button.setEnabled(True)
                self._typing_bubble = None
                self._typing_text = ""
                self._typing_index = 0

        _type_next()

    def on_gen_started(self):
        
        if not getattr(self, "_streaming", False):
            try:
                self.speech_engine.reset_stream_session()
            except Exception:
                pass
        self._streaming = True
        self._partial_text = ""
        self._spoken_len = 0
        self._revealed_len = 0
        self._reveal_active = True
        if self.typing_bubble is None:
            self.add_typing_indicator()
        if self.typing_bubble:
            self.typing_bubble.set_typing_mode(False)
            self.typing_bubble.set_text("")

    def on_partial(self, delta):
        
        if not getattr(self, "_streaming", False):
            self.on_gen_started()
        self._partial_text += delta
        self._update_streaming_bubble()
        self._flush_speak()

    def _speech_will_play(self):
        
        return bool(self.voice_enabled
                    and getattr(self, "speech_engine", None)
                    and self.speech_engine.engine
                    and not self.model_caps.get("tts"))

    def _update_streaming_bubble(self):
        
        if not self.typing_bubble:
            return
        if self._speech_will_play():
            shown = self._partial_text[:max(0, self._revealed_len)]
        else:
            shown = self._partial_text
        self.typing_bubble.set_text(shown)
        if self.auto_scroll:
            self.chat_scroll.verticalScrollBar().setValue(
                self.chat_scroll.verticalScrollBar().maximum())

    def _on_stream_reveal(self, n):
        
        if not getattr(self, "_reveal_active", False):
            return
        self._revealed_len = min(len(self._partial_text),
                                 self._revealed_len + max(0, int(n)))
        self._update_streaming_bubble()

    def _reveal_all_text(self):
        
        if not getattr(self, "_reveal_active", False):
            return
        self._revealed_len = len(self._partial_text)
        self._update_streaming_bubble()
        self._reveal_active = False

    def _flush_speak(self):
        
        if not (self.voice_enabled and getattr(self, "speech_engine", None)
                and self.speech_engine.engine):
            return
        if self.model_caps.get("tts"):
            return
        rest = self._partial_text[self._spoken_len:]
        if not re.search(r"[。！？!?；;]", rest):
            return
        ends = [m.end() for m in re.finditer(r"[。！？!?；;]", rest)]
        cut = ends[-1]
        sentence = rest[:cut]
        self._spoken_len += cut
        try:
            self.speech_engine.append_speak(sentence)
        except Exception as e:
            print("追加朗读失败:", e)

    def on_synth_status(self, msg):
        
        if hasattr(self, "synth_status_label"):
            self.synth_status_label.setText(msg or "")

    def closeEvent(self, event):
        
        if getattr(self, 'tray_icon', None) is not None and self.tray_icon.isVisible():

            if getattr(self, "screen_monitor", None) is not None \
                    and self.screen_monitor.running:
                self.screen_monitor.stop()
            event.ignore()
            self.hide()
            return

        if getattr(self, "screen_monitor", None) is not None \
                and self.screen_monitor.running:
            self.screen_monitor.stop()
            self.screen_monitor.wait()

        if self.speech_engine:
            self.speech_engine.stop()

        if self.worker and self.worker.isRunning():
            self.worker.wait()
        if getattr(self, "_screen_worker", None) and self._screen_worker.isRunning():
            self._screen_worker.wait()
        event.accept()


class BubblePanel(QWidget):
    

    def __init__(self, parent=None):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(0, 0)
        self.setMaximumWidth(520)
        self.tail_dir = "right"
        self._drag_pos = None
        self._drag_start = None
        self._dragging = False
        self._panel_hiding = False
        self._last_ai_text = ""
        self._size_anim = None


        self._tail_anchor_y = 0
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(0)

        container = QWidget()
        container.setObjectName("bubble_container")
        container.setStyleSheet(
            "QWidget#bubble_container {"
            "  background:#1e1e2e;"
            "  border-radius:18px;"
            "}"
        )
        cl = QVBoxLayout(container)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.setSpacing(0)


        self.display = QLabel()
        self.display.setWordWrap(True)
        self.display.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.display.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.display.setStyleSheet(
            "background:transparent; color:#ffffff; border:none;"
            "padding:0px; font-size:25px; line-height:1.5;"
        )


        self.scroll = QScrollArea()
        self.scroll.setWidget(self.display)
        self.scroll.setWidgetResizable(False)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet(
            "QScrollArea{border:none;background:transparent;}"
            "QScrollArea QWidget#qt_scrollarea_viewport{background:transparent;}"
            "QScrollBar:vertical{background:rgba(255,255,255,0.12);width:6px;"
            "border-radius:3px;margin:2px;}"
            "QScrollBar::handle:vertical{background:rgba(255,255,255,0.45);"
            "border-radius:3px;min-height:24px;}"
            "QScrollBar::handle:vertical:hover{background:rgba(255,255,255,0.7);}"
        )
        cl.addWidget(self.scroll)

        root.addWidget(container)


    _WS_RE = __import__("re").compile(r"\s+")

    def _clean_text(self, text):
        
        if not text:
            return ""
        return self._WS_RE.sub(" ", text).strip()

    def _fit_size_to_content(self):
        
        if self._panel_hiding:
            return
        text = self.display.text() or ""

        fm = self.display.fontMetrics()
        char_w = fm.horizontalAdvance("中") or fm.averageCharWidth() or 13
        chars_per_line = 25
        line_w = int(char_w * chars_per_line) + 6


        h_extra = 64
        v_extra = 52

        desired_outer_w = line_w + h_extra


        MIN_W = 260
        new_w = min(self.maximumWidth(), max(MIN_W, desired_outer_w))

        text_w = new_w - h_extra
        text_w = max(60, text_w)

        self.display.setWordWrap(True)
        self.display.setFixedWidth(text_w)


        if text:
            rect = fm.boundingRect(QRect(0, 0, text_w, 99999),
                                   Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop,
                                   text)
            wrapped_h = rect.height()
        else:
            wrapped_h = 0

        wrapped_h = int(wrapped_h * 1.05) + 2


        screen = QApplication.screenAt(self.pos()) or QApplication.primaryScreen()
        avail_h = screen.availableGeometry().height() if screen else 800
        max_h = int(avail_h * 0.6)

        self.display.setFixedHeight(max(wrapped_h, 1))
        new_h = min(max_h, max(0, wrapped_h + v_extra))


        cur = self.size()
        if abs(cur.width() - new_w) <= 1 and abs(cur.height() - new_h) <= 1:
            return

        self.setFixedSize(new_w, new_h)
        self.update()

        fw = getattr(self, 'floating', None)
        if isinstance(fw, FloatingWindow):
            fw._reposition_panel()

    def show_streaming_text(self, text):
        
        if getattr(self, '_type_timer', None) is not None:
            self._type_timer.stop()
        text = self._clean_text(text)
        self.display.setText(text)
        self._fit_size_to_content()

    def _on_response(self, response, source_tag, speak=False):
        print("AI 回复：", response[:80], "..." if len(response) > 80 else "")
        self._append_ai(response, source_tag)
        mw = self.floating.main_window
        if speak and mw and getattr(mw, 'speech_engine', None):
            if mw.model_caps.get("tts"):
                print("当前模型声明内置 TTS，跳过本地朗读（由模型输出语音）")
            else:
                try:
                    mw.speech_engine.speak(response)
                    print("已触发本地语音朗读")
                except Exception as e:
                    print(f"语音朗读失败: {e}")
        elif speak:
            print("未触发朗读：speech_engine 未就绪或不存在")

    def _append_ai(self, response, source_tag):
        response = self._clean_text(response)
        self._last_ai_text = response
        self._type_full = response
        self._type_idx = 0
        if getattr(self, '_type_timer', None) is not None:
            self._type_timer.stop()
        self._type_timer = QTimer(self)
        self._type_timer.timeout.connect(self._type_step)
        self._type_timer.start(22)

    def _type_step(self):
        if self._type_idx < len(self._type_full):
            self._type_idx += 1
            self.display.setText(self._type_full[:self._type_idx])
            self._fit_size_to_content()
        else:
            if getattr(self, '_type_timer', None) is not None:
                self._type_timer.stop()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect().adjusted(2, 2, -2, -2))
        radius = 16
        tail = 12
        path = QPainterPath()

        if self.tail_dir == "down":
            body = QRectF(rect.adjusted(0, 0, 0, -tail))
            path.addRoundedRect(body, radius, radius)
            cx = rect.center().x()
            by = rect.bottom() - tail
            polygon = QPolygonF([
                QPointF(cx - 8, by),
                QPointF(cx + 8, by),
                QPointF(cx, by + tail)
            ])
            path.addPolygon(polygon)
        elif self.tail_dir == "up":
            body = QRectF(rect.adjusted(0, tail, 0, 0))
            path.addRoundedRect(body, radius, radius)
            cx = rect.center().x()
            ty = rect.top() + tail
            polygon = QPolygonF([
                QPointF(cx - 8, ty),
                QPointF(cx + 8, ty),
                QPointF(cx, ty - tail)
            ])
            path.addPolygon(polygon)
        elif self.tail_dir == "left":
            body = QRectF(rect.adjusted(tail, 0, 0, 0))
            path.addRoundedRect(body, radius, radius)
            cy = rect.center().y()
            lx = rect.left() + tail
            polygon = QPolygonF([
                QPointF(lx, cy - 8),
                QPointF(lx, cy + 8),
                QPointF(lx - tail, cy)
            ])
            path.addPolygon(polygon)
        elif self.tail_dir == "right":
            body = QRectF(rect.adjusted(0, 0, -tail, 0))
            path.addRoundedRect(body, radius, radius)


            cy = self._tail_anchor_y - self.y()
            cy = max(rect.top() + tail + 2, min(rect.bottom() - tail - 2, cy))
            rx = rect.right() - tail
            polygon = QPolygonF([
                QPointF(rx, cy - 8),
                QPointF(rx, cy + 8),
                QPointF(rx + tail, cy)
            ])
            path.addPolygon(polygon)
        else:
            path.addRoundedRect(rect, radius, radius)

        painter.fillPath(path, QBrush(QColor("#1e1e2e")))
        painter.end()


    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.globalPos()
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and (event.buttons() & Qt.LeftButton):
            if (event.globalPos() - self._drag_start).manhattanLength() > 10:
                self._dragging = True
            if self._dragging:
                self.move(event.globalPos() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self._dragging = False
        super().mouseReleaseEvent(event)




class EmotionAnalyzer:
    


    LEXICON = {
        "开心": ["开心", "高兴", "快乐", "喜欢", "爱", "哈哈", "嘻嘻", "兴奋", "棒", "赞",
                "好耶", "满意", "感谢", "谢谢", "漂亮", "可爱", "幸福", "爽", "美滋滋", "好喜欢",
                "happy", "great", "good", "love", "like", "excited", "awesome", "lol",
                "haha", "nice", "😊", "😄", "😁", "❤", "💕", "👍"],
        "悲伤": ["难过", "伤心", "哭", "悲伤", "难受", "寂寞", "孤独", "想哭", "沮丧",
                "失望", "遗憾", "心碎", "sad", "cry", "upset", "lonely", "miss", "depressed",
                "😢", "😭", "💔"],
        "愤怒": ["生气", "愤怒", "讨厌", "烦", "气死", "可恶", "混蛋", "滚", "恨", "骂",
                "怒", "烦人", "angry", "hate", "annoyed", "mad", "damn", "shit", "😡", "💢"],
        "恐惧": ["害怕", "恐惧", "吓", "担心", "怕", "恐怖", "惊慌", "紧张", "焦虑",
                "afraid", "scared", "fear", "worry", "nervous", "panic", "😨", "😱"],
        "惊讶": ["惊讶", "震惊", "不敢相信", "哇", "天哪", "居然", "竟然", "意外", "绝了",
                "wow", "omg", "surprised", "shock", "what", "😮", "😲"],
    }


    _HF_LABEL_MAP = {
        "joy": "开心", "sadness": "悲伤", "anger": "愤怒",
        "fear": "恐惧", "surprise": "惊讶", "love": "开心",
        "neutral": "中性", "LABEL_0": "中性", "LABEL_1": "开心",
        "LABEL_2": "悲伤", "LABEL_3": "愤怒", "LABEL_4": "恐惧",
        "LABEL_5": "惊讶", "LABEL_6": "中性",
    }

    def __init__(self):
        self._hf_loaded = False
        self._hf_pipeline = None
        self._hf_path = os.environ.get("EMOTION_HF_MODEL", "").strip()
        self._want_hf = bool(self._hf_path)

    def _load_hf(self):
        
        if self._hf_loaded:
            return self._hf_pipeline
        self._hf_loaded = True
        if not self._want_hf:
            return None
        try:
            from transformers import pipeline  # type: ignore
            self._hf_pipeline = pipeline(
                "text-classification", model=self._hf_path)
            print("情感识别：已加载本地神经网络模型", self._hf_path)
        except Exception as e:
            print("情感识别：本地神经网络模型加载失败，回退词典：", e)
            self._hf_pipeline = None
        return self._hf_pipeline

    def analyze(self, text):
        
        if not text or not text.strip():
            return ("中性", 0.0, "lexicon")

        pl = self._load_hf()
        if pl is not None:
            try:
                res = pl(text[:512])[0]
                label = self._HF_LABEL_MAP.get(res["label"], res["label"])
                return (label, float(res["score"]), "hf")
            except Exception:
                pass

        counts = {cat: 0 for cat in self.LEXICON}
        low = text.lower()
        for cat, words in self.LEXICON.items():
            for w in words:
                if w in low:
                    counts[cat] += 1
        total = sum(counts.values())
        if total == 0:
            return ("中性", 0.0, "lexicon")
        best = max(counts, key=lambda c: counts[c])
        score = counts[best] / total
        return (best, min(1.0, score), "lexicon")



_whisper_models = {}


def _load_whisper_model(name="base"):
    
    import whisper  # noqa: F401
    if name not in _whisper_models:
        _whisper_models[name] = whisper.load_model(name)
    return _whisper_models[name]


def _whisper_available():
    try:
        import whisper  # noqa: F401
        return True
    except Exception:
        return False



_WHISPER_INITIAL_PROMPT = (
    "以下是中文普通话的日常对话语音转写，口语化，请结合上下文准确识别同音字与语义。"
)


def _pick_whisper_size():
    
    cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "whisper")
    small = os.path.join(cache_dir, "small.pt")
    if os.path.exists(small) and os.path.getsize(small) > 100_000_000:
        return "small"
    return "base"


def _transcribe_audio_file(path, language="zh"):
    
    try:
        model = _load_whisper_model(_pick_whisper_size())
        result = model.transcribe(
            path, language=language, fp16=False,
            initial_prompt=_WHISPER_INITIAL_PROMPT,
            condition_on_previous_text=False)
        return (result.get("text") or "").strip()
    except Exception as e:
        print("whisper 转写失败:", e)
        return ""


def _denoise_for_asr(src_path):
    
    try:
        import shutil
        from tts_audio_utils import denoise_output
        tmp = tempfile.mktemp(suffix=".wav")
        shutil.copyfile(src_path, tmp)
        out = denoise_output(tmp)
        if out and os.path.exists(out) and os.path.getsize(out) > 0:
            return out
        return src_path
    except Exception as e:
        print("[ASR] 降噪失败，回退原声：", repr(e))
        return src_path


class ScreenMonitor(QThread):
    


    frame_ready = pyqtSignal(str, object)
    error = pyqtSignal(str)
    state_changed = pyqtSignal(str)  # "monitoring" / "stopped" / "error:..."

    def __init__(self, parent=None, interval_ms=3000, capture_audio=False, source=None):
        super().__init__(parent)
        self.running = False
        self._lock = threading.Lock()
        self._stop_requested = False
        self.interval_ms = interval_ms

        self.capture_audio = capture_audio


        self.source = source
        self.audio_min_rms = 200
        self.audio_unsupported = False
        self._audio_stream = None
        self._audio_buffer = []
        self._audio_lock = threading.Lock()
        self._audio_sr = 16000

    def stop(self):
        with self._lock:
            self._stop_requested = True

    def _should_stop(self):
        with self._lock:
            return self._stop_requested

    def _current_region(self):
        
        if not self.source:
            return None
        try:
            if self.source["type"] == "screen":
                scr = QApplication.screens()[self.source["index"]]
                g = scr.geometry()
                return (g.x(), g.y(), g.x() + g.width(), g.y() + g.height())
            elif self.source["type"] == "window":
                import pygetwindow as gw
                matches = [w for w in gw.getWindowsWithTitle(self.source["title"])
                           if w.title == self.source["title"]]
                if matches:
                    w = matches[0]
                    return (w.left, w.top, w.left + w.width, w.top + w.height)
        except Exception as e:
            print("计算共享区域失败，回退全屏：%s" % e)
        return None


    def _find_loopback_device(self):
        
        try:
            import sounddevice as sd
            default = sd.default.device  # (input_index, output_index)
            out_idx = default[1]
            devs = sd.query_devices()
            if isinstance(out_idx, int) and 0 <= out_idx < len(devs):
                return out_idx
        except Exception:
            pass
        return None

    def _start_audio_capture(self):
        
        self._audio_error_msg = None
        try:
            import sounddevice as sd
            import numpy as np
        except ImportError as e:
            self._audio_error_msg = "缺少 sounddevice（pip install sounddevice）"
            self.audio_unsupported = True
            return False
        dev = self._find_loopback_device()
        if dev is None:
            self._audio_error_msg = "未找到可回环的音频输出设备"
            self.audio_unsupported = True
            return False
        self._sd = sd
        self._np = np
        self._audio_buffer = []
        extra = None
        try:
            extra = sd.WasapiSettings(loopback=True)
        except Exception:
            extra = None

        for ch in (1, 2):
            try:
                self._audio_stream = sd.InputStream(
                    device=dev, samplerate=self._audio_sr, channels=ch,
                    blocksize=2048, dtype='int16',
                    callback=self._audio_callback, extra_settings=extra)
                self._audio_stream.start()
                return True
            except Exception as e:
                self._audio_error_msg = str(e)
                try:
                    self._audio_stream = None
                except Exception:
                    pass
        self.audio_unsupported = True
        return False

    def _audio_callback(self, indata, frames, time_info, status):
        try:
            with self._audio_lock:
                self._audio_buffer.append(indata.copy())
        except Exception as e:
            if not getattr(self, '_warned_acb', False):
                self._warned_acb = True
                print("【屏幕音频】回调写入缓冲失败：", repr(e))

    def _collect_audio_chunk(self):
        
        with self._audio_lock:
            chunks = self._audio_buffer
            self._audio_buffer = []
        if not chunks:
            return None
        try:
            np = self._np
            audio = np.concatenate(chunks, axis=0)
        except Exception:
            return None

        max_len = int(self._audio_sr * (self.interval_ms / 1000.0 + 1.0))
        if len(audio) > max_len:
            audio = audio[-max_len:]
        try:
            rms = float(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))
        except Exception as e:
            if not getattr(self, '_warned_srms', False):
                self._warned_srms = True
                print("【屏幕音频】RMS 计算失败，按 0 处理：", repr(e))
            rms = 0.0
        if rms < self.audio_min_rms:
            return None
        try:
            import wave
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            path = os.path.join(tempfile.gettempdir(),
                                f"screen_audio_{ts}.wav")
            with wave.open(path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self._audio_sr)
                wf.writeframes(audio.tobytes())
            return path
        except Exception as e:
            self.error.emit("保存音频失败：%s" % e)
            return None

    def _stop_audio_capture(self):
        try:
            if self._audio_stream is not None:
                self._audio_stream.stop()
                self._audio_stream.close()
                self._audio_stream = None
        except Exception:
            pass

    def run(self):
        try:
            from PIL import ImageGrab
        except ImportError:
            self.error.emit("缺少依赖：屏幕监控需要 Pillow，请先安装 pip install Pillow")
            self.state_changed.emit("error:no_pillow")
            return

        audio_ok = False
        if self.capture_audio:
            audio_ok = self._start_audio_capture()
            if not audio_ok:
                print("系统音频捕获不可用：%s，屏幕监控将只发送画面。"
                      % (self._audio_error_msg or "未知原因"))
                self.state_changed.emit("audio_unavailable")
        self.running = True
        self.state_changed.emit("monitoring")
        try:
            while not self._should_stop():
                img_path = None
                audio_path = None
                try:
                    region = self._current_region()
                    img = ImageGrab.grab(bbox=region) if region else ImageGrab.grab()

                    max_w = 1280
                    if img.width > max_w:
                        ratio = max_w / img.width
                        img = img.resize((max_w, int(img.height * ratio)))
                    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                    img_path = os.path.join(tempfile.gettempdir(),
                                            f"screen_monitor_{ts}.png")
                    img.save(img_path, "PNG")
                    if audio_ok:
                        audio_path = self._collect_audio_chunk()
                except Exception as e:
                    print("【屏幕监控】截屏失败：", repr(e))
                    self.error.emit("截屏失败：%s" % e)
                if img_path:
                    self.frame_ready.emit(img_path, audio_path)

                waited = 0
                step = 100
                while waited < self.interval_ms and not self._should_stop():
                    self.msleep(step)
                    waited += step
        finally:
            self._stop_audio_capture()
            self.running = False
            self.state_changed.emit("stopped")


class ScreenShareDialog(QDialog):
    

    source_selected = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowStaysOnTopHint)
        self.setWindowTitle("屏幕共享")
        self.setMinimumWidth(560)
        self.setMinimumHeight(380)
        self._selected = None
        self._card_count = 0
        self.setStyleSheet(
            "QDialog { background:#15151f; border-radius:12px; }"
            "QLabel { color:#e8e8f0; }"
            "QPushButton { background:#2a2a3a; color:#fff; border:none;"
            " border-radius:8px; padding:8px 18px; font-size:13px; }"
            "QPushButton:hover { background:#3a3a52; }"
            "QPushButton:disabled { background:#444; color:#999; }"
            "QScrollArea { border:none; background:transparent; }"
        )
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        title = QLabel("选择共享的屏幕")
        title.setStyleSheet("font-size:16px; font-weight:bold;")
        root.addWidget(title)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.grid = QWidget()
        self.grid_layout = QGridLayout(self.grid)
        self.grid_layout.setSpacing(12)
        self.scroll.setWidget(self.grid)
        root.addWidget(self.scroll, 1)


        for i, scr in enumerate(QApplication.screens()):
            name = "主屏幕" if i == 0 else "屏幕 %d" % (i + 1)
            self._add_card("screen", name, i, scr.geometry())


        self._more_btn = QPushButton("展开更多")
        self._more_btn.setStyleSheet(
            "QPushButton { background:transparent; color:#8aa4ff; padding:4px 0; }"
            "QPushButton:hover { color:#aabbff; }")
        self._more_btn.clicked.connect(self._expand_windows)
        root.addWidget(self._more_btn)


        bottom = QHBoxLayout()
        bottom.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        self.ok_btn = QPushButton("开始共享")
        self.ok_btn.setEnabled(False)
        self.ok_btn.clicked.connect(self._on_ok)
        bottom.addWidget(cancel)
        bottom.addWidget(self.ok_btn)
        root.addLayout(bottom)

    def _add_card(self, stype, name, index, geometry):
        card = QPushButton()
        card.setFixedSize(220, 150)
        card.setCheckable(True)
        card.setStyleSheet(
            "QPushButton { background:#23232f; border:2px solid transparent;"
            " border-radius:10px; color:#cfcfe0; font-size:12px;"
            " text-align:bottom; padding:6px; }"
            "QPushButton:checked { border:2px solid #667eea; }")
        try:
            from PIL import ImageGrab
            bbox = (geometry.x(), geometry.y(),
                    geometry.x() + geometry.width(),
                    geometry.y() + geometry.height())
            shot = ImageGrab.grab(bbox=bbox).resize((208, 110))
            card.setIcon(QIcon(self._pil_to_pixmap(shot)))
            card.setIconSize(QSize(208, 110))
        except Exception as e:
            print("屏幕缩略图失败：%s" % e)
        card.setText(name)
        card.toggled.connect(
            lambda checked, idx=index, t=stype, n=name:
            self._on_toggled(checked, idx, t, n, None))
        row = self._card_count // 2
        col = self._card_count % 2
        self._card_count += 1
        self.grid_layout.addWidget(card, row, col)

    def _expand_windows(self):
        self._more_btn.setEnabled(False)
        self._more_btn.setText("正在加载窗口…")
        try:
            import pygetwindow as gw
        except ImportError:
            self._more_btn.setText("未安装 pygetwindow（pip install pygetwindow）")
            return
        try:
            wins = [w for w in gw.getAllWindows()
                    if w.title and w.width > 60 and w.height > 60][:12]
            for w in wins:
                card = QPushButton()
                card.setFixedSize(220, 150)
                card.setCheckable(True)
                card.setStyleSheet(
                    "QPushButton { background:#23232f; border:2px solid transparent;"
                    " border-radius:10px; color:#cfcfe0; font-size:12px;"
                    " text-align:bottom; padding:6px; }"
                    "QPushButton:checked { border:2px solid #667eea; }")
                try:
                    from PIL import ImageGrab
                    bbox = (w.left, w.top, w.left + w.width, w.top + w.height)
                    shot = ImageGrab.grab(bbox=bbox).resize((208, 110))
                    card.setIcon(QIcon(self._pil_to_pixmap(shot)))
                    card.setIconSize(QSize(208, 110))
                except Exception:
                    pass
                card.setText(w.title[:24])
                card.toggled.connect(
                    lambda checked, win=w:
                    self._on_toggled(checked, None, "window", win.title, win.title))
                row = self._card_count // 2
                col = self._card_count % 2
                self._card_count += 1
                self.grid_layout.addWidget(card, row, col)
            self._more_btn.hide()
        except Exception as e:
            self._more_btn.setText("加载窗口失败：%s" % e)

    def _on_toggled(self, checked, index, stype, name, title):
        sender = self.sender()
        if checked:
            for c in self.grid.findChildren(QPushButton):
                if c is not sender:
                    c.setChecked(False)
            self._selected = {"type": stype, "index": index,
                              "title": title, "name": name}
            self.ok_btn.setEnabled(True)
        else:
            if (self._selected and self._selected.get("type") == stype and
                    self._selected.get("name") == name):
                self._selected = None
                self.ok_btn.setEnabled(False)

    @staticmethod
    def _pil_to_pixmap(img):
        if img.mode != "RGB":
            img = img.convert("RGB")
        w, h = img.size
        qimg = QImage(img.tobytes("raw", "RGB"), w, h, w * 3,
                      QImage.Format_RGB888)
        return QPixmap.fromImage(qimg)

    def _on_ok(self):
        if self._selected:
            self.source_selected.emit(self._selected)
            self.accept()


from voice_id import (speaker_verdict, reset_speaker_profile,
                      speaker_profile_status)


def _analyze_voice_tone(wav_path):
    
    try:
        import wave
        import struct
        import math
        with wave.open(wav_path, 'rb') as wf:
            nch = wf.getnchannels()
            sw = wf.getsampwidth()
            fr = wf.getframerate()
            nframes = wf.getnframes()
            raw = wf.readframes(nframes)
        if sw == 2:
            count = len(raw) // 2
            samples = struct.unpack('<' + 'h' * count, raw)
            maxv = 32768.0
        elif sw == 1:
            count = len(raw)
            samples = struct.unpack('<' + 'B' * count, raw)
            maxv = 128.0
        else:
            return ''
        if nch == 2:
            samples = samples[0::2]
        if not samples:
            return ''
        sq = sum(s * s for s in samples) / len(samples)
        rms = math.sqrt(sq) / maxv
        dur = nframes / float(fr) if fr else 0

        win = max(1, int(fr * 0.02))
        low = total = 0
        for i in range(0, len(samples) - win, win):
            seg = samples[i:i + win]
            sr2 = math.sqrt(sum(x * x for x in seg) / len(seg)) / maxv
            total += 1
            if sr2 < 0.02:
                low += 1
        pause = (low / total) if total else 0
        vol = "音量较大" if rms > 0.15 else ("音量偏小" if rms < 0.05 else "音量适中")
        if pause > 0.4:
            pace = "停顿较多，听起来有些犹豫或在思考"
        elif pause < 0.15:
            pace = "语流连贯、节奏偏快"
        else:
            pace = "语速平稳"
        return (f"用户语音特征：{vol}，{pace}（录音约{dur:.1f}秒）。"
                f"请据此调整你回应的语气与节奏。")
    except Exception as e:
        print("语音语气分析失败：", e)
        return ''


class VoiceListener(QThread):
    

    text_ready = pyqtSignal(str, str)
    audio_ready = pyqtSignal(str, str)
    user_started_speaking = pyqtSignal()
    voice_ignored = pyqtSignal(str)
    state_changed = pyqtSignal(str)  # idle/listening/transcribing/...

    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = False
        self._lock = threading.Lock()
        self._should_reset = False
        self.sample_rate = 16000
        self.channels = 1
        self._input_device_index = None
        self.format = None
        self.chunk = 1024
        self.silence_threshold = 250
        self.noise_floor = 0.0
        self._ambient_history = []
        self._ambient_window = 30
        self._consecutive_over = 0
        self._trigger_required = 5
        self.silence_seconds = 0.8
        self.min_speech_seconds = 0.5
        self.max_record_seconds = 30
        self.whisper_model = None
        self.model_handles_asr = False


        self._vad_enabled = False
        self._vad_model = None
        self._vad_pcm = None
        self._vad_speaking = False
        self._vad_speech_run = 0
        self._vad_silence_run = 0
        self._vad_start_windows = 3
        self._vad_end_windows = 62


        self.suppress = False





        self.ai_playing = False
        self._barge_mode = False



        self._ambient_floor = 0.0
        self._recent_level = 0.0
        self._echo_floor = 0.0
        self._echo_peak = 0.0
        self._barge_hold = 0
        self._barge_threshold = 450.0
        self._barge_hold_frames = 4
        self._barge_guard_until = 0.0
        self._barge_guard_seconds = 0.9
        self._barge_detected = False
        self._last_barge_in = False
        self._barge_skip_ms = 60
        self._barge_cooldown_until = 0.0


        self._barge_spk_checked = False
        self._barge_spk_ok = False

        self._mic_ring = None
        self._mic_ring_cap = int(16000 * 1.0)

    def _probe_default_input_device(self, pa):
        
        try:
            info = pa.get_default_input_device_info()
            idx = info.get('index')
            channels = int(info.get('maxInputChannels', 1))
            sr = int(info.get('defaultSampleRate', 16000))

            if channels < 1:
                channels = 1
            if channels > 2:
                channels = 2
            if sr < 8000:
                sr = 16000
            if sr > 96000:
                sr = 48000
            self._input_device_index = idx
            self.channels = channels
            self.sample_rate = sr
            name = info.get('name', 'Unknown')
            print("探测到默认麦克风：index=%s, name='%s', channels=%d, sample_rate=%d"
                  % (idx, name, channels, sr))
            return True
        except Exception as e:
            print("探测默认麦克风失败：", e)
            self._input_device_index = None
            self.channels = 1
            self.sample_rate = 16000
            return False

    def _load_whisper(self):
        if self.model_handles_asr:

            return True
        if self.whisper_model is not None:
            return True
        try:
            self.state_changed.emit("loading_model")
            self.whisper_model = _load_whisper_model(_pick_whisper_size())
            self.state_changed.emit("model_ready")
            return True
        except Exception as e:
            print(f"加载 whisper 失败: {e}")
            self.state_changed.emit(f"model_error:{e}")
            return False

    def reset(self):
        with self._lock:
            self._should_reset = True

    def _check_reset(self):
        with self._lock:
            if self._should_reset:
                self._should_reset = False
                return True
        return False

    def set_suppress(self, val):
        
        val = bool(val)
        if val == self.suppress:
            return
        self.suppress = val
        if val:

            import numpy as np
            self._vad_speaking = False
            self._vad_speech_run = 0
            self._vad_silence_run = 0
            if self._vad_enabled and self._vad_model is not None:
                try:
                    self._vad_model.reset_states()
                except Exception as e:
                    print("【VAD】reset_states 失败：", repr(e))
                self._vad_pcm = np.zeros(0, dtype=np.float32)
            print("[屏蔽] AI 朗读中，麦克风已屏蔽，不会把 AI 的声音当输入")
        else:
            print("[屏蔽] AI 朗读结束，麦克风已恢复监听")

    def _resample_to_16k_mono(self, frames):
        
        import numpy as np
        raw = b''.join(frames)
        if not raw:
            return b''
        arr = np.frombuffer(raw, dtype=np.int16)
        if self.channels > 1:
            valid_len = (len(arr) // self.channels) * self.channels
            arr = arr[:valid_len].reshape(-1, self.channels)
            arr = arr.mean(axis=1).astype(np.int16)
        if self.sample_rate != 16000:
            ratio = self.sample_rate / 16000.0
            n_out = max(1, int(len(arr) / ratio))
            idx = np.linspace(0, len(arr) - 1, n_out)
            arr = np.interp(idx, np.arange(len(arr)), arr).astype(np.int16)
        return arr.tobytes()

    def _to_16k_mono_float(self, data):
        
        import numpy as np
        if not data:
            return np.zeros(0, dtype=np.float32)
        arr = np.frombuffer(data, dtype=np.int16)
        if self.channels > 1:
            valid = (len(arr) // self.channels) * self.channels
            arr = arr[:valid].reshape(-1, self.channels).mean(axis=1)
        arr = arr.astype(np.float32)
        if self.sample_rate != 16000:
            ratio = self.sample_rate / 16000.0
            n_out = max(1, int(len(arr) / ratio))
            idx = np.linspace(0, len(arr) - 1, n_out)
            arr = np.interp(idx, np.arange(len(arr)), arr)
        return (arr / 32768.0).astype(np.float32)

    def _load_vad(self):
        
        try:
            import sys
            import types



            if 'torchaudio' not in sys.modules:
                _ta = types.ModuleType('torchaudio')
                _ta.__version__ = '0.0.0'
                sys.modules['torchaudio'] = _ta
            import numpy as np  # noqa: F401
            import torch
            from silero_vad import load_silero_vad
            self._vad_model = load_silero_vad()
            self._vad_model.eval()
            self._vad_enabled = True
            self._vad_pcm = np.zeros(0, dtype=np.float32)
            self._vad_speaking = False
            self._vad_speech_run = 0
            self._vad_silence_run = 0

            self._vad_start_windows = 3
            self._vad_end_windows = max(20, int(self.silence_seconds / 0.032))
            print("VAD 模型加载成功（silero-vad），将用真正人声检测替代纯能量阈值")
            return True
        except Exception as e:
            self._vad_enabled = False
            self._vad_model = None
            print("[VAD] 加载失败，回退到 RMS 能量阈值：", repr(e))
            return False

    def _feed_vad(self, pcm16k):
        
        import numpy as np
        if not self._vad_enabled or self._vad_model is None:
            return self._vad_speaking
        import torch
        self._vad_pcm = np.concatenate([self._vad_pcm, pcm16k])
        win = 512
        while len(self._vad_pcm) >= win:
            chunk = self._vad_pcm[:win]
            self._vad_pcm = self._vad_pcm[win:]
            t = torch.from_numpy(chunk).unsqueeze(0)
            with torch.no_grad():
                prob = self._vad_model(t, 16000).item()
            if prob >= 0.5:
                self._vad_speech_run += 1
                self._vad_silence_run = 0
            else:
                self._vad_silence_run += 1
                self._vad_speech_run = 0
            if not self._vad_speaking and self._vad_speech_run >= self._vad_start_windows:
                self._vad_speaking = True
            if self._vad_speaking and self._vad_silence_run >= self._vad_end_windows:
                self._vad_speaking = False
        return self._vad_speaking

    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    def feed_ai_audio(self, wav_path):
        
        if not wav_path:
            return

        self._barge_guard_until = time.time() + self._barge_guard_seconds
        self._barge_detected = False
        self._barge_hold = 0

        self._barge_spk_checked = False
        self._barge_spk_ok = False

    def set_ai_playing(self, val):
        
        val = bool(val)
        self.ai_playing = val
        self._barge_mode = val
        if val:

            self.suppress = True
            self._ambient_floor = 0.0
            self._recent_level = 0.0
            self._echo_floor = 0.0
            self._echo_peak = 0.0
            self._barge_hold = 0
            self._barge_detected = False
            self._last_barge_in = False
            self._barge_echo_floor = 0.0
            self._barge_cooldown_until = 0.0
            self._barge_spk_checked = False
            self._barge_spk_ok = False
            self._mic_ring = None
            self._barge_guard_until = time.time() + self._barge_guard_seconds
        else:

            self.suppress = False
            self._ambient_floor = 0.0
            self._recent_level = 0.0
            self._echo_floor = 0.0
            self._echo_peak = 0.0
            self._barge_hold = 0
            self._barge_detected = False
            self._last_barge_in = False
            self._barge_echo_floor = 0.0
            self._barge_cooldown_until = 0.0
            self._barge_spk_checked = False
            self._barge_spk_ok = False

    def _barge_in_detect(self, tnow, rms, vad_speaking):
        

        if tnow < self._barge_guard_until or tnow < self._barge_cooldown_until:
            return False, False


        if self._ambient_floor <= 0:
            self._ambient_floor = rms
            self._recent_level = rms
        else:
            if rms > self._ambient_floor:

                self._ambient_floor = self._ambient_floor * 0.85 + rms * 0.15
            else:


                self._ambient_floor = self._ambient_floor * 0.999 + rms * 0.001

        self._recent_level = self._recent_level * 0.9 + rms * 0.1

        self._echo_floor = self._ambient_floor
        self._echo_peak = max(self._ambient_floor, rms)

        floor_cap = max(self.noise_floor * 2.0, 80.0)
        if self._ambient_floor < floor_cap:
            self._ambient_floor = floor_cap


        if self._barge_detected:
            return False, True


        excess = rms - self._ambient_floor
        rel_ratio = (excess / self._ambient_floor) if self._ambient_floor > 0 else 0.0
        onset = rms - self._recent_level
        onset_ratio = (onset / self._recent_level) if self._recent_level > 0 else 0.0

        ambient_factor = 1.6 if self._ambient_floor < 800 else 2.2
        threshold = max(self._barge_threshold,
                        self._ambient_floor * (ambient_factor - 1.0),
                        self.noise_floor * 3.0)
        is_candidate = (vad_speaking and
                        excess > threshold and
                        rms > self._ambient_floor * ambient_factor and
                        onset > self._barge_threshold and
                        onset_ratio > 0.8 and
                        rms > self.noise_floor * 4.0)

        if not is_candidate:
            self._barge_hold = max(0, self._barge_hold - 1)

            if self._barge_hold == 0:
                self._barge_spk_checked = False
                self._barge_spk_ok = False
            return False, False


        if not self._barge_spk_checked:
            self._barge_spk_checked = True
            self._barge_spk_ok = self._verify_barge_speaker()
        if not self._barge_spk_ok:

            self._barge_hold = 0
            print("[插话] 候选被说话人验证拒绝（疑似视频/旁人声音，未打断）")
            return False, False


        self._barge_hold += 1
        if self._barge_hold >= self._barge_hold_frames:
            self._barge_detected = True
            self._last_barge_in = True
            self._barge_echo_floor = self._ambient_floor
            self.suppress = False
            self._barge_cooldown_until = tnow + 1.0
            print("[插话] AI 朗读中检测到【你】插话（RMS=%.1f 基线=%.1f 超额=%.1f），打断 AI"
                  % (rms, self._ambient_floor, excess))
            return True, True
        return False, False

    def _verify_barge_speaker(self):
        
        import numpy as np
        import wave
        ring = getattr(self, "_mic_ring", None)
        if ring is None or len(ring) < int(16000 * 0.3):

            return True

        clip = ring[-int(16000 * 0.7):].copy()
        clip = np.clip(clip, -1.0, 1.0)
        p16 = (clip * 32767.0).astype(np.int16)
        tmp = os.path.join(tempfile.gettempdir(),
                           "barge_spk_%d.wav" % int(time.time() * 1000))
        try:
            with wave.open(tmp, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(p16.tobytes())
            spk = speaker_verdict(tmp)
        except Exception as e:
            print("[插话] 说话人验证异常，放行：", repr(e))
            try:
                os.remove(tmp)
            except Exception:
                pass
            return True
        try:
            os.remove(tmp)
        except Exception:
            pass

        return bool(spk.get("accept", True))

    def _adaptive_barge_skip(self, audio_data):
        
        import numpy as np
        if not audio_data:
            return audio_data
        arr = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
        sr = 16000
        win_ms = 20
        hop_ms = 10
        pre_ms = 20
        win = max(1, int(sr * win_ms / 1000))
        hop = max(1, int(sr * hop_ms / 1000))
        pre = int(sr * pre_ms / 1000)
        echo_floor = getattr(self, "_barge_echo_floor", 0.0)
        voice_floor = max(self.noise_floor * 2.0, echo_floor * 1.3, 250.0)
        voice_floor = min(voice_floor, 600.0)
        for i in range(0, max(1, len(arr) - win + 1), hop):
            rms = float(np.sqrt(np.mean(arr[i:i + win] ** 2))) if len(arr[i:i + win]) else 0.0
            if rms >= voice_floor:
                start = max(0, i - pre)
                skip_ms = int(start / sr * 1000)
                print("[插话] 自适应去尾音：从 %dms 开始保留人声（RMS=%.1f 阈值=%.1f）"
                      % (skip_ms, rms, voice_floor))
                return audio_data[start * 2:]

        skip_bytes = int(sr * 2 * self._barge_skip_ms / 1000)
        if len(audio_data) > skip_bytes:
            print("[插话] 自适应未找到人声，兜底丢弃前 %dms" % self._barge_skip_ms)
            return audio_data[skip_bytes:]
        return audio_data

    def _save_and_transcribe(self, frames, pa):
        import wave
        path = os.path.join(tempfile.gettempdir(),
                            f"voice_{int(time.time()*1000)}.wav")
        try:
            audio_data = self._resample_to_16k_mono(frames)
            if not audio_data:
                print("录音数据为空，跳过转写")
                return


            if self._last_barge_in:
                audio_data = self._adaptive_barge_skip(audio_data)
                self._last_barge_in = False
            with wave.open(path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(pa.get_sample_size(self.format))
                wf.setframerate(16000)
                wf.writeframes(audio_data)
        except Exception as e:
            print(f"保存录音失败: {e}")
            return


        tone_hint = _analyze_voice_tone(path)




        try:
            spk = speaker_verdict(path)
        except Exception as e:
            spk = {"accept": True, "confidence": 0.0,
                   "reason": "说话人识别异常，已放行：%s" % e, "hint": ""}
        if not spk["accept"]:
            print("【说话人识别】已忽略：%s（相似度 %.0f%%）"
                  % (spk["reason"], spk["confidence"] * 100))
            self.voice_ignored.emit(
                "🔇 检测到其他人的声音（相似度 %.0f%%），已忽略——不会把视频/音频里的人当成你在说话"
                % (spk["confidence"] * 100))
            try:
                os.remove(path)
            except Exception:
                pass
            return
        if spk.get("hint"):
            tone_hint = (tone_hint + " " + spk["hint"]).strip()

        if self.model_handles_asr:

            self.state_changed.emit("transcribing")
            print("【AI读取检测】✅ 检测成功：使用模型自带听音，已将录音传给 AI")
            self.audio_ready.emit(path, tone_hint)
            return

        try:
            self.state_changed.emit("transcribing")
            asr_path = _denoise_for_asr(path)
            result = self.whisper_model.transcribe(
                asr_path, language="zh", fp16=False,
                initial_prompt=_WHISPER_INITIAL_PROMPT,
                condition_on_previous_text=False)
            text = result.get("text", "").strip()
            if asr_path != path:
                try:
                    os.remove(asr_path)
                except Exception:
                    pass
            print("whisper 转写结果：", text or "<空>")
            if text:
                print("【AI读取检测】✅ 检测成功：已将你的语音识别为文字 →",
                      (text[:40] + "…") if len(text) > 40 else text)
                self.text_ready.emit(text, tone_hint)
            else:
                print("【AI读取检测】❌ 未检测到：录音已转写但没有识别到文字")
        except Exception as e:
            print(f"语音转文字失败: {e}")
            print("【AI读取检测】❌ 未检测到：语音转写过程出错")
        finally:
            try:
                os.remove(path)
            except Exception:
                pass

    def run(self):
        try:
            import pyaudio
            import wave  # noqa: F401
            import numpy as np
            if not self.model_handles_asr:
                import whisper
        except ImportError as e:
            missing = getattr(e, 'name', str(e))
            self.state_changed.emit(f"missing:{missing}")
            return

        if not self._load_whisper():
            return


        self._load_vad()

        self.format = pyaudio.paInt16
        pa = pyaudio.PyAudio()


        self._probe_default_input_device(pa)
        try:
            stream = pa.open(format=self.format,
                             channels=self.channels,
                             rate=self.sample_rate,
                             input=True,
                             input_device_index=self._input_device_index,
                             frames_per_buffer=self.chunk)
        except Exception as e:
            print("按探测参数打开麦克风失败，回退到 1ch/16kHz：", e)
            self.channels = 1
            self.sample_rate = 16000
            self._input_device_index = None
            try:
                stream = pa.open(format=self.format,
                                 channels=1,
                                 rate=16000,
                                 input=True,
                                 frames_per_buffer=self.chunk)
            except Exception as e2:
                print("【麦克风】回退到 1ch/16kHz 后仍无法打开：", e2)
                self.state_changed.emit(f"mic_error:{e2}")
                return

        self.running = True
        self.state_changed.emit("idle")






        try:

            for _ in range(5):
                stream.read(self.chunk, exception_on_overflow=False)
            calib_n = max(10, int(self.sample_rate / self.chunk * 1.5))
            calib = []
            for _ in range(calib_n):
                d = stream.read(self.chunk, exception_on_overflow=False)
                a = np.frombuffer(d, dtype=np.int16).astype(np.float32)
                if len(a):
                    calib.append(float(np.sqrt(np.mean(a ** 2))))
            if calib:
                calib.sort()
                n = len(calib)

                lo = max(1, n // 10)
                hi = max(1, n * 2 // 10)
                trimmed = calib[lo:n - hi]
                noise_floor = trimmed[len(trimmed) // 2] if trimmed else calib[n // 2]
                self.noise_floor = noise_floor

                self._ambient_history = [noise_floor] * self._ambient_window
                self.silence_threshold = max(400.0, min(700.0, noise_floor * 1.5))
                print("麦克风底噪校准：noise_floor=%.1f，初始触发阈值=%.1f"
                      % (noise_floor, self.silence_threshold))
            self._last_diag = 0.0
        except Exception as e:
            print("底噪校准失败，沿用默认阈值：", e)

        frames = []
        is_recording = False
        speech_frames = 0
        pre_frames = []
        pre_limit = max(1, int(self.sample_rate / self.chunk * 0.5))
        last_speech_time = 0.0
        max_frames = int(self.sample_rate / self.chunk * self.max_record_seconds)
        min_speech_frames = int(self.sample_rate / self.chunk * self.min_speech_seconds)

        while self.running:
            try:
                data = stream.read(self.chunk, exception_on_overflow=False)
            except Exception as e:
                if not getattr(self, '_warned_read', False):
                    self._warned_read = True
                    print("【麦克风】stream.read 失败，将静默重试：", repr(e))
                continue

            if self._check_reset():
                frames = []
                pre_frames = []
                is_recording = False
                speech_frames = 0
                last_speech_time = 0.0
                self._consecutive_over = 0
                self._vad_speaking = False
                self._vad_speech_run = 0
                self._vad_silence_run = 0
                if self._vad_enabled and self._vad_model is not None:
                    try:
                        self._vad_model.reset_states()
                    except Exception as e:
                        print("【VAD】reset_states 失败：", repr(e))
                    self._vad_pcm = np.zeros(0, dtype=np.float32)
                continue

            try:
                import numpy as np
                audio_data = np.frombuffer(data, dtype=np.int16)
                rms = float(np.sqrt(np.mean(audio_data.astype(np.float32) ** 2))) if len(audio_data) else 0.0
            except Exception as e:
                if not getattr(self, '_warned_rms', False):
                    self._warned_rms = True
                    print("【音量】RMS 计算失败，将按 0 处理：", repr(e))
                rms = 0.0
            tnow = time.time()


            if self._vad_enabled:
                try:
                    pcm16k = self._to_16k_mono_float(data)
                    speaking_now = self._feed_vad(pcm16k)
                except Exception as e:


                    print("[VAD] 推理异常，本次帧跳过：", repr(e))
                    speaking_now = is_recording
            else:

                trigger_threshold = max(450.0, min(650.0, self.noise_floor * 1.5))
                sustain_threshold = max(380.0, min(550.0, self.noise_floor * 1.2))
                if is_recording:
                    speaking_now = rms > sustain_threshold
                else:
                    if rms > trigger_threshold:
                        self._consecutive_over += 1
                    else:
                        self._consecutive_over = 0
                    speaking_now = self._consecutive_over >= self._trigger_required


            if self.ai_playing:
                try:
                    pcm = self._to_16k_mono_float(data)
                    if pcm is not None and len(pcm):
                        if self._mic_ring is None:
                            self._mic_ring = pcm
                        else:
                            self._mic_ring = np.concatenate([self._mic_ring, pcm])
                        if len(self._mic_ring) > self._mic_ring_cap:
                            self._mic_ring = self._mic_ring[-self._mic_ring_cap:]
                except Exception:
                    pass



            barged = False
            barge_human = False
            if self.ai_playing and self._barge_mode:
                barged, barge_human = self._barge_in_detect(tnow, rms, speaking_now)


            if tnow - getattr(self, '_last_diag', 0.0) >= 1.0:
                self._last_diag = tnow
                if self._vad_enabled:
                    suffix = "← 检测到人声，正在录音" if is_recording else ""
                    if self.suppress:
                        suffix = "（AI 朗读中：已屏蔽，等待插话）"
                    elif self.ai_playing:
                        suffix = "（AI 朗读中：基线=%.0f 超额=%.0f）" % (
                            self._echo_floor, max(0.0, rms - self._echo_floor))
                    print("[音量诊断] RMS=%.1f  VAD=%s  %s"
                          % (rms, "人声" if self._vad_speaking else "静音", suffix))
                else:
                    active_threshold = (sustain_threshold if is_recording
                                        else trigger_threshold)
                    print("[音量诊断] RMS=%.1f  阈值=%.1f  连续=%d/%d  %s"
                          % (rms, active_threshold, self._consecutive_over,
                             self._trigger_required,
                             "← 超过阈值，正在录音" if rms > active_threshold else ""))


            pre_frames.append(data)
            if len(pre_frames) > pre_limit:
                pre_frames.pop(0)

            if self.suppress:



                if is_recording:
                    is_recording = False
                    frames = []
                    speech_frames = 0
                    pre_frames = []
                    self._vad_speaking = False
                    self._vad_speech_run = 0
                    self._vad_silence_run = 0
                    if self._vad_enabled and self._vad_model is not None:
                        try:
                            self._vad_model.reset_states()
                        except Exception:
                            pass
                        self._vad_pcm = np.zeros(0, dtype=np.float32)
                last_speech_time = tnow
            elif speaking_now or barge_human:
                last_speech_time = tnow
                if not is_recording:
                    is_recording = True
                    if barged:


                        frames = []
                        pre_frames = []
                    else:

                        frames = list(pre_frames)
                    tag = ("插话打断→打断AI" if barged
                           else ("VAD 检测到人声" if self._vad_enabled else "能量超阈值"))
                    print("[录音] 开始录音（%s，RMS=%.1f）" % (tag, rms))
                    self.user_started_speaking.emit()
                    self.state_changed.emit("listening")

                frames.append(data)
                speech_frames += 1
            else:
                if is_recording:
                    frames.append(data)


                    if self._vad_enabled or (tnow - last_speech_time >= self.silence_seconds):
                        dur = speech_frames * self.chunk / float(self.sample_rate)
                        print("[录音] 结束，有效语音约 %.1fs（speech_frames=%d），"
                              "将转写" % (dur, speech_frames))
                        if speech_frames >= min_speech_frames:
                            self._save_and_transcribe(frames, pa)
                        else:
                            print("[录音] 时长不足 %.1fs，丢弃" % self.min_speech_seconds)
                        is_recording = False
                        frames = []
                        speech_frames = 0
                        self.state_changed.emit("idle")

            if is_recording and len(frames) > max_frames:
                self._save_and_transcribe(frames, pa)
                is_recording = False
                frames = []
                speech_frames = 0
                self.state_changed.emit("idle")

        try:
            stream.stop_stream()
            stream.close()
        except Exception:
            pass
        pa.terminate()
class FloatingWindow(QWidget):
    

    BUBBLE_SIZE = 56

    def __init__(self, main_window=None):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.main_window = main_window
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(self.BUBBLE_SIZE, self.BUBBLE_SIZE)
        self._drag_pos = None
        self._drag_start = None
        self._dragging = False
        self._panel = BubblePanel(self)
        self._panel.floating = self
        self._panel.hide()
        self._anim_group = None
        self._main_anim_group = None
        self._panel_hiding = False
        self._hover_timer = QTimer(self)
        self._hover_timer.timeout.connect(self._check_hover)
        self._hover_timer.start(120)
        self._init_bubble()
        self._setup_menu()
        self._place_bottom_right()


        self.mic_indicator = QLabel(self)
        self.mic_indicator.setFixedSize(14, 14)
        self.mic_indicator.setStyleSheet(
            "QLabel { background:#ff3b30; border:2px solid #fff;"
            " border-radius:7px; }")
        self.mic_indicator.move(self.BUBBLE_SIZE - 18, 0)
        self.mic_indicator.hide()
        self._mic_blink_on = False
        self._mic_blink = QTimer(self)
        self._mic_blink.timeout.connect(self._blink_mic)


        self.listener = VoiceListener(self)

        if main_window and getattr(main_window, "model_caps", None):
            self.listener.model_handles_asr = main_window.model_caps.get("asr", False)
        self.listener.text_ready.connect(self._on_voice_text)
        self.listener.audio_ready.connect(self._on_voice_audio)
        self.listener.user_started_speaking.connect(self._interrupt_ai)
        self.listener.voice_ignored.connect(self._on_voice_ignored)
        self.listener.state_changed.connect(self._on_voice_state)


        self._unsuppress_timer = None
        if main_window and getattr(main_window, "speech_engine", None):
            main_window.speech_engine.speaking_started.connect(self._on_ai_speak_start)
            main_window.speech_engine.speaking_finished.connect(self._on_ai_speak_end)

            main_window.speech_engine.segment_playing.connect(self._on_ai_segment)

            main_window.speech_engine.stream_reveal.connect(self._on_stream_reveal)
            main_window.speech_engine.speaking_finished.connect(self._reveal_all_text)


        self._panel_pinned = False
        self._panel_pin_timer = QTimer(self)
        self._panel_pin_timer.setSingleShot(True)
        self._panel_pin_timer.timeout.connect(self._unpin_panel)


        self._streaming = False
        self._partial_text = ""
        self._spoken_len = 0
        self._revealed_len = 0
        self._reveal_active = False



        self._in_float_mode = True

    def showEvent(self, event):
        
        self._in_float_mode = True
        self.setWindowOpacity(1.0)
        self._start_listener()
        super().showEvent(event)

    def hideEvent(self, event):
        
        self._in_float_mode = False
        self._stop_listener()
        super().hideEvent(event)

    def _init_bubble(self):
        self.bubble = QLabel("AI", self)
        self.bubble.setFixedSize(self.BUBBLE_SIZE, self.BUBBLE_SIZE)
        self.bubble.setAlignment(Qt.AlignCenter)
        self.bubble.setStyleSheet(
            "QLabel{background:qradialgradient(cx:0.35,cy:0.35,radius:0.9,"
            "stop:0 #8aa4ff, stop:0.55 #5b7fff, stop:1 #3b62ff);"
            "color:#fff;border:2px solid rgba(255,255,255,0.85);"
            "border-radius:28px;font-size:17px;font-weight:bold;}"
        )
        self.bubble.setAttribute(Qt.WA_TransparentForMouseEvents)

    def _setup_menu(self):
        self._menu = QMenu(self)
        back = QAction("返回主界面", self)
        back.triggered.connect(self._return_to_main)
        self._menu.addAction(back)
        self._menu.addSeparator()
        quit_act = QAction("退出", self)
        quit_act.triggered.connect(lambda: QApplication.instance().quit())
        self._menu.addAction(quit_act)

    def contextMenuEvent(self, event):
        self._menu.exec_(event.globalPos())

    def _place_bottom_right(self):
        
        screen = QApplication.primaryScreen()
        sg = screen.availableGeometry() if screen else QRect(0, 0, 1280, 800)

        self.move(sg.width() - self.BUBBLE_SIZE - 20,
                  sg.top() + 80)

    def _reposition_panel(self):


        bubble_top_left = self.mapToGlobal(QPoint(0, 0))
        bubble = QRect(bubble_top_left, self.size())
        screen = QApplication.screenAt(bubble.center()) or QApplication.primaryScreen()
        sg = screen.availableGeometry() if screen else QRect(0, 0, 1280, 800)
        pw, ph = self._panel.width(), self._panel.height()
        gap = 12


        if bubble.left() - pw - gap >= sg.left() + 6:
            self._panel.tail_dir = "right"
            x = bubble.left() - pw - gap
        else:

            self._panel.tail_dir = "left"
            x = bubble.right() + gap


        self._panel._tail_anchor_y = bubble.center().y()




        if getattr(self, "_panel_hiding", False):
            self._panel.update()
            return



        y = bubble.top()
        if y < sg.top() + 6:
            y = sg.top() + 6
        if y + ph > sg.bottom() - 6:
            y = sg.bottom() - ph - 6


        if x < sg.left() + 6:
            x = sg.left() + 6
        if x + pw > sg.right() - 6:
            x = sg.right() - pw - 6

        self._panel.move(x, y)
        self._panel.update()

    def _toggle_panel(self):
        if self._panel.isVisible():
            self._hide_panel()
        else:
            self._show_panel()

    def _show_panel(self):
        
        self._panel_hiding = False


        if not self._panel.display.text().strip():
            last = getattr(self._panel, "_last_ai_text", "")
            if last:
                self._panel.display.setText(self._panel._clean_text(last))
            else:

                return


        self._panel._fit_size_to_content()




        self._reposition_panel()

        if self._anim_group is not None and self._anim_group.state() == QPropertyAnimation.Running:
            self._anim_group.stop()
        self._panel.setWindowOpacity(0.0)
        self._panel.show()
        self._panel.raise_()

        self._anim_group = QPropertyAnimation(self._panel, b"windowOpacity")
        self._anim_group.setStartValue(0.0)
        self._anim_group.setEndValue(1.0)
        self._anim_group.setDuration(450)
        self._anim_group.setEasingCurve(QEasingCurve.OutQuad)

        def _on_panel_shown():


            self._panel._fit_size_to_content()
            self._reposition_panel()

        self._anim_group.finished.connect(_on_panel_shown)
        self._anim_group.start()

    def _hide_panel(self):
        
        if not self._panel.isVisible() or self._panel_hiding:
            return

        self._panel_pinned = False
        if getattr(self, "_panel_pin_timer", None) is not None:
            self._panel_pin_timer.stop()
        self._panel_hiding = True
        target_geo = QRect(self._panel.x(), self._panel.y(),
                           self._panel.width(), self._panel.height())
        center = target_geo.center()
        end_geo = QRect(center.x(), center.y(), 0, 0)

        geo_anim = QPropertyAnimation(self._panel, b"geometry")
        geo_anim.setStartValue(target_geo)
        geo_anim.setEndValue(end_geo)
        geo_anim.setDuration(700)
        geo_anim.setEasingCurve(QEasingCurve.InQuad)

        op_anim = QPropertyAnimation(self._panel, b"windowOpacity")
        op_anim.setStartValue(1.0)
        op_anim.setEndValue(0.0)
        op_anim.setDuration(600)

        self._anim_group = QParallelAnimationGroup(self)
        self._anim_group.addAnimation(geo_anim)
        self._anim_group.addAnimation(op_anim)

        def _on_finished():
            self._panel.hide()
            self._panel_hiding = False

        self._anim_group.finished.connect(_on_finished)
        self._anim_group.start()

    def _return_to_main(self):
        
        self._in_float_mode = False
        self._hide_panel()
        self._stop_listener()
        bubble_center = self.geometry().center()
        self._burst_bubble()
        self._show_main_with_animation(bubble_center)

    def _burst_bubble(self):
        
        if not self.isVisible():
            return
        center = self.geometry().center()
        start_geo = self.geometry()
        size = max(start_geo.width(), start_geo.height())
        end_geo = QRect(center.x() - size, center.y() - size,
                        size * 2, size * 2)

        geo_anim = QPropertyAnimation(self, b"geometry")
        geo_anim.setStartValue(start_geo)
        geo_anim.setEndValue(end_geo)
        geo_anim.setDuration(600)
        geo_anim.setEasingCurve(QEasingCurve.OutQuad)

        op_anim = QPropertyAnimation(self, b"windowOpacity")
        op_anim.setStartValue(1.0)
        op_anim.setEndValue(0.0)
        op_anim.setDuration(520)

        group = QParallelAnimationGroup(self)
        group.addAnimation(geo_anim)
        group.addAnimation(op_anim)
        group.finished.connect(self.hide)
        group.start()

    def _set_mic_active(self, active):
        
        self.mic_indicator.setVisible(active)
        if active:
            self._mic_blink_on = True
            self.mic_indicator.setStyleSheet(
                "QLabel { background:#ff3b30; border:2px solid #fff;"
                " border-radius:7px; }")
            self._mic_blink.start(600)
        else:
            self._mic_blink.stop()
            self.mic_indicator.setStyleSheet(
                "QLabel { background:#ff3b30; border:2px solid #fff;"
                " border-radius:7px; }")

    def _blink_mic(self):
        
        self._mic_blink_on = not self._mic_blink_on
        color = "#ff3b30" if self._mic_blink_on else "#7a2018"
        self.mic_indicator.setStyleSheet(
            "QLabel { background:%s; border:2px solid #fff; border-radius:7px; }"
            % color)

    def _start_listener(self):
        
        if (getattr(self, 'listener', None) and
                not self.listener.isRunning()):
            self.listener.running = True
            self.listener.start()
            self._set_mic_active(True)

    def _stop_listener(self):
        
        self._set_mic_active(False)
        if (getattr(self, 'listener', None) and
                self.listener.isRunning()):
            self.listener.running = False
            self.listener.wait(1500)
            if self.listener.isRunning():

                try:
                    self.listener.terminate()
                except Exception:
                    pass
                self.listener.wait(2000)

    def _show_main_with_animation(self, origin_center):
        
        mw = self.main_window
        if not mw:
            return
        mw.show()
        mw.raise_()
        mw.activateWindow()
        target_geo = mw.geometry()
        start_geo2 = QRect(origin_center.x() - 25, origin_center.y() - 18, 50, 36)
        mw.setGeometry(start_geo2)
        mw.setWindowOpacity(0.0)

        geo_anim2 = QPropertyAnimation(mw, b"geometry")
        geo_anim2.setStartValue(start_geo2)
        geo_anim2.setEndValue(target_geo)
        geo_anim2.setDuration(1500)
        geo_anim2.setEasingCurve(QEasingCurve.OutBack)

        op_anim2 = QPropertyAnimation(mw, b"windowOpacity")
        op_anim2.setStartValue(0.0)
        op_anim2.setEndValue(1.0)
        op_anim2.setDuration(1000)

        self._main_anim_group = QParallelAnimationGroup(self)
        self._main_anim_group.addAnimation(geo_anim2)
        self._main_anim_group.addAnimation(op_anim2)
        self._main_anim_group.start()

    def _check_hover(self):
        
        if not self._panel.isVisible() or self._panel_hiding:
            return
        if getattr(self, "_panel_pinned", False):
            return

        if getattr(self, "_streaming", False):
            return

        if getattr(self, "_reveal_active", False):
            return

        mw = self.main_window
        if mw and getattr(mw, "speech_engine", None) \
                and getattr(mw.speech_engine, "is_speaking", False):
            return
        pos = QCursor.pos()
        if (not self._panel.geometry().contains(pos) and
                not self.geometry().contains(pos)):
            self._hide_panel()

    def _on_voice_text(self, text, tone_hint=""):
        
        if not text.strip():
            return
        print("语音已转文字，将发送给 AI：", text)
        self._user_voice_text = text
        self._send_ai(text, show_user=False, speak=True, tone_meta=tone_hint)

    def _on_voice_audio(self, path, tone_hint=""):
        
        if not path or not os.path.exists(path):
            return
        print("模型自带听音：直接发送音频附件给 AI")
        self.bubble.setToolTip("已把录音发给模型识别…")
        att = {"path": path, "type": "audio", "name": os.path.basename(path)}
        self._send_ai("", show_user=False, speak=True, attachments=[att],
                     cleanup_paths=[path], tone_meta=tone_hint)

    def _send_ai(self, message, show_user=False, speak=False, attachments=None,
                 cleanup_paths=None, tone_meta=""):
        

        emotion = None
        mw = self.main_window
        if mw and getattr(mw, "emotion_analyzer", None) is not None:
            emotion = mw._detect_emotion(message)
            if emotion and emotion[0] not in ("中性", None, ""):
                self.bubble.setToolTip("识别到情绪：%s（约 %.0f%%）" %
                                       (emotion[0], emotion[1] * 100))

        model_message = message
        if mw and getattr(mw, "_screen_context", ""):
            model_message = (
                message + "\n\n[屏幕背景（这是你已经掌握的内部信息，只在相关时自然用上，"
                "不要在回复里复述或朗读屏幕内容）]\n" + mw._screen_context)
        self.worker = ChatWorker(model_message, attachments or [], emotion=emotion,
                                  speak=speak, cleanup_paths=cleanup_paths,
                                  tone_meta=tone_meta)
        self.worker.response_ready.connect(self._on_response)
        self.worker.partial_ready.connect(self._on_partial)
        self.worker.gen_started.connect(self._on_gen_started)
        self.worker.start()

    def _on_gen_started(self):
        
        if not self._in_float_mode:

            if self.main_window:
                self.main_window.on_gen_started()
            return
        self._streaming = True
        self._partial_text = ""
        self._spoken_len = 0
        self._revealed_len = 0
        self._reveal_active = True

    def _on_partial(self, delta):
        
        if not self._in_float_mode:

            if self.main_window:
                self.main_window.on_partial(delta)
            return
        if not getattr(self, "_streaming", False):
            self._on_gen_started()
        self._partial_text += delta

        self._update_streaming_panel()

        revealed = self._partial_text[:max(0, self._revealed_len)]
        if revealed.strip() and not self._panel.isVisible():
            self._ensure_panel_visible()
        self._flush_speak()

    def _smart_cut(self, text, max_len):
        
        if not text or max_len <= 0:
            return 1
        if len(text) <= max_len:
            return len(text)

        m = re.search(r".*[。！？!?；;]", text[:max_len])
        if m:
            return m.end()

        try:
            import jieba
            pos = 0
            for w in jieba.cut(text, cut_all=False):
                if pos + len(w) > max_len:

                    return max(pos, 1)
                pos += len(w)
            return len(text)
        except Exception:
            pass

        sp = text.rfind(" ", 0, max_len + 1)
        if sp > 0:
            return sp + 1

        return max_len

    def _flush_speak(self, force=False):
        
        mw = self.main_window
        if mw and getattr(mw, "model_caps", None) and mw.model_caps.get("tts"):
            return
        se = getattr(mw, "speech_engine", None)
        if se is None:
            return
        rest = self._partial_text[self._spoken_len:]
        if not rest:
            return
        _STREAM_CHUNK = 40
        SENT_PUNCT = r"[。！？!?；;]"
        if not force:
            m = re.search(r".*" + SENT_PUNCT, rest)
            if m is not None:
                cut = m.end()
            elif len(rest) >= _STREAM_CHUNK:
                cut = self._smart_cut(rest, _STREAM_CHUNK)
            else:
                return
        else:
            cut = len(rest)
        sentence = rest[:cut]
        self._spoken_len += cut
        try:
            se.append_speak(sentence)
        except Exception as e:
            print("追加朗读失败:", e)

    def _speech_will_play(self):
        
        mw = self.main_window
        return bool(mw and getattr(mw, "voice_enabled", False)
                    and getattr(mw, "speech_engine", None)
                    and mw.speech_engine.engine
                    and not (getattr(mw, "model_caps", None) and mw.model_caps.get("tts")))

    def _update_streaming_panel(self):
        
        if not getattr(self, "_panel", None):
            return
        if self._speech_will_play():
            shown = self._partial_text[:max(0, self._revealed_len)]
        else:
            shown = self._partial_text
        self._panel.show_streaming_text(shown)

    def _on_stream_reveal(self, n):
        
        if not self._in_float_mode or not getattr(self, "_reveal_active", False):
            return
        self._revealed_len = min(len(self._partial_text),
                                 self._revealed_len + max(0, int(n)))
        self._update_streaming_panel()

        revealed = self._partial_text[:self._revealed_len]
        if revealed.strip() and not self._panel.isVisible():
            self._ensure_panel_visible()

    def _reveal_all_text(self):
        
        if not self._in_float_mode or not getattr(self, "_reveal_active", False):
            return
        self._revealed_len = len(self._partial_text)
        self._update_streaming_panel()
        self._reveal_active = False

    def _on_response(self, response, source_tag, speak=False):
        
        if not self._in_float_mode:

            if self.main_window:
                self.main_window.on_response_ready(response, source_tag)
            return
        if getattr(self, "_streaming", False):

            self._flush_speak(force=True)
            mw = self.main_window
            if mw and getattr(mw, "speech_engine", None) \
                    and not (getattr(mw, "model_caps", None) and mw.model_caps.get("tts")):
                try:
                    mw.speech_engine.finish_stream_session()
                except Exception:
                    pass
            self._streaming = False


            self._update_streaming_panel()
            self._panel._last_ai_text = self._panel._clean_text(response)



            if not self._speech_will_play():
                self._reveal_all_text()
            return
        if not response or not response.strip():
            print("【AI回复检测】❌ 未检测到：AI 返回内容为空（不弹气泡）")
            return
        print("【AI回复检测】✅ 检测成功：AI 已返回回复（来源：%s）" % source_tag)
        if getattr(self, "_panel", None) is None:
            print("悬浮窗回复回调：面板不存在，丢弃回复")
            return


        self._ensure_panel_visible()
        self._panel._on_response(response, source_tag, speak)

    def _ensure_panel_visible(self):
        
        if not self._in_float_mode:
            return
        if not self._panel.isVisible():
            self._show_panel()
        self._panel_pinned = True
        self._panel_pin_timer.start(6000)

    def _unpin_panel(self):
        
        self._panel_pinned = False

    def _on_ai_speak_start(self):
        
        if getattr(self, "listener", None) is not None:
            self.listener.set_ai_playing(True)

        if getattr(self, "_unsuppress_timer", None) is not None:
            self._unsuppress_timer.stop()

    def _on_ai_segment(self, wav_path):
        
        if getattr(self, "listener", None) is None:
            return
        self.listener.feed_ai_audio(wav_path)

    def _on_ai_speak_end(self):
        
        if getattr(self, "listener", None) is None:
            return
        if getattr(self, "_unsuppress_timer", None) is None:
            self._unsuppress_timer = QTimer(self)
            self._unsuppress_timer.setSingleShot(True)
            self._unsuppress_timer.timeout.connect(self._do_unsuppress)
        self._unsuppress_timer.start(600)

    def _do_unsuppress(self):
        if getattr(self, "listener", None) is not None:
            self.listener.set_suppress(False)
            self.listener.set_ai_playing(False)

    def _on_voice_ignored(self, msg):
        
        print("【说话人识别】", msg)
        self.bubble.setToolTip(msg)

        timer = getattr(self, "_voice_ignored_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            self._voice_ignored_timer = timer

        try:
            timer.timeout.disconnect()
        except Exception:
            pass
        timer.timeout.connect(
            lambda: self.bubble.setToolTip("点击说话 / 右键返回主界面"))
        timer.start(4000)

    def _on_voice_state(self, state):
        
        if state in ("idle", "listening", "transcribing", "loading_model",
                     "model_ready"):
            self._set_mic_active(True)
        elif state.startswith(("missing", "mic_error", "model_error")):
            self._set_mic_active(False)
        if state == "listening":
            self.bubble.setToolTip("正在听你说…")
        elif state == "transcribing":
            self.bubble.setToolTip("识别中…")
        elif state == "idle":
            self.bubble.setToolTip("点击说话 / 右键返回主界面")
        elif state.startswith("missing"):
            self.bubble.setToolTip("缺少语音依赖，请装 pyaudio/openai-whisper")
        elif state.startswith("mic_error"):
            self.bubble.setToolTip("麦克风不可用")
        elif state.startswith("model_error"):
            self.bubble.setToolTip("whisper 加载失败")

    def _interrupt_ai(self):
        
        mw = self.main_window
        if mw and getattr(mw, 'speech_engine', None):
            try:
                mw.speech_engine.stop()
            except Exception:
                pass
        if getattr(self, "listener", None) is not None:
            try:
                self.listener.set_ai_playing(False)
            except Exception:
                pass

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:

            self._drag_start = event.globalPos()
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, _event):


        self._cancel_single_click()
        self._return_to_main()

    def _schedule_single_click(self):
        
        self._cancel_single_click()
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(self._on_single_click_fired)
        timer.start(QApplication.instance().doubleClickInterval())
        self._single_click_timer = timer

    def _cancel_single_click(self):
        timer = getattr(self, "_single_click_timer", None)
        if timer is not None:
            try:
                timer.stop()
            except Exception:
                pass
        self._single_click_timer = None

    def _on_single_click_fired(self):
        self._single_click_timer = None
        self._toggle_panel()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and (event.buttons() & Qt.LeftButton):
            if (event.globalPos() - self._drag_start).manhattanLength() > 5:
                self._dragging = True
            if self._dragging:
                self.move(event.globalPos() - self._drag_pos)

                if self._panel.isVisible():
                    self._reposition_panel()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and not self._dragging:




            self._schedule_single_click()
        elif self._dragging:

            if self._panel.isVisible():
                self._reposition_panel()
        self._drag_pos = None
        self._dragging = False
        super().mouseReleaseEvent(event)

    def moveEvent(self, event):
        
        super().moveEvent(event)
        panel = getattr(self, "_panel", None)
        if panel is not None and panel.isVisible():
            try:
                self._reposition_panel()
            except Exception:
                pass

    def closeEvent(self, event):
        
        if (getattr(self, 'tray_icon', None) is not None and
                self.tray_icon.isVisible()):
            event.ignore()
            self.hide()


def _create_tray_icon(parent, window, floating):
    
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    gradient = QRadialGradient(size / 2, size / 2, size / 2 - 2)
    gradient.setColorAt(0, QColor("#8aa4ff"))
    gradient.setColorAt(0.6, QColor("#5b7fff"))
    gradient.setColorAt(1, QColor("#3b62ff"))
    painter.setBrush(QBrush(gradient))
    painter.setPen(QPen(QColor("#ffffff"), 2))
    painter.drawEllipse(2, 2, size - 4, size - 4)
    painter.setPen(QColor("#ffffff"))
    font = QFont("Microsoft YaHei", 20, QFont.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "AI")
    painter.end()

    icon = QIcon(pixmap)
    tray = QSystemTrayIcon(icon, parent)
    tray.setToolTip("AI聊天智能体")

    menu = QMenu()
    show_main = QAction("显示主界面", parent)
    show_main.triggered.connect(lambda: (window.show(), window.raise_(),
                                         window.activateWindow()))
    show_float = QAction("显示悬浮窗", parent)
    show_float.triggered.connect(lambda: (floating.show(),
                                          floating.raise_(),
                                          floating.activateWindow()))
    quit_action = QAction("退出", parent)
    quit_action.triggered.connect(lambda: (_stop_speech_and_quit(window),
                                           QApplication.instance().quit()))
    menu.addAction(show_main)
    menu.addAction(show_float)
    menu.addSeparator()

    tts_menu = QMenu("TTS 后端", parent)
    act_ov = QAction("OpenVoice (克隆音色)", parent)
    act_ov.setCheckable(True)
    act_cv = QAction("CosyVoice (流式克隆)", parent)
    act_cv.setCheckable(True)

    window._tray_act_ov = act_ov
    window._tray_act_cv = act_cv
    _sync_tts_backend_ui(window, get_tts_backend())
    act_ov.triggered.connect(lambda: _set_tts_backend(window, "openvoice"))
    act_cv.triggered.connect(lambda: _set_tts_backend(window, "cosyvoice"))
    tts_menu.addAction(act_ov)
    tts_menu.addAction(act_cv)
    menu.addMenu(tts_menu)
    menu.addSeparator()
    menu.addAction(quit_action)
    tray.setContextMenu(menu)


    tray.activated.connect(
        lambda reason: (window.show(), window.raise_(),
                        window.activateWindow())
        if reason == QSystemTrayIcon.Trigger else None)
    tray.show()
    return tray


def _stop_speech_and_quit(window):
    
    try:
        if window.speech_engine:
            window.speech_engine.stop()
    except Exception as e:
        print("退出前停止语音引擎失败:", e)


def _sync_tts_backend_ui(window, backend):
    
    ov = backend == "openvoice"
    cv = backend == "cosyvoice"

    act_ov = getattr(window, "_tray_act_ov", None)
    act_cv = getattr(window, "_tray_act_cv", None)
    if act_ov is not None:
        act_ov.setChecked(ov)
    if act_cv is not None:
        act_cv.setChecked(cv)

    dlg = getattr(window, "settings_dialog", None)
    if dlg is not None and dlg.isVisible():
        rb_ov = getattr(dlg, "_rb_tts_ov", None)
        rb_cv = getattr(dlg, "_rb_tts_cv", None)
        if rb_ov is not None and rb_cv is not None:
            rb_ov.blockSignals(True)
            rb_cv.blockSignals(True)
            rb_ov.setChecked(ov)
            rb_cv.setChecked(cv)
            rb_ov.blockSignals(False)
            rb_cv.blockSignals(False)

        try:
            if hasattr(dlg, "_restore_voice_for_backend"):
                dlg._restore_voice_for_backend(backend)
            else:
                if hasattr(dlg, "refresh_voice_list"):
                    dlg.refresh_voice_list()
                if hasattr(dlg, "_refresh_clone_manage_ui"):
                    dlg._refresh_clone_manage_ui()
        except Exception as e:
            print("TTS 后端同步刷新设置页失败:", e)


def _set_tts_backend(window, backend):
    
    name = "OpenVoice" if backend == "openvoice" else "CosyVoice"
    try:
        if getattr(window, "speech_engine", None):
            window.speech_engine.set_tts_backend(backend)
        else:
            set_tts_backend(backend)
        _sync_tts_backend_ui(window, backend)
        tray = getattr(window, "tray_icon", None)
        if tray:
            tray.showMessage("TTS 后端", "已切换为 %s" % name)
        print("TTS 后端已切换为:", name)
    except Exception as e:
        print("切换 TTS 后端失败:", e)
        tray = getattr(window, "tray_icon", None)
        if tray:
            tray.showMessage("TTS 后端", "切换失败: %s" % e)


def main():
    
    app = QApplication(sys.argv)


    app.setQuitOnLastWindowClosed(False)


    app.setStyle('Fusion')


    window = AIChatWindow()
    window.hide()


    floating = FloatingWindow(window)
    floating.show()
    window.floating = floating


    tray_icon = _create_tray_icon(window, window, floating)
    window.tray_icon = tray_icon
    floating.tray_icon = tray_icon


    def _shutdown_tts():
        se = getattr(window, 'speech_engine', None)
        if se is not None:
            try:
                se._tts_thread.shutdown()
            except Exception:
                pass
    app.aboutToQuit.connect(_shutdown_tts)


    app.aboutToQuit.connect(stop_launched_ollama_instances)


    sys.exit(app.exec_())


class CosyVoicePromptWorker(QThread):
    
    status_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(str, str, str, str, bool, object)
    error_signal = pyqtSignal(str)
    TEST_TEXT = "你好，这是你的专属音色试听。"

    def __init__(self, src, parent=None):
        super().__init__(parent)
        self.src = src

    def run(self):
        try:
            from cosyvoice_tts import get_tts_backend
            if get_tts_backend() == "openvoice":
                self._run_openvoice(self.src)
            else:
                self._run_cosyvoice(self.src)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error_signal.emit("音色生成失败：%s" % str(e))

    @staticmethod
    def _speed_for(parent):
        
        _rate = 150.0
        if parent is not None:
            try:
                _rate = float(getattr(parent, "voice_speed", 150) or 150)
            except Exception:
                _rate = 150.0
        return max(1.0, min(2.8, _rate / 150.0))

    def _run_openvoice(self, src):
        
        from voice_clone import (VoiceCloner, load_cloned_voices,
                                 save_cloned_voices)
        import os
        self.status_signal.emit("① 提取 OpenVoice 声纹…")
        try:
            vc = VoiceCloner.get_instance(device="cpu")
        except Exception as e:
            self.error_signal.emit("OpenVoice 模型加载失败：%s" % str(e))
            return
        pt, err = vc.extract_voice_pack(src)
        if not pt:
            self.error_signal.emit("未能从音频中提取人声：%s" % (err or "未知错误"))
            return
        self.status_signal.emit("② 已生成 OpenVoice 声纹，合成试听…")

        base = os.path.splitext(os.path.basename(src))[0]
        name = base
        voices = load_cloned_voices()
        existing = [v.get("name") for v in voices]
        if name in existing:
            i = 2
            while ("%s_%d" % (name, i)) in existing:
                i += 1
            name = "%s_%d" % (name, i)
        voices.append({"name": name,
                       "se_path": os.path.join("voices_cloned", os.path.basename(pt)),
                       "lang": "zh"})
        save_cloned_voices(voices)

        try:
            synth_wav = vc.synthesize(self.TEST_TEXT, pt, "zh")
        except Exception as e:
            self.error_signal.emit("OpenVoice 合成失败：%s" % str(e))
            return
        self.status_signal.emit("③ 语音转文字验证清晰度…")
        transcribe = _transcribe_audio_file(synth_wav, language="zh") if synth_wav else ""
        clear = bool(transcribe) and len(transcribe.strip()) >= 4
        self.finished_signal.emit(src, synth_wav, name, transcribe, clear,
                                  {"backend": "openvoice", "name": name, "se_path": pt})

    def _run_cosyvoice(self, src):
        
        from cosyvoice_tts import (prepare_cosyvoice_prompt,
                                   set_tts_backend, CosyVoiceCloner)
        self.status_signal.emit("① 提取音频并自动降噪…（想要长文本朗读更清晰，"
                                 "可用「推荐录制文本」录清晰人声再拖入）")
        ref, prompt_text, warn = prepare_cosyvoice_prompt(src)
        if not ref:
            self.error_signal.emit("未能从音频中提取到人声，请换带人声的音频。")
            return


        if get_tts_backend() != "cosyvoice":
            set_tts_backend("cosyvoice")
        self.status_signal.emit("② 用 CosyVoice 合成试听（较慢，请耐心等待）…")
        try:
            synth_wav = CosyVoiceCloner.get_instance().synthesize(
                self.TEST_TEXT, None, "zh", speed=self._speed_for(self.parent()))
        except Exception as e:
            msg = str(e)
            if "1455" in msg or "页面文件" in msg:
                self.error_signal.emit(
                    "内存不足：CosyVoice 加载失败（%s）。请关闭其他程序释放内存，"
                    "或在 Windows 虚拟内存中调大页面文件；或改用 OpenVoice 后端。" % msg)
            else:
                self.error_signal.emit("CosyVoice 合成失败：%s" % msg)
            return
        self.status_signal.emit("③ 语音转文字验证清晰度…")
        transcribe = _transcribe_audio_file(synth_wav, language="zh")
        clear = bool(transcribe) and len(transcribe.strip()) >= 4


        if warn:
            self.status_signal.emit("⚠️ " + warn)
        name = os.path.splitext(os.path.basename(ref))[0] if ref else "专属音色"
        self.finished_signal.emit(
            src, synth_wav, prompt_text, transcribe, clear,
            {"backend": "cosyvoice", "name": name,
             "prompt_wav": ref, "prompt_text": prompt_text})


if __name__ == '__main__':
    main()