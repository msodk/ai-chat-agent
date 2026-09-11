# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import tempfile
import threading

_FFMPEG_CACHE = None
_FFMPEG_LOCK = threading.Lock()


def get_ffmpeg_exe():
    
    global _FFMPEG_CACHE
    if _FFMPEG_CACHE is not None:
        return _FFMPEG_CACHE
    with _FFMPEG_LOCK:
        if _FFMPEG_CACHE is not None:
            return _FFMPEG_CACHE
        candidates = []
        sys_ff = r"D:\AI\ffmpeg\bin\ffmpeg.exe"
        if os.path.exists(sys_ff):
            candidates.append(sys_ff)
        try:
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
            if exe and os.path.exists(exe):
                candidates.append(exe)
        except Exception:
            pass
        candidates.append("ffmpeg")
        for c in candidates:
            if c and os.path.exists(c):
                _FFMPEG_CACHE = c
                return c
        _FFMPEG_CACHE = candidates[-1]
        return _FFMPEG_CACHE


def run_ffmpeg(cmd, timeout=120, **kwargs):
    
    if sys.platform.startswith("win"):
        CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        kwargs.setdefault("creationflags", CREATE_NO_WINDOW)
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        kwargs.setdefault("startupinfo", si)
    try:
        return subprocess.run(cmd, timeout=timeout, **kwargs)
    except Exception:
        return None


def resample_to_playback_rate(wav_path, target_sr=44100):
    
    ffmpeg = get_ffmpeg_exe()
    final = tempfile.mktemp(suffix=".wav")
    cmd = [
        ffmpeg, "-y", "-i", wav_path,
        "-ar", str(target_sr), "-ac", "1", "-c:a", "pcm_s16le",
        final,
    ]
    try:
        run_ffmpeg(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    except Exception:
        return wav_path
    if os.path.exists(final) and os.path.getsize(final) > 0:
        try:
            os.replace(final, wav_path)
            return wav_path
        except Exception:
            try:
                os.remove(final)
            except Exception:
                pass
            return wav_path
    return wav_path


def normalize_loudness(wav_path, target_peak=0.92, min_gain=1.0, max_gain=8.0):
    
    try:
        import wave
        import numpy as np
        with wave.open(wav_path, "rb") as wf:
            nch = wf.getnchannels()
            sw = wf.getsampwidth()
            fr = wf.getframerate()
            n = wf.getnframes()
            data = wf.readframes(n)
        if sw != 2 or len(data) == 0:
            return wav_path
        arr = np.frombuffer(data, dtype=np.int16).astype(np.float32)
        peak = float(np.max(np.abs(arr)))
        if peak < 1.0:
            return wav_path
        target = target_peak * 32767.0
        gain = min(max_gain, max(min_gain, target / peak))



        if gain <= 1.0 + 1e-6:
            return wav_path
        arr = arr * gain
        arr = np.clip(arr, -32768.0, 32767.0)
        out = arr.astype(np.int16)
        tmp = tempfile.mktemp(suffix=".wav")
        with wave.open(tmp, "wb") as ww:
            ww.setnchannels(nch)
            ww.setsampwidth(sw)
            ww.setframerate(fr)
            ww.writeframes(out.tobytes())
        os.replace(tmp, wav_path)
    except Exception:
        return wav_path
    return wav_path


def denoise_output(wav_path, nr=6, nf=-32, hp=60):
    
    ffmpeg = get_ffmpeg_exe()
    final = tempfile.mktemp(suffix=".wav")
    af = "highpass=f=%d,afftdn=nr=%d:nf=%d" % (hp, nr, nf)
    cmd = [
        ffmpeg, "-y", "-i", wav_path,
        "-af", af,
        "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le",
        final,
    ]
    try:
        run_ffmpeg(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    except Exception:
        return wav_path
    if os.path.exists(final) and os.path.getsize(final) > 0:
        try:
            os.replace(final, wav_path)
            return wav_path
        except Exception:
            try:
                os.remove(final)
            except Exception:
                pass
            return wav_path
    return wav_path


def trim_trailing_silence(wav_path, max_silence=0.2, top_db=35):
    
    try:
        import soundfile as sf
        import numpy as np
        data, sr = sf.read(wav_path, dtype="float32", always_2d=False)
        if data.ndim > 1:
            data = data.mean(axis=1)
        n = len(data)
        if n == 0:
            return wav_path
        peak = float(np.max(np.abs(data))) or 1.0
        thresh = peak * (10 ** (-top_db / 20.0))
        if thresh <= 0:
            thresh = 1e-4

        last_speech = n - 1
        while last_speech > 0 and abs(data[last_speech]) < thresh:
            last_speech -= 1
        keep = last_speech + int(max_silence * sr) + 1
        if keep >= n:
            return wav_path
        trimmed = data[:keep]
        tmp = tempfile.mktemp(suffix=".wav")
        sf.write(tmp, trimmed, sr, subtype="PCM_16")
        os.replace(tmp, wav_path)
    except Exception:
        return wav_path
    return wav_path
