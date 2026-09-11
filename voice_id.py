

import wave
import struct
import math
import os
import json
import time


F0_MIN, F0_MAX = 70.0, 300.0
F0STD_MAX = 40.0
ZCR_MIN, ZCR_MAX = 0.01, 0.15
RMS_MAX = 0.25


FEAT_WEIGHTS = [0.5, 0.2, 0.15, 0.15]   # [f0, f0_std, zcr, rms]
DIST_TOL = 0.45
ACCEPT_THRESH = 0.5
ENROLL_N = 3
CALIB_ALPHA_EARLY = 0.34
CALIB_ALPHA_LATE = 0.06


def get_speaker_profile_path():
    
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "voiceprint.json")



def extract_features(wav_path):
    
    try:
        with wave.open(wav_path, 'rb') as wf:
            nch = wf.getnchannels()
            sw = wf.getsampwidth()
            fr = wf.getframerate()
            nframes = wf.getnframes()
            raw = wf.readframes(nframes)
    except Exception:
        return None
    if sw == 2:
        cnt = len(raw) // 2
        samples = struct.unpack('<' + 'h' * cnt, raw)
        maxv = 32768.0
    elif sw == 1:
        cnt = len(raw)
        samples = struct.unpack('<' + 'B' * cnt, raw)
        maxv = 128.0
    else:
        return None
    if nch == 2:
        samples = samples[0::2]
    if not samples:
        return None

    N = len(samples)
    dur = nframes / float(fr) if fr else 0.0


    sq = sum(s * s for s in samples) / N
    rms = math.sqrt(sq) / maxv


    zc = 0
    for i in range(1, N):
        if (samples[i] >= 0) != (samples[i - 1] >= 0):
            zc += 1
    zcr = zc / float(N) if N else 0.0


    f0_list = _estimate_pitch(samples, maxv, fr)
    if not f0_list:
        return None
    f0_list.sort()
    f0 = f0_list[len(f0_list) // 2]
    mean = sum(f0_list) / len(f0_list)
    f0_std = math.sqrt(sum((x - mean) ** 2 for x in f0_list) / len(f0_list))

    return {'f0': f0, 'f0_std': f0_std, 'zcr': zcr, 'rms': rms, 'duration': dur}


def _estimate_pitch(samples, maxv, sr):
    
    N = len(samples)
    win = 1024
    hop = 512
    min_lag = max(2, int(sr / 300.0))
    max_lag = min(N - 1, int(sr / 70.0))
    if max_lag <= min_lag:
        return []
    try:
        import numpy as np
        return _estimate_pitch_np(samples, maxv, sr, win, hop, min_lag, max_lag, np)
    except Exception:
        pass

    res = []
    i = 0
    windows_done = 0
    max_windows = 60
    while i + win < N and windows_done < max_windows:
        seg = samples[i:i + win]
        e = math.sqrt(sum(x * x for x in seg) / win) / maxv
        if e < 0.02:
            i += hop
            continue
        m = sum(seg) / win
        s = [x - m for x in seg]
        best_lag = 0
        best_corr = 0.0
        for lag in range(min_lag, max_lag + 1):
            c = 0
            for k in range(win - lag):
                c += s[k] * s[k + lag]
            if c > best_corr:
                best_corr = c
                best_lag = lag
        if best_lag > 0:
            denom = math.sqrt(
                sum(x * x for x in s[:win - best_lag]) *
                sum(x * x for x in s[best_lag:win]))
            norm = best_corr / denom if denom > 0 else 0
            if norm > 0.4:
                res.append(sr / best_lag)
        windows_done += 1
        i += hop
    return res


def _estimate_pitch_np(samples, maxv, sr, win, hop, min_lag, max_lag, np):
    res = []
    i = 0
    windows_done = 0
    max_windows = 60
    while i + win < len(samples) and windows_done < max_windows:
        seg = samples[i:i + win]
        e = math.sqrt(sum(x * x for x in seg) / win) / maxv
        if e < 0.02:
            i += hop
            continue
        arr = np.asarray(seg, dtype=np.float64)
        arr = arr - arr.mean()

        f = np.fft.rfft(arr)
        acf = np.fft.irfft(f * np.conjugate(f))[:max_lag + 1]
        r0 = acf[0]
        if r0 <= 0:
            i += hop
            continue

        best_lag = 0
        best_norm = 0.0
        for lag in range(min_lag, max_lag + 1):
            denom = math.sqrt(r0 * acf[lag]) if acf[lag] > 0 else 0
            norm = acf[lag] / denom if denom > 0 else 0
            if norm > best_norm:
                best_norm = norm
                best_lag = lag
        if best_lag > 0 and best_norm > 0.4:
            res.append(sr / best_lag)
        windows_done += 1
        i += hop
    return res



def _norm_vec(feat):
    f0 = max(0.0, min(1.0, (feat['f0'] - F0_MIN) / (F0_MAX - F0_MIN)))
    f0s = max(0.0, min(1.0, feat['f0_std'] / F0STD_MAX))
    zcr = max(0.0, min(1.0, (feat['zcr'] - ZCR_MIN) / (ZCR_MAX - ZCR_MIN)))
    rms = max(0.0, min(1.0, feat['rms'] / RMS_MAX))
    return [f0, f0s, zcr, rms]


def load_profile(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def save_profile(path, prof):
    try:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(prof, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _similarity(vec, pvec):
    d2 = 0.0
    for w, a, b in zip(FEAT_WEIGHTS, vec, pvec):
        d2 += w * (a - b) ** 2
    dist = math.sqrt(d2)
    return max(0.0, 1.0 - dist / DIST_TOL)


def _update_profile(path, vec, feat, is_new):
    prof = load_profile(path) or {'count': 0, 'vec': [0.0, 0.0, 0.0, 0.0],
                                  'f0_raw': 0.0, 'updated': 0.0}
    count = prof.get('count', 0)
    if is_new or count == 0:
        alpha = 1.0
    elif count < ENROLL_N:
        alpha = CALIB_ALPHA_EARLY
    else:
        alpha = CALIB_ALPHA_LATE
    old = prof.get('vec', [0.0, 0.0, 0.0, 0.0])
    newvec = [alpha * a + (1 - alpha) * b for a, b in zip(vec, old)]
    prof['vec'] = newvec
    prof['f0_raw'] = round(feat['f0'], 1)
    prof['count'] = count + 1
    prof['updated'] = time.time()
    save_profile(path, prof)


def reset_speaker_profile(profile_path=None):
    
    p = profile_path or get_speaker_profile_path()
    try:
        if os.path.exists(p):
            os.remove(p)
        return True
    except Exception:
        return False


def speaker_profile_status(profile_path=None):
    
    p = profile_path or get_speaker_profile_path()
    prof = load_profile(p)
    if not prof or prof.get('count', 0) == 0:
        return None
    return (prof['count'], prof.get('f0_raw', 0))



def speaker_verdict(wav_path, profile_path=None):
    
    prof_path = profile_path or get_speaker_profile_path()
    feat = extract_features(wav_path)
    if feat is None:




        prof = load_profile(prof_path)
        if prof is not None and prof.get('count', 0) >= ENROLL_N:
            return {'accept': False, 'confidence': 0.0,
                    'reason': '无法确认是你（无人声/纯音乐），已忽略',
                    'hint': '', 'features': None, 'enrolling': False}
        return {'accept': True, 'confidence': 0.0,
                'reason': '无法提取声纹（太短或无清晰人声），已放行',
                'hint': '', 'features': None, 'enrolling': False}

    vec = _norm_vec(feat)
    prof = load_profile(prof_path)

    if prof is None or prof.get('count', 0) == 0:

        _update_profile(prof_path, vec, feat, is_new=True)
        return {'accept': True, 'confidence': 1.0,
                'reason': '首次建档，已记录你的音色',
                'hint': '（正在熟悉你的音色，这是第 1 次）',
                'features': feat, 'enrolling': True}

    count = prof['count']
    if count < ENROLL_N:
        conf = _similarity(vec, prof['vec'])
        _update_profile(prof_path, vec, feat, is_new=False)
        return {'accept': True, 'confidence': conf,
                'reason': '建档校准中（第 %d/%d 次）' % (count + 1, ENROLL_N),
                'hint': '（正在熟悉你的音色，第 %d 次）' % (count + 1),
                'features': feat, 'enrolling': True}

    conf = _similarity(vec, prof['vec'])
    if conf >= ACCEPT_THRESH:
        _update_profile(prof_path, vec, feat, is_new=False)
        return {'accept': True, 'confidence': conf,
                'reason': '已确认是你在说话', 'hint': '',
                'features': feat, 'enrolling': False}
    return {'accept': False, 'confidence': conf,
            'reason': '不是你的声音（可能是视频 / 旁人在说话）', 'hint': '',
            'features': feat, 'enrolling': False}
