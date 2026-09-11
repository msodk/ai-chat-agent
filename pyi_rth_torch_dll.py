








import os
import sys
import ctypes

kernel32 = ctypes.windll.kernel32
LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR = 0x00000100
LOAD_LIBRARY_SEARCH_SYSTEM32 = 0x00000800
LOAD_LIBRARY_SEARCH_USER_DIRS = 0x00000400
FLAGS = (LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR
         | LOAD_LIBRARY_SEARCH_SYSTEM32
         | LOAD_LIBRARY_SEARCH_USER_DIRS)


_bundle = getattr(sys, "_MEIPASS", None)
if _bundle:
    if _bundle not in sys.path:
        sys.path.insert(0, _bundle)
_exe_dir = os.path.dirname(sys.executable)
if _exe_dir not in sys.path:
    sys.path.insert(0, _exe_dir)

_search_roots = []
for base in (_bundle, _exe_dir):
    if not base:
        continue
    for pkg in ("torch", "torchaudio"):
        lib = os.path.join(base, pkg, "lib")
        if os.path.isdir(lib) and lib not in _search_roots:
            _search_roots.append(lib)

_failed = []
_loaded = 0
for lib in _search_roots:
    try:
        dlls = [f for f in os.listdir(lib) if f.lower().endswith(".dll")]
    except OSError:
        dlls = []

    for name in sorted(dlls):
        p = os.path.join(lib, name)
        h = kernel32.LoadLibraryExW(p, None, FLAGS)
        if h:
            _loaded += 1
        else:
            _failed.append((name, kernel32.GetLastError()))


try:
    _log = os.path.join(_exe_dir if _exe_dir else os.getcwd(), "torch_dll_preload.log")
    with open(_log, "w", encoding="utf-8") as _lf:
        _lf.write("roots=%s\n" % _search_roots)
        _lf.write("loaded=%d\n" % _loaded)
        if _failed:
            _lf.write("FAILED:\n")
            for _n, _e in _failed:
                _lf.write("  %s err=%d\n" % (_n, _e))
except OSError:
    pass
