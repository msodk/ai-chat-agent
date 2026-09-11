# -*- coding: utf-8 -*-

import os
import sys
import shutil
import time

PROJECT = r"D:\AI\ai-chat-agent"
VENV_SP = os.path.join(PROJECT, ".venv", "Lib", "site-packages")
DIST    = os.path.join(PROJECT, "dist", "AI聊天智能体桌面版")
INTERNAL= os.path.join(DIST, "_internal")
REPO    = r"D:\AI\CosyVoice"
WEIGHTS = r"D:\AI\CosyVoice2-0.5B"


BLACKLIST = {
    "torch", "torchaudio", "torchgen", "numpy", "onnxruntime",
    "PyQt5", "PyQt6", "PySide2", "PySide6", "sip", "shiboken", "qt",
    "pip", "setuptools", "wheel", "pkg_resources", "distutils",
    "_distutils_hack",
}


def _discover_cosy_deps():
    
    saved = list(sys.path)
    sys.path.insert(0, REPO)
    sys.path.insert(0, os.path.join(REPO, "third_party", "Matcha-TTS"))
    try:
        import importlib

        import cosyvoice.cli.cosyvoice  # noqa: F401
        importlib.import_module("cosyvoice")

        for m in ("transformers", "sentencepiece", "modelscope", "conformer",
                  "x_transformers", "hyperpyyaml", "omegaconf", "pyworld",
                  "wetext", "diffusers", "accelerate", "inflect", "tiktoken",
                  "whisper", "einops", "tokenizers", "safetensors",
                  "huggingface_hub", "regex", "filelock", "fsspec"):
            try:
                importlib.import_module(m)
            except Exception:
                pass
    except Exception as e:
        print("[WARN] cosyvoice 导入探测异常（部分依赖可能漏收集）:", repr(e))
    finally:
        sys.path[:] = saved

    pkgs = set()
    for name, mod in list(sys.modules.items()):
        if mod is None:
            continue
        fn = getattr(mod, "__file__", None)
        if not fn:

            pth = getattr(mod, "__path__", None)
            hit = False
            if pth:
                for p in pth:
                    if os.path.abspath(p).startswith(VENV_SP):
                        hit = True
                        break
            if not hit:
                continue
            top = name.split(".")[0]
            if top not in BLACKLIST:
                pkgs.add(top)
            continue
        fn = os.path.abspath(fn)
        if not fn.startswith(VENV_SP):
            continue
        top = name.split(".")[0]
        if top in BLACKLIST:
            continue
        pkgs.add(top)
    return sorted(pkgs)


def _rename_aside(path):
    if not os.path.exists(path):
        return
    bak = "%s_old_%d" % (path, int(time.time()))
    try:
        os.rename(path, bak)
        print("    stashed:", os.path.basename(path), "->", os.path.basename(bak))
    except Exception as e:
        print("    [WARN] 无法暂存", path, ":", e)


def _copy_top(pkg):
    
    import importlib.util as _iu
    src_dir = os.path.join(VENV_SP, pkg)
    dst = os.path.join(INTERNAL, pkg)



    spec = _iu.find_spec(pkg, [VENV_SP])
    if spec is not None and spec.origin and spec.origin not in ("namespace",) \
            and os.path.isfile(spec.origin) \
            and spec.origin.lower().endswith((".pyd", ".so", ".dll")):
        d = os.path.join(INTERNAL, os.path.basename(spec.origin))
        if not os.path.exists(d):
            shutil.copy2(spec.origin, d)
        return os.path.getsize(d) if os.path.exists(d) else 0




    if os.path.isdir(src_dir):
        shutil.copytree(src_dir, dst, dirs_exist_ok=True)
        return sum(os.path.getsize(os.path.join(dp, f))
                   for dp, _, fs in os.walk(dst) for f in fs)
    print("  [skip] 无法定位顶层模块:", pkg)
    return 0


def _copy_metadata():
    
    n = 0
    for name in os.listdir(VENV_SP):
        low = name.lower()
        if not (low.endswith(".dist-info") or low.endswith(".egg-info")):
            continue
        src = os.path.join(VENV_SP, name)
        dst = os.path.join(INTERNAL, name)
        if os.path.isdir(src) and not os.path.exists(dst):
            shutil.copytree(src, dst)
            n += 1
    print("    复制元数据(dist-info/egg-info) %d 个" % n)


def _copy_tree(src, dst, label):
    if not os.path.isdir(src):
        print("  [ERROR] 源不存在，跳过 %s: %s" % (label, src))
        return
    if os.path.isdir(dst):
        print("  [skip exists] %s 已存在，沿用" % label)
        return
    print("  复制 %s -> %s (请耐心，可能数 GB) ..." % (label, dst))
    shutil.copytree(src, dst)
    sz = sum(os.path.getsize(os.path.join(dp, f))
             for dp, _, fs in os.walk(dst) for f in fs)
    print("  %s 完成，约 %.2f GB" % (label, sz / 1024 ** 3))


def _stdlib_lib_dir():
    
    bp = getattr(sys, "base_prefix", None) or getattr(sys, "base_exec_prefix", None) or sys.prefix

    d = os.path.join(bp, "Lib")
    while d and not os.path.isdir(os.path.join(d, "filecmp.py")):
        parent = os.path.dirname(bp)
        if parent == bp:
            break
        bp = parent
        d = os.path.join(bp, "Lib")
    return d


def _ensure_stdlib_modules(modules=("filecmp",)):
    
    stdlib = _stdlib_lib_dir()
    if not os.path.isdir(stdlib):
        print("    [WARN] 无法定位 base Python stdlib，跳过 stdlib 补全")
        return
    n = 0
    for mod in modules:
        src = os.path.join(stdlib, mod + ".py")
        if not os.path.isfile(src):
            continue
        dst = os.path.join(INTERNAL, mod + ".py")
        if os.path.exists(dst):
            continue
        shutil.copy2(src, dst)
        n += 1
    if n:
        print("    补全 stdlib 模块 %d 个: %s" % (n, ", ".join(modules)))


def main():
    os.makedirs(INTERNAL, exist_ok=True)

    print(">>> [A] 发现并复制 CosyVoice 第三方依赖 ...")
    pkgs = _discover_cosy_deps()
    print("    待复制顶层包(%d): %s" % (len(pkgs), ", ".join(pkgs)))
    total = 0
    for p in pkgs:
        total += _copy_top(p)
    print("    依赖复制完成，约 %.2f GB" % (total / 1024 ** 3))
    _copy_metadata()
    _copy_top_extensions()
    _ensure_stdlib_modules(["filecmp"])


def _copy_top_extensions():
    
    n = 0
    for name in os.listdir(VENV_SP):
        if not name.lower().endswith((".pyd", ".so")):
            continue
        src = os.path.join(VENV_SP, name)
        dst = os.path.join(INTERNAL, name)
        if os.path.isfile(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)
            n += 1
    print("    复制顶层扩展模块(.pyd/.so) %d 个" % n)

    print(">>> [B] 复制 CosyVoice 仓库(含 Matcha-TTS) ...")
    _copy_tree(REPO, os.path.join(DIST, "CosyVoice"), "CosyVoice 仓库")

    print(">>> [C] 复制 CosyVoice2-0.5B 权重 ...")
    _copy_tree(WEIGHTS, os.path.join(DIST, "CosyVoice2-0.5B"), "CosyVoice2-0.5B 权重")

    print("=== COPY COSYVOICE DONE ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
