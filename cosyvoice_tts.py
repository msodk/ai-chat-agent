# -*- coding: utf-8 -*-

import os
import sys
import json
import subprocess
import tempfile
import hashlib
import shutil
import threading
from collections import OrderedDict



from tts_audio_utils import (
    get_ffmpeg_exe as _ffmpeg,
    run_ffmpeg as _run_ffmpeg,
    resample_to_playback_rate as _resample_to_playback_rate,
    normalize_loudness as _normalize_loudness,
    trim_trailing_silence as _trim_trailing_silence,
)


def _app_base():
    if getattr(sys, "_MEIPASS", None):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _config_path():
    return os.path.join(_app_base(), "tts_config.json")







_config_lock = threading.RLock()


def _ensure_real_package(name, submodules=()):
    
    import importlib.util


    mod = sys.modules.get(name)
    if mod is not None and getattr(mod, '__spec__', None) is not None \
       and getattr(mod, '__path__', None):
        ok = True
        for sub in submodules:
            try:
                importlib.import_module(f'{name}.{sub}')
            except Exception:
                ok = False
                break
        if ok:
            return


    prefix = name + '.'
    for key in list(sys.modules.keys()):
        if key == name or key.startswith(prefix):
            del sys.modules[key]


    real_pkg_dir = None
    for p in sys.path:
        if not p:
            p = os.getcwd()
        candidate = os.path.join(p, name)
        init_file = os.path.join(candidate, '__init__.py')
        if os.path.isdir(candidate) and os.path.isfile(init_file):
            real_pkg_dir = candidate
            break

    if not real_pkg_dir:
        spec = importlib.util.find_spec(name)
        if spec and spec.origin:
            real_pkg_dir = os.path.dirname(spec.origin)
        else:
            return


    parent = os.path.dirname(real_pkg_dir)
    inserted = False
    if not sys.path or sys.path[0] != parent:
        sys.path.insert(0, parent)
        inserted = True

    try:
        importlib.import_module(name)
        for sub in submodules:
            importlib.import_module(f'{name}.{sub}')
    finally:
        if inserted:
            try:
                if sys.path and sys.path[0] == parent:
                    sys.path.pop(0)
                else:
                    sys.path.remove(parent)
            except ValueError:
                pass


def _ensure_real_torchaudio():
    _ensure_real_package('torchaudio', ['compliance', 'compliance.kaldi',
                                        'transforms', 'functional'])


def _ensure_real_sklearn():
    _ensure_real_package('sklearn')



_ensure_real_torchaudio()
_ensure_real_sklearn()


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------








#







_COSYVOICE_DISABLED = False
_COSYVOICE_DISABLE_REASON = ""
_PROBE_DONE = False


def _probe_cosyvoice_compat():
    
    global _COSYVOICE_DISABLED, _COSYVOICE_DISABLE_REASON, _PROBE_DONE
    if _PROBE_DONE:
        return
    _PROBE_DONE = True
    try:
        import importlib.util
        import subprocess
        import sys
        if importlib.util.find_spec("onnxruntime") is None:
            _COSYVOICE_DISABLED = True
            _COSYVOICE_DISABLE_REASON = (
                "未安装 onnxruntime，CosyVoice 已禁用并自动回退 OpenVoice")
            return
        if getattr(sys, "frozen", False):


            try:
                import onnxruntime  # noqa: F401
            except Exception as e:
                _COSYVOICE_DISABLED = True
                _COSYVOICE_DISABLE_REASON = (
                    "onnxruntime 与当前 NumPy 不兼容（%s），CosyVoice 已禁用并回退 OpenVoice" % e)
            return


        proc = subprocess.run(
            [sys.executable, "-c", "import onnxruntime"],
            capture_output=True, timeout=30)
        if proc.returncode != 0:
            _COSYVOICE_DISABLED = True
            _COSYVOICE_DISABLE_REASON = (
                "onnxruntime 与当前 NumPy 不兼容（导入失败），CosyVoice 已禁用并自动回退 OpenVoice")
    except Exception as e:

        _COSYVOICE_DISABLED = True
        _COSYVOICE_DISABLE_REASON = (
            "onnxruntime 兼容性探测失败（%s），CosyVoice 已禁用并回退 OpenVoice" % e)





