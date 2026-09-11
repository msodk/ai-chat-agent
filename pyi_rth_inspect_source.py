# -*- coding: utf-8 -*-

import inspect
import os
import sys
import types


def _patch_inspect_for_frozen():
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass or not getattr(sys, "frozen", False):
        return

    _orig_getsourcefile = inspect.getsourcefile

    def _candidate_py_paths(module_name, module_file):
        
        candidates = []
        if module_name:
            parts = module_name.split(".")
            candidates.append(os.path.join(meipass, *parts) + ".py")
            candidates.append(os.path.join(meipass, *parts, "__init__.py"))
        if module_file:


            if module_file.endswith(".pyc"):
                candidates.append(module_file[:-1])  # .py
            elif module_file.endswith(".py"):
                candidates.append(module_file)

            if meipass in module_file and module_file.endswith(".py"):
                candidates.append(module_file)
        return candidates

    def _resolve_sourcefile(obj):

        module_name = None
        module_file = None
        if isinstance(obj, types.FunctionType):
            module_name = obj.__module__
            if obj.__code__:
                module_file = obj.__code__.co_filename
        elif isinstance(obj, type):
            module_name = obj.__module__
            module_file = getattr(sys.modules.get(module_name), "__file__", None)
        elif hasattr(obj, "__module__"):
            module_name = obj.__module__


        if not module_name:
            try:
                module = inspect.getmodule(obj)
                if module is not None:
                    module_name = getattr(module, "__name__", None)
                    module_file = getattr(module, "__file__", module_file)
            except Exception:
                pass


        if module_name and module_name in sys.modules:
            module_file = getattr(sys.modules[module_name], "__file__", module_file)

        for candidate in _candidate_py_paths(module_name, module_file):
            if candidate and os.path.isfile(candidate):
                return candidate
        return None

    def _getsourcefile(obj):
        try:
            result = _orig_getsourcefile(obj)
            if result is not None:
                return result
        except Exception:
            pass
        return _resolve_sourcefile(obj)

    inspect.getsourcefile = _getsourcefile


_patch_inspect_for_frozen()





def _patch_typeguard_for_frozen():
    if not getattr(sys, "frozen", False):
        return
    try:
        import typeguard._decorators as _tg

        def _typechecked(_func=None, **kwargs):
            if _func is None:
                return lambda f: f
            return _func

        _tg.typechecked = _typechecked

        try:
            import typeguard
            typeguard.typechecked = _typechecked
        except Exception:
            pass
    except Exception:
        pass


_patch_typeguard_for_frozen()
