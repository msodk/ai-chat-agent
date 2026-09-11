# -*- coding: utf-8 -*-

import os
import sys
import re
import json
import hashlib
import shutil
import subprocess
import tempfile
import threading
import types
from collections import OrderedDict





# ----------------------------------------------------------------------------




# ----------------------------------------------------------------------------
def _ensure_sklearn_stub():



    try:
        import sklearn  # noqa: F401
        return
    except Exception:
        pass

    if "sklearn" in sys.modules:
        return
    sklearn = types.ModuleType("sklearn")
    sklearn.__path__ = []

    def _sub(name, **attrs):
        m = types.ModuleType("sklearn." + name)
        for k, v in attrs.items():
            setattr(m, k, v)
        return m



    class _Unavailable:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("sklearn stub: %s not available in frozen build" % self.__class__.__name__)

    sklearn.decomposition = _sub("decomposition", NMF=_Unavailable)
    sklearn.cluster = _sub("cluster", KMeans=_Unavailable, AffinityPropagation=_Unavailable, AgglomerativeClustering=_Unavailable)
    sklearn.feature_extraction = _sub("feature_extraction")
    sklearn.neighbors = _sub("neighbors", NearestNeighbors=_Unavailable)

    for name in ("decomposition", "cluster", "feature_extraction", "neighbors"):
        sys.modules["sklearn." + name] = getattr(sklearn, name)
    sys.modules["sklearn"] = sklearn


_ensure_sklearn_stub()



from tts_audio_utils import (
    get_ffmpeg_exe as _get_ffmpeg_exe,
    run_ffmpeg as _run_ffmpeg,
    resample_to_playback_rate as _resample_to_playback_rate,
    normalize_loudness as _normalize_loudness,
    trim_trailing_silence as _trim_trailing_silence,
    denoise_output as _denoise_output,
)


# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
def _app_base():
    
    if getattr(sys, "_MEIPASS", None):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_model_dir():
    
    base = _app_base()
    meipass = getattr(sys, "_MEIPASS", None)
    candidates = [os.path.join(base, "checkpoints_v2")]
    if meipass and meipass != base:
        candidates.append(os.path.join(meipass, "checkpoints_v2"))
    for c in candidates:
        if os.path.isdir(c):
            return c

    return candidates[0]


def get_cloned_dir():
    
    d = os.path.join(_app_base(), "voices_cloned")
    os.makedirs(d, exist_ok=True)
    return d


# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
def get_cloned_voices_path():
    return os.path.join(_app_base(), "cloned_voices.json")


def _looks_like_garbage(stem):
    
    if not stem:
        return True

    if re.fullmatch(r"[0-9a-fA-F]{32}", stem):
        return True
    return False


def load_cloned_voices():
    
    p = get_cloned_voices_path()
    if not os.path.exists(p):
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        base = _app_base()
        out = []
        for v in data.get("voices", []):
            se = v.get("se_path", "")
            if not se or not se.endswith(".pt"):
                continue
            if not os.path.isabs(se):
                se = os.path.join(base, se)
            if not (os.path.isfile(se) and os.path.getsize(se) > 0):
                continue
            name = v.get("name") or os.path.splitext(os.path.basename(se))[0]
            if _looks_like_garbage(name):
                continue
            out.append({
                "name": name,
                "se_path": se,
                "lang": v.get("lang", "zh"),
            })
        return out
    except Exception:
        return []


def save_cloned_voices(entries):
    
    p = get_cloned_voices_path()
    base = _app_base()
    data = {"voices": []}
    for e in entries:
        se = e["se_path"]
        if os.path.isabs(se) and se.startswith(base + os.sep):
            rel = os.path.relpath(se, base)
        else:
            rel = se
        data["voices"].append({
            "name": e["name"], "se_path": rel, "lang": e.get("lang", "zh"),
        })
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def rebuild_cloned_voices():
    
    d = get_cloned_dir()
    entries = []
    for f in sorted(os.listdir(d)):
        if not f.endswith(".pt"):
            continue
        stem = os.path.splitext(f)[0]
        if _looks_like_garbage(stem):
            continue
        fp = os.path.join(d, f)
        if not (os.path.isfile(fp) and os.path.getsize(fp) > 0):
            continue
        entries.append({
            "name": stem,
            "se_path": fp,
            "lang": "zh",
        })
    save_cloned_voices(entries)
    return entries



