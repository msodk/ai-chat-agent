# -*- coding: utf-8 -*-

import os
import sys
import shutil


def _resolve_stdlib_dir():
    
    import sysconfig
    candidate = sysconfig.get_paths().get("stdlib")
    if not candidate:

        candidate = os.path.join(os.path.dirname(sys.executable), "Lib")
    candidate = os.path.abspath(candidate)
    if not os.path.isdir(candidate):
        raise RuntimeError("无法定位 stdlib 目录：%s" % candidate)
    return candidate



_SKIP_PACKAGES = frozenset({
    "site-packages", "lib-tk", "idlelib", "lib2to3",
    "tkinter", "turtledemo",
    # Windows installer bits:
    "ensurepip", "venv",
})


_SKIP_TOP_MODULES = frozenset({
    "__hello__", "_osx_support",
    "antigravity", "this", "tabnanny",
    "turtle",
    "cgi", "cgitb",
    "imghdr", "sndhdr", "mailbox", "mailcap", "uu", "xdrlib",
    "telnetlib", "nntplib", "imaplib", "poplib",
    "pipes", "pty",
    "crypt", "sched", "shelve", "modulefinder", "pyclbr", "symtable",
})


def _iter_missing_pyc(bundle_internal, stdlib_dir):
    
    pyc_suffix = ".cpython-%d%d.pyc" % sys.version_info[:2]
    short_suffix = ".pyc"


    top_cache = os.path.join(stdlib_dir, "__pycache__")
    if os.path.isdir(top_cache):
        for f in os.listdir(top_cache):
            if not f.endswith(pyc_suffix):
                continue
            modname = f[: -len(pyc_suffix)]
            if modname.startswith("_") and modname == "__hello__":
                continue
            if modname in _SKIP_TOP_MODULES:
                continue
            dest_pyc = os.path.join(bundle_internal, modname + short_suffix)
            if os.path.exists(dest_pyc):
                continue
            yield ("", modname, os.path.join(top_cache, f), dest_pyc)


    for entry in os.listdir(stdlib_dir):
        if entry in _SKIP_PACKAGES:
            continue
        pkg_dir = os.path.join(stdlib_dir, entry)
        init_py = os.path.join(pkg_dir, "__init__.py")
        if not os.path.isfile(init_py):
            continue
        cache_dir = os.path.join(pkg_dir, "__pycache__")
        if not os.path.isdir(cache_dir):
            continue
        bun_pkg_dir = os.path.join(bundle_internal, entry)
        if not os.path.isdir(bun_pkg_dir):

            continue
        for f in os.listdir(cache_dir):
            if not f.endswith(pyc_suffix):
                continue
            modname = f[: -len(pyc_suffix)]
            dest_pyc = os.path.join(bun_pkg_dir, modname + short_suffix)
            if os.path.exists(dest_pyc):
                continue
            yield (entry, modname, os.path.join(cache_dir, f), dest_pyc)


def _find_missing_stdlib_pyc(bundle_internal, stdlib_dir):
    return list(_iter_missing_pyc(bundle_internal, stdlib_dir))


def main(argv):

    if len(argv) > 1:
        dist_root = os.path.abspath(argv[1])
    else:
        dist_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "dist", "AI聊天智能体桌面版")
        )

    bundle_internal = os.path.join(dist_root, "_internal")
    if not os.path.isdir(dist_root):
        print("[copy_stdlib_pyc] 错误：dist 目录不存在：%s" % dist_root)
        return 2
    if not os.path.isdir(bundle_internal):
        print("[copy_stdlib_pyc] 错误：_internal/ 不存在：%s" % bundle_internal)
        return 2


    stdlib_dir = _resolve_stdlib_dir()


    missing = _find_missing_stdlib_pyc(bundle_internal, stdlib_dir)
    if not missing:
        print("[copy_stdlib_pyc] 0 个缺失，无需补拷（已健康）")
        return 0


    n_ok = 0
    n_err = 0
    n_skip = 0
    for pkg, mod, src, dest in missing:
        try:

            dest_dir = os.path.dirname(dest)
            if not os.path.isdir(dest_dir):
                os.makedirs(dest_dir, exist_ok=True)
            shutil.copyfile(src, dest)
            n_ok += 1
        except Exception as e:
            print("[copy_stdlib_pyc] 拷贝失败 %s/%s: %s" % (pkg, mod, e))
            n_err += 1

    print("[copy_stdlib_pyc] 补拷 %d 个 / 错误 %d 个（stdlib=%s，dist=%s）"
          % (n_ok, n_err, stdlib_dir, dist_root))
    for pkg, mod, src, dest in missing:
        status = "OK" if os.path.exists(dest) else "FAIL"
        rel = os.path.relpath(dest, dist_root)
        tag = (pkg + "/") if pkg else "."
        print("  [%s] %s%s → %s" % (status, tag, mod, rel))
    return 0 if n_err == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