_config_cache = {}
_config_mtime = 0.0



def _read_config_raw(p):
    
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _cached_config():
    global _config_mtime
    p = _config_path()
    try:
        m = os.path.getmtime(p)
    except OSError:
        return _read_config_raw(p)
    if m != _config_mtime or not _config_cache:
        with _config_lock:


            if m != _config_mtime or not _config_cache:
                _config_cache.clear()
                _config_cache.update(_read_config_raw(p))
                _config_mtime = m



    return dict(_config_cache)


def _invalidate_config_cache():
    
    global _config_mtime
    with _config_lock:
        _config_cache.clear()
        _config_mtime = 0.0


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------




def _cosyvoice_weights_dir():
    cfg = _cached_config()
    local = cfg.get("cosyvoice_model_local")
    if local:
        local = local if os.path.isabs(local) else os.path.join(_app_base(), local)
        local = os.path.abspath(local)
        if os.path.isdir(local):
            return local



    if getattr(sys, "frozen", False):
        return os.path.join(_app_base(), "CosyVoice2-0.5B")
    return r"D:\AI\CosyVoice2-0.5B"


def cosyvoice_weights_present():
    
    try:
        return os.path.isdir(_cosyvoice_weights_dir())
    except Exception:
        return False


# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
_PATHS_READY = False


def _cosyvoice_repo():
    cfg = _cached_config()
    repo = cfg.get("cosyvoice_repo")
    if repo:
        repo = repo if os.path.isabs(repo) else os.path.join(_app_base(), repo)
        repo = os.path.abspath(repo)
        if os.path.isdir(repo):
            return repo



    if getattr(sys, "frozen", False):
        return os.path.join(_app_base(), "CosyVoice")
    return r"D:\AI\CosyVoice"


def load_wav(wav, target_sr, min_sr=16000):
    
    import soundfile as sf
    import torch
    import torchaudio
    data, sample_rate = sf.read(wav, dtype="float32", always_2d=True)
    if data.shape[1] > 1:
        data = data.mean(axis=1, keepdims=True)
    speech = torch.from_numpy(data.T).contiguous()  # [1, T]
    if sample_rate != target_sr:
        assert sample_rate >= min_sr, \
            "wav sample rate %d must be >= %d" % (sample_rate, target_sr)
        speech = torchaudio.transforms.Resample(
            orig_freq=sample_rate, new_freq=target_sr)(speech)
    return speech


def _venv_site_packages():
    
    base = _app_base()
    proj = os.path.dirname(os.path.dirname(base))
    cand = os.path.join(proj, ".venv", "Lib", "site-packages")
    if os.path.isdir(cand):
        return cand
    env = os.environ.get("COSYVOICE_VENV_SP")
    if env and os.path.isdir(env):
        return env
    return ""


def ensure_cosyvoice_on_path():
    
    global _PATHS_READY
    if _PATHS_READY:
        return
    repo = _cosyvoice_repo()
    candidates = [
        repo,
        os.path.join(repo, "third_party", "Matcha-TTS"),
    ]
    for p in candidates:
        ap = os.path.abspath(p)
        if os.path.isdir(ap) and ap not in sys.path:
            sys.path.insert(0, ap)
    if getattr(sys, "frozen", False):
        sp = _venv_site_packages()
        if sp and os.path.isdir(sp) and sp not in sys.path:
            sys.path.append(sp)
    _PATHS_READY = True


def load_tts_config():
    with _config_lock:
        p = _config_path()
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}