VIDEO_EXTS = (".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv", ".m4v", ".webm")
AUDIO_EXTS = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".wma", ".opus")
SUPPORTED_EXTS = VIDEO_EXTS + AUDIO_EXTS


def is_supported(path):
    return os.path.splitext(path)[1].lower() in SUPPORTED_EXTS


# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
def to_wav(src_path, ffmpeg):
    
    ext = os.path.splitext(src_path)[1].lower()
    if ext == ".wav":
        return src_path
    tmp = tempfile.mktemp(suffix=".wav")
    cmd = [
        ffmpeg, "-y", "-i", src_path,
        "-vn", "-ac", "1", "-ar", "16000", "-t", "30",
        tmp,
    ]
    try:
        _run_ffmpeg(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=180,
        )
    except Exception:
        return None
    if os.path.exists(tmp) and os.path.getsize(tmp) > 0:
        return tmp
    return None


def unique_pt_path(out_dir, base):
    
    candidate = os.path.join(out_dir, base + ".pt")
    if not os.path.exists(candidate):
        return candidate
    i = 2
    while True:
        candidate = os.path.join(out_dir, f"{base}_{i}.pt")
        if not os.path.exists(candidate):
            return candidate
        i += 1


# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
class VoiceCloner:
    

    _instance = None
    _lock = threading.Lock()

    def __init__(self, model_dir=None, device="cpu"):
        self.model_dir = model_dir or get_model_dir()
        self.device = device
        self.ffmpeg = _get_ffmpeg_exe()
        self._base_tts_map = {}
        self._load_lock = threading.Lock()



        self._synth_lock = threading.Lock()
        self._se_cache = {}

        self._cache_dir = os.path.join(_app_base(), "openvoice_cache")
        self._cache = OrderedDict()
        self._cache_lock = threading.Lock()

        self._prune_cache_dir()


        conv_cfg = os.path.join(self.model_dir, "converter", "config.json")
        conv_ckpt = os.path.join(self.model_dir, "converter", "checkpoint.pth")
        if not os.path.isfile(conv_ckpt):
            raise FileNotFoundError(
                "未找到转换器模型: %s\n请先运行下载脚本获取 OpenVoice V2 checkpoints_v2。" % conv_ckpt
            )



        self._ensure_torch_env()
        from openvoice import api


        self.converter = api.ToneColorConverter(
            conv_cfg, device=device, enable_watermark=False
        )
        self.converter.load_ckpt(conv_ckpt)
        print("VoiceCloner 转换器加载完成")

    def _ensure_base_tts(self, lang="zh"):
        
        key = "zh" if str(lang).lower().startswith("zh") else "en"
        if self._base_tts_map.get(key) is not None:
            return
        with self._load_lock:
            if self._base_tts_map.get(key) is not None:
                return
            from openvoice import api

            base_dir = os.path.join(self.model_dir, "base_speakers", key.upper())
            base_cfg = os.path.join(base_dir, "config.json")
            base_ckpt = os.path.join(base_dir, "checkpoint.pth")

            if not os.path.isfile(base_ckpt):
                raise FileNotFoundError(
                    "未找到基础说话人模型: %s\n"
                    "提取音色包不需要此模型，但「合成克隆语音」需要。\n"
                    "如需合成中文，请把 OpenVoice V2 的 base_speakers/ZH 放到该目录；\n"
                    "如需合成英文，请放置 base_speakers/EN/checkpoint.pth。" % base_ckpt
                )

            tts = api.BaseSpeakerTTS(base_cfg, device=self.device)
            tts.load_ckpt(base_ckpt)
            self._base_tts_map[key] = tts
            print("VoiceCloner 基础说话人模型加载完成(%s)" % key.upper())

    @classmethod
    def get_instance(cls, model_dir=None, device="cpu"):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(model_dir, device)
        return cls._instance


    def extract_voice_pack(self, src_path, out_dir=None, step_cb=None):
        

        self._ensure_torch_env()
        import torch
        if out_dir is None:
            out_dir = get_cloned_dir()
        os.makedirs(out_dir, exist_ok=True)

        wav = to_wav(src_path, self.ffmpeg)
        if not wav:
            return None, "无法提取音频（文件损坏或不支持的编码）"


        cleaned = self._clean_ref_audio(wav)
        if step_cb:
            step_cb("audio")

        from openvoice.se_extractor import get_se

        try:


            with self._synth_lock:
                se, _ = get_se(cleaned, self.converter)
        except Exception as e:
            return None, "声纹提取失败: %s" % str(e)
        finally:


            if cleaned not in (src_path, wav) and os.path.exists(cleaned):
                try:
                    os.remove(cleaned)
                except Exception:
                    pass

            if wav != src_path and os.path.exists(wav):
                try:
                    os.remove(wav)
                except Exception:
                    pass
        if step_cb:
            step_cb("se")

        base = os.path.splitext(os.path.basename(src_path))[0]
        pt_path = unique_pt_path(out_dir, base)
        torch.save(se.cpu(), pt_path)
        if step_cb:
            step_cb("save")
        return pt_path, None

    def _ensure_torch_env(self):
        
        if getattr(self, "_torch_env_ready", False):
            return
        _exe_dir = os.path.dirname(sys.executable)
        if _exe_dir not in sys.path:
            sys.path.insert(0, _exe_dir)
        _torch_lib = os.path.join(_exe_dir, "torch", "lib")
        if os.path.isdir(_torch_lib) and hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(_torch_lib)
            except (ValueError, OSError):
                pass
        self._torch_env_ready = True




    OPENVOICE_BASE_SPEED = 0.9

    def synthesize(self, text, se_path, lang="zh", emotion_label=None,
                   enable_emotion=True, speed=None):
        

        self._ensure_torch_env()
        import torch
        if not os.path.exists(se_path):
            raise FileNotFoundError("音色包不存在: %s" % se_path)
        if se_path not in self._se_cache:
            self._se_cache[se_path] = torch.load(se_path, map_location=self.device, weights_only=False)
        se = self._se_cache[se_path]


        emotion = emotion_label
        if emotion is None and enable_emotion:
            emotion = self._detect_emotion(text)

        user_speed = speed if (speed and speed > 0) else 1.0

        if enable_emotion and emotion and emotion != "中性":
            tempo = self.EMOTION_SPEED.get(emotion, 1.0)
        else:
            tempo = 1.0
        speed = max(0.5, min(2.5, user_speed * self.OPENVOICE_BASE_SPEED * tempo))

        base_wav = tempfile.mktemp(suffix=".wav")
        out_wav = tempfile.mktemp(suffix=".wav")

        lang_map = {
            "zh": "Chinese", "zh-cn": "Chinese", "chinese": "Chinese",
            "cn": "Chinese", "中文": "Chinese",
            "en": "English", "english": "English", "英文": "English",
        }
        language = lang_map.get(str(lang).strip().lower(), "Chinese")




        with self._synth_lock:
            try:

                self._ensure_base_tts(lang)
                base_key = "zh" if str(lang).lower().startswith("zh") else "en"
                self._base_tts_map[base_key].tts(
                    text=text, output_path=base_wav,
                    speaker="default", language=language, speed=speed,
                )

                src_se = self.converter.extract_se([base_wav], se_save_path=None)

                self.converter.convert(
                    audio_src_path=base_wav, src_se=src_se, tgt_se=se,
                    output_path=out_wav,
                )
            finally:

                if os.path.exists(base_wav):
                    try:
                        os.remove(base_wav)
                    except Exception:
                        pass



        out_wav = _resample_to_playback_rate(out_wav, target_sr=44100)


        out_wav = _normalize_loudness(out_wav)



        try:
            out_wav = _trim_trailing_silence(out_wav, max_silence=0.2)
        except Exception as e:
            print("尾部静音裁剪失败，忽略:", e)


        try:
            out_wav = _denoise_output(out_wav)
        except Exception as e:
            print("输出降噪失败，忽略:", e)



        if enable_emotion:
            try:
                out_wav = self._apply_prosody(out_wav, emotion, sr=44100)
            except Exception as e:
                print("情绪语调处理失败，回退原声:", e)


        return self._return_with_cache(out_wav, text, se_path, lang,
                                       emotion_label, enable_emotion, speed)







    _CACHE_MAX = 50


    _CACHE_HARD_CAP = 60

    def _cache_key(self, text, se_path, lang, emotion_label, enable_emotion, speed):



        try:
            mtime = int(os.path.getmtime(se_path))
        except Exception:
            mtime = 0
        raw = "%s|%s|%s|%s|%r|%s|%d" % (
            text, os.path.basename(se_path), lang, emotion_label,
            enable_emotion, "%.3f" % (speed or 0), mtime)
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def _cache_get(self, key):
        with self._cache_lock:
            if key not in self._cache:
                return None
            path = self._cache[key]
            self._cache.move_to_end(key)
            if not os.path.exists(path):
                self._cache.pop(key, None)
                return None
            return path

    def _cache_put(self, key, master_path):
        with self._cache_lock:
            self._cache[key] = master_path
            self._cache.move_to_end(key)
            while len(self._cache) > self._CACHE_MAX:
                _, old = self._cache.popitem(last=False)
                try:
                    if old and os.path.exists(old):
                        os.remove(old)
                except Exception:
                    pass

            self._prune_cache_dir()

    def _prune_cache_dir(self, cap=_CACHE_HARD_CAP):
        
        try:
            d = self._cache_dir
            if not os.path.isdir(d):
                return
            files = [os.path.join(d, f) for f in os.listdir(d)
                     if f.endswith(".wav")]
            if len(files) <= cap:
                return
            files.sort(key=lambda p: os.path.getmtime(p))
            for p in files[:len(files) - cap]:
                try:
                    os.remove(p)
                except Exception:
                    pass
        except Exception:
            pass

    def _return_with_cache(self, out, text, se_path, lang, emotion_label, enable_emotion, speed):
        
        key = self._cache_key(text, se_path, lang, emotion_label, enable_emotion, speed)
        hit = self._cache_get(key)
        if hit:
            tmp = tempfile.mktemp(suffix=".wav")
            shutil.copyfile(hit, tmp)
            try:
                os.remove(out)
            except Exception:
                pass
            return tmp
        try:
            os.makedirs(self._cache_dir, exist_ok=True)
            master = os.path.join(self._cache_dir, key + ".wav")


            shutil.move(out, master)
            self._cache_put(key, master)
            out_consumed = True
        except Exception:
            master = None
            out_consumed = False
        tmp = tempfile.mktemp(suffix=".wav")
        src = master if master else out
        shutil.copyfile(src, tmp)
        if not out_consumed:
            try:
                os.remove(out)
            except Exception:
                pass
        return tmp









    EMOTION_SPEED = {
        "疑问": 1.05,
        "伤心": 0.90,
        "开心": 1.08,
        "愤怒": 1.12,
        "惊讶": 1.06,
        "中性": 1.05,
    }

    _EMOTION_LEXICON = {
        "伤心": ["难过", "伤心", "哭", "悲伤", "难受", "寂寞", "孤独", "想哭", "沮丧",
                 "失望", "遗憾", "心碎", "舍不得", "悲哀", "心寒", "委屈"],
        "开心": ["开心", "高兴", "快乐", "喜欢", "爱", "哈哈", "嘻嘻", "兴奋", "棒", "赞",
                 "好耶", "满意", "感谢", "谢谢", "漂亮", "可爱", "幸福", "爽", "美滋滋",
                 "好喜欢", "太好了", "真高兴"],
        "愤怒": ["生气", "愤怒", "讨厌", "烦", "气死", "可恶", "混蛋", "滚", "恨", "骂",
                 "怒", "烦人", "受不了", "岂有此理"],
        "惊讶": ["惊讶", "震惊", "不敢相信", "哇", "天哪", "居然", "竟然", "意外", "绝了",
                 "天啊", "我的天", "难以置信"],
    }

    def _detect_emotion(self, text):
        
        if not text or not text.strip():
            return "中性"
        t = text.strip()
        last = t[-1]

        if last in ("?", "？") or t.endswith(("吗", "呢", "啊", "呀")) \
                or any(w in t for w in ("怎么", "为什么", "什么", "哪", "几", "是否",
                                         "能不能", "可以吗", "对不对", "是不是", "干嘛",
                                         "咋", "何时", "为何")):
            return "疑问"

        if last in ("！", "!"):
            return "惊讶" if ("？！" in t or "?!" in t) else "开心"

        if "…" in t or "..." in t:
            return "伤心"

        if "～" in t or "~" in t:
            return "开心"

        best, best_n = "中性", 0
        for cat, words in self._EMOTION_LEXICON.items():
            n = sum(1 for w in words if w in t)
            if n > best_n:
                best, best_n = cat, n
        return best

    def _apply_prosody(self, wav_path, emotion, sr=44100):
        
        import soundfile as sf
        import numpy as np

        data, file_sr = sf.read(wav_path, dtype="float32", always_2d=False)
        if data.ndim > 1:
            data = data.mean(axis=1)
        sr = file_sr or sr
        x = np.asarray(data, dtype=np.float64)
        if len(x) < int(0.2 * sr):
            return wav_path
        N = len(x)


        pos = np.arange(N) / N  # 0..1
        mod = np.ones(N, dtype=np.float64)

        tail_start = 0.90
        tail = pos >= tail_start
        frac = (pos[tail] - tail_start) / (1.0 - tail_start)
        mod[tail] *= (1.0 - 0.04 * frac)

        emo = emotion or "中性"
        if emo == "疑问":
            mod[tail] *= (1.0 + 0.12 * frac)
        elif emo == "伤心":
            mod *= 0.985
            mod[tail] *= (1.0 - 0.05 * frac)
        elif emo == "开心":
            mod *= 1.01
        elif emo == "惊讶":
            mod *= 1.015
        elif emo == "愤怒":
            mod *= 1.005

        win = max(3, int(sr * 0.015))
        if win % 2 == 0:
            win += 1
        mod = np.convolve(mod, np.ones(win) / win, mode="same")



        s_seq = np.cumsum(mod)
        s_seq *= (N - 1) / s_seq[-1]
        y = np.interp(s_seq, np.arange(N), x)


        peak = float(np.max(np.abs(y))) or 1.0
        if peak > 0.92:
            y *= 0.92 / peak

        tmp = tempfile.mktemp(suffix=".wav")
        sf.write(tmp, y.astype(np.float32), sr)
        os.replace(tmp, wav_path)
        return wav_path

    def _clean_ref_audio(self, wav_path):
        
        out = tempfile.mktemp(suffix=".wav")
        cmd = [
            self.ffmpeg, "-y", "-i", wav_path,
            "-af", "afftdn=nr=6:nf=-32,highpass=f=60",
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
            out,
        ]
        try:
            _run_ffmpeg(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        except Exception:
            return wav_path
        if os.path.exists(out) and os.path.getsize(out) > 0:
            return out
        return wav_path