def save_tts_config(cfg):
    with _config_lock:
        with open(_config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    _invalidate_config_cache()



_backend = None


class CosyVoiceUnavailable(Exception):
    
    pass


def get_tts_backend():
    global _backend
    if _backend is None:
        env = os.environ.get("TTS_BACKEND")
        if env in ("openvoice", "cosyvoice"):
            _backend = env
        else:
            cfg = load_tts_config()
            _backend = cfg.get("backend", "openvoice")
    return _backend


def set_tts_backend(backend):
    global _backend
    if backend not in ("openvoice", "cosyvoice"):
        raise ValueError("backend must be openvoice or cosyvoice")
    _backend = backend
    cfg = load_tts_config()
    cfg["backend"] = backend
    save_tts_config(cfg)


def cosyvoice_is_available():
    
    _probe_cosyvoice_compat()
    if _COSYVOICE_DISABLED or not cosyvoice_weights_present():
        return False
    try:
        inst = CosyVoiceCloner.get_instance()
        if inst._unavailable:
            return False

        return True
    except Exception:
        return False


def _openvoice_fallback_wav(text, lang, enable_emotion):
    
    try:
        from voice_clone import VoiceCloner, load_cloned_voices, get_model_dir
        profs = load_cloned_voices() or []
        if not profs:
            return None
        se_path = profs[0]["se_path"]
        if not se_path or not os.path.exists(se_path):
            return None
        if str(lang).lower().startswith("zh"):
            zh_ckpt = os.path.join(get_model_dir(), "base_speakers", "ZH", "checkpoint.pth")
            if not os.path.isfile(zh_ckpt):
                return None
        vc = VoiceCloner.get_instance(device="cpu")
        return vc.synthesize(text, se_path, lang, enable_emotion=enable_emotion)
    except Exception as e:
        print("OpenVoice 回退合成失败:", e)
        return None


def synthesize_cloned(text, profile, lang="zh", enable_emotion=True, speed=1.0):
    
    backend = get_tts_backend()
    if backend == "cosyvoice":
        inst = CosyVoiceCloner.get_instance()
        if inst._unavailable:
            fb = _openvoice_fallback_wav(text, lang, enable_emotion)
            if fb:
                print("CosyVoice 不可用，已回退 OpenVoice 克隆音色：",
                      inst._unavailable_reason)
                return fb
            raise CosyVoiceUnavailable(
                "CosyVoice 当前不可用（%s）。请到设置切回 OpenVoice，或检查 "
                "D:/AI/CosyVoice2-0.5B 权重是否完整、内存是否充足。" % inst._unavailable_reason)
        try:
            return inst.synthesize(text, profile, lang, enable_emotion, speed)
        except Exception as e:
            if inst._unavailable:
                fb = _openvoice_fallback_wav(text, lang, enable_emotion)
                if fb:
                    print("CosyVoice 合成失败，已回退 OpenVoice 克隆音色：", e)
                    return fb
            raise
    from voice_clone import VoiceCloner
    vc = VoiceCloner.get_instance()
    return vc.synthesize(text, profile.get("se_path"), lang,
                         enable_emotion=enable_emotion, speed=speed)


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------










#               speechnorm / agate / anlmdn
# ---------------------------------------------------------------------------
_DENOISE_FILTER = (
    "highpass=f=80,afftdn=nr=8:nf=-24,lowpass=f=11000,"
    "dynaudnorm=f=250:g=8"
)


def _denoise_wav(in_wav, out_wav):
    
    ffmpeg = _ffmpeg()
    cmd = [ffmpeg, "-y", "-i", in_wav, "-af", _DENOISE_FILTER,
           "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", out_wav]
    if _run_ffmpeg(cmd) and os.path.exists(out_wav) and os.path.getsize(out_wav) > 0:
        return out_wav

    if os.path.exists(in_wav) and in_wav != out_wav:
        try:
            import shutil
            shutil.copyfile(in_wav, out_wav)
        except Exception:
            pass
    return out_wav if os.path.exists(out_wav) else None


class CosyVoiceCloner:
    

    _instance = None
    _lock = threading.Lock()





    _CACHE_MAX = 50


    _CACHE_HARD_CAP = 60


    _unavailable = False
    _unavailable_reason = ""

    def __init__(self):
        self.model = None



        if _COSYVOICE_DISABLED:
            self._unavailable = True
            self._unavailable_reason = _COSYVOICE_DISABLE_REASON
        elif not cosyvoice_weights_present():
            self._unavailable = True
            self._unavailable_reason = (
                "CosyVoice 本地权重缺失（需 %s），已禁用并自动回退 OpenVoice"
                % _cosyvoice_weights_dir())
        else:
            self._unavailable = False
            self._unavailable_reason = ""
        self._load_lock = threading.Lock()





        self._synth_lock = threading.Lock()
        self._cv = None
        self._load_wav = None
        self._torch = None


        self._cache_dir = os.path.join(_app_base(), "cosyvoice_cache")
        self._cache = OrderedDict()
        self._cache_lock = threading.Lock()

        self._prune_cache_dir()

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    def _cache_key(self, text, speed, prompt_sig=""):



        h = hashlib.md5(("%s|%r|seed%d|%s" % (
            text, round(speed, 3), self._cosyvoice_seed(),
            prompt_sig)).encode("utf-8")).hexdigest()
        return h

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

    def warm_up(self):
        
        if self.model is not None:
            return
        def _run():
            try:
                self._ensure_model()
            except Exception as e:
                print("CosyVoice 预热失败（首次合成时会再尝试）:", e)
        t = threading.Thread(target=_run, daemon=True)
        t.start()

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

    def _return_with_cache(self, out, text, speed, prompt_sig=""):
        
        key = self._cache_key(text, speed, prompt_sig)
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

    def _resolve_prompt(self, profile):

        prompt_wav = (profile or {}).get("prompt_wav")
        prompt_text = (profile or {}).get("prompt_text")
        cfg = _cached_config()
        if not prompt_wav:
            prompt_wav = cfg.get("cosyvoice_prompt_wav")
        if not prompt_text:
            prompt_text = cfg.get("cosyvoice_prompt_text")
        if not prompt_wav or not os.path.exists(prompt_wav):
            raise RuntimeError(
                "CosyVoice 需要参考音频(prompt_wav)：请在 tts_config.json 设置 "
                "cosyvoice_prompt_wav 为当初提取音色用的原始录音路径，并确保文件存在。")
        if not prompt_text:
            raise RuntimeError(
                "CosyVoice 需要参考音频的文字稿(prompt_text)：请在 tts_config.json 设置 "
                "cosyvoice_prompt_text（即 prompt_wav 这段音频对应的文字）。")
        return prompt_wav, prompt_text

    def _ensure_model(self):
        if self.model is not None:
            return



        if _COSYVOICE_DISABLED:
            self._unavailable = True
            self._unavailable_reason = _COSYVOICE_DISABLE_REASON
            raise CosyVoiceUnavailable(_COSYVOICE_DISABLE_REASON)
        if not cosyvoice_weights_present():
            self._unavailable = True
            self._unavailable_reason = (
                "CosyVoice 本地权重缺失（需 %s），已禁用并自动回退 OpenVoice"
                % _cosyvoice_weights_dir())
            raise CosyVoiceUnavailable(self._unavailable_reason)
        with self._load_lock:
            if self.model is not None:
                return
            try:
                print("CosyVoice 正在加载模型（首次会下载，请稍候）…")


                _ensure_real_torchaudio()
                _ensure_real_sklearn()
                ensure_cosyvoice_on_path()
                from cosyvoice.cli.cosyvoice import CosyVoice2
                import cosyvoice.utils.file_utils as _fu


                _fu.load_wav = load_wav
                import torch
                cfg = _cached_config()
                model_id = cfg.get("cosyvoice_model", "iic/CosyVoice2-0.5B")
                local = _cosyvoice_weights_dir()
                if os.path.isdir(local):
                    model_id = local
                self._cv = CosyVoice2(model_id, load_jit=False, load_trt=False, fp16=False)
                self._load_wav = load_wav
                self._torch = torch



                self.model = True
                print("CosyVoice 模型加载完成")
            except Exception as e:





                self._unavailable = True
                self._unavailable_reason = str(e)
                CosyVoiceCloner._unavailable = True
                CosyVoiceCloner._unavailable_reason = str(e)
                print("CosyVoice 模型加载失败（已标记不可用，将回退）:", e)
                raise

    def synthesize(self, text, profile, lang="zh", enable_emotion=True, speed=1.0):
        
        with self._synth_lock:
            return self._synthesize(text, profile, lang, enable_emotion, speed)

    def _seed_rng(self, seed):
        
        try:
            import random as _random
            import numpy as _np
            torch = self._torch
            torch.manual_seed(seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(seed)
            _random.seed(seed)
            _np.random.seed(seed)
        except Exception:
            pass

    def _cosyvoice_seed(self):
        cfg = _cached_config()
        s = cfg.get("cosyvoice_seed", None)
        if isinstance(s, int):
            return s

        return 1234

    def _synthesize(self, text, profile, lang="zh", enable_emotion=True, speed=1.0):
        self._ensure_model()
        prompt_wav, prompt_text = self._resolve_prompt(profile)



        prompt_sig = ""
        try:
            _st = os.stat(prompt_wav)
            prompt_sig = "%d_%d" % (int(_st.st_mtime), _st.st_size)
        except Exception:
            prompt_sig = ""
        torch = self._torch


        self._seed_rng(self._cosyvoice_seed())


        chunks = []
        for item in self._cv.inference_zero_shot(
                text, prompt_text, prompt_wav, stream=True, speed=speed):
            chunks.append(item["tts_speech"])
        if not chunks:
            raise RuntimeError("CosyVoice 未返回音频")
        audio = torch.cat(chunks, dim=1)  # [1, T]
        import soundfile as sf
        sr = 24000
        out = tempfile.mktemp(suffix=".wav")
        sf.write(out, audio.squeeze(0).cpu().numpy(), sr)
        out = _resample_to_playback_rate(out, target_sr=44100)
        out = _normalize_loudness(out)
        out = _trim_trailing_silence(out, max_silence=0.2)


        return self._return_with_cache(out, text, speed, prompt_sig)


# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
def _clean_prompt_text(t):
    import re
    t = re.sub(r"[\s，。！？、；：\"'（）()\[\]【】]+$", "", t)
    t = re.sub(r"^[\s，。！？、；：\"'（）()\[\]【】]+", "", t)
    return t.strip()





_whisper_cache = {}


def _get_whisper(model_size="small"):
    m = _whisper_cache.get(model_size)
    if m is None:
        import whisper
        m = whisper.load_model(model_size)
        _whisper_cache[model_size] = m
    return m





RECOMMENDED_VOICE_TEXT = (
    "春天来了，花儿红，鸟儿唱，风轻轻吹过山坡。"
    "请你慢慢说话，声音要清晰，高低起伏都要有。"
    "我爱学习，也爱生活，一天比一天更快乐。"
)


def _tonal_variety(samples, sr):
    
    try:
        import numpy as np
        import librosa
        if sr > 8000:
            samples = librosa.resample(samples.astype(np.float32),
                                       orig_sr=sr, target_sr=8000)
            sr = 8000
        f0 = librosa.yin(samples, fmin=80, fmax=400, sr=sr)
        voiced = f0[np.isfinite(f0) & (f0 > 0)]
        if len(voiced) < 8:
            return 0.0
        std = float(np.std(voiced))
        return min(1.0, max(0.0, std / 50.0))
    except Exception:
        return 0.0


def _tonal_variety_file(path):
    try:
        import soundfile as sf
        data, sr = sf.read(path, dtype="float32", always_2d=False)
        if data.ndim > 1:
            data = data.mean(axis=1)
        return _tonal_variety(data, sr)
    except Exception:
        return 0.0


def _best_speech_window(audio_path, window=10.0, hop=0.5, sr=16000,
                        tonal_weight=0.6):
    
    try:
        import soundfile as sf
        import numpy as np
        data, _ = sf.read(audio_path, dtype="float32", always_2d=False)
        if data.ndim > 1:
            data = data.mean(axis=1)
        n = len(data)
        if n < int(window * sr):
            return 0.0
        win = int(window * sr)
        frame = max(1, int(hop * sr))

        energies = []
        i = 0
        while i + win <= n:
            seg = data[i:i + win]
            energies.append((i / sr, float(np.sqrt(np.mean(seg * seg)))))
            i += frame
        if not energies:
            return 0.0
        max_e = max(e for _, e in energies)
        if max_e <= 0:
            return 0.0
        best_start, best_score = 0.0, -1.0
        for start, energy in energies:

            if energy < 0.1 * max_e:
                score = energy / max_e
            else:
                s0 = int(start * sr)
                tv = _tonal_variety(data[s0:s0 + win], sr)


                score = (energy / max_e) * (1.0 + tonal_weight * tv)
            if score > best_score:
                best_score = score
                best_start = start
        return best_start
    except Exception:
        return 0.0


def prepare_cosyvoice_prompt(src, sample_sec=18, ref_dur=10, model="small"):
    
    ffmpeg = _ffmpeg()
    out_dir = _app_base()
    full = os.path.join(out_dir, "_prompt_full.wav")
    full_dn = os.path.join(out_dir, "_prompt_full_denoised.wav")
    ref = os.path.join(out_dir, "cosyvoice_prompt_ref.wav")
    try:

        subprocess.run([ffmpeg, "-y", "-i", src, "-ss", "0", "-t",
                        str(sample_sec), "-vn", "-ac", "1", "-ar", "16000",
                        full], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True, timeout=300)


        analyze = _denoise_wav(full, full_dn) or full





        _start = _best_speech_window(analyze, window=ref_dur, sr=16000)

        _max_start = max(0.0, sample_sec - ref_dur)
        if _start < 0 or _start > _max_start:
            _start = 0.0
        subprocess.run([ffmpeg, "-y", "-i", analyze, "-ss", str(_start), "-t",
                        str(ref_dur), "-vn", "-ac", "1", "-ar", "16000", ref],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=True, timeout=300)
        print("prepare_cosyvoice_prompt：参考段起点 %.1fs（人声最密+语调最丰富窗口）" % _start)


        wmodel = _get_whisper(model)
        res = wmodel.transcribe(ref, language="zh", fp16=False, verbose=False)
        text = _clean_prompt_text(res.get("text", "") or "")


        if not text and analyze != ref:
            res2 = wmodel.transcribe(analyze, language="zh", fp16=False, verbose=False)
            text = _clean_prompt_text(res2.get("text", "") or "")


        if not text:
            print("prepare_cosyvoice_prompt：未从音频中识别到人声文字")
            return None, None, ""


        cfg = _cached_config()
        cfg["cosyvoice_prompt_wav"] = ref
        cfg["cosyvoice_prompt_text"] = text[:24] if text else ""
        save_tts_config(cfg)


        _cache_dir = os.path.join(out_dir, "cosyvoice_cache")
        if os.path.isdir(_cache_dir):
            for _f in os.listdir(_cache_dir):
                try:
                    os.remove(os.path.join(_cache_dir, _f))
                except Exception:
                    pass



        warn = ""
        try:
            tv = _tonal_variety_file(ref)
            no_speech = float(res.get("no_speech_prob", 0.0) or 0.0)
            tlen = len(text.strip())
            if tv < 0.12:
                warn = ("参考音语调偏单调，长文本可能读错字；建议用「推荐录制文本」"
                        "录一段清晰、起伏明显的人声再提取")
            elif tlen < 6:
                warn = "参考音转写的文字太少，克隆稳定性差；建议录 10~15 秒清晰人声再提取"
            elif no_speech > 0.6:
                warn = "参考音被识别为疑似无语音，清晰度可能差；请换清晰人声再提取"
        except Exception:
            warn = ""
        return ref, cfg["cosyvoice_prompt_text"], warn
    except Exception as e:
        print("prepare_cosyvoice_prompt 失败:", e)
        import traceback
        traceback.print_exc()
        return None, None, ""
    finally:

        for _tmp in (full, full_dn):
            try:
                if _tmp and os.path.exists(_tmp) and _tmp != ref:
                    os.remove(_tmp)
            except Exception:
                pass
