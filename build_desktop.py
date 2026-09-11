# -*- coding: utf-8 -*-

import os
import sys
import shutil
import time
import subprocess
import tempfile

BUILD_TEMP = r"D:\build_temp"
PROJECT    = r"D:\AI\ai-chat-agent"
DIST       = os.path.join(PROJECT, "dist", "AI聊天智能体桌面版")
APPNAME    = "AI聊天智能体桌面版"



BUILD_OUT  = r"D:\build_out"
SPEC       = os.path.join(BUILD_TEMP, "AI聊天智能体桌面版_onedir.spec")
PY         = r"D:\AI\ai-chat-agent\.venv\Scripts\python.exe"




_USER_ARTIFACTS = (
    "cosyvoice_prompt_ref.wav",
    "voices_cloned",
    "cloned_voices.json",
    "settings.json",
    "tts_config.json",
    "ai_models.json",
)


def _snapshot_user_artifacts(dist_dir, snap_dir):
    
    if not os.path.isdir(dist_dir):
        return
    os.makedirs(snap_dir, exist_ok=True)
    for name in _USER_ARTIFACTS:
        s = os.path.join(dist_dir, name)
        if not os.path.exists(s):
            continue
        d = os.path.join(snap_dir, name)
        try:
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)
        except Exception as e:
            print("    [warn] 快照用户产物失败: %s :: %s" % (name, e))


def _restore_user_artifacts(snap_dir, dist_dir):
    
    if not os.path.isdir(snap_dir):
        return
    for name in _USER_ARTIFACTS:
        s = os.path.join(snap_dir, name)
        if not os.path.exists(s):
            continue
        d = os.path.join(dist_dir, name)
        try:
            if os.path.isdir(s):
                os.makedirs(d, exist_ok=True)
                for root, _, files in os.walk(s):
                    rel = os.path.relpath(root, s)
                    tgt = d if rel == "." else os.path.join(d, rel)
                    os.makedirs(tgt, exist_ok=True)
                    for f in files:
                        shutil.copy2(os.path.join(root, f), os.path.join(tgt, f))
            else:
                shutil.copy2(s, d)
            print("    [restore] 用户产物回灌: %s" % name)
        except Exception as e:
            print("    [warn] 回灌用户产物失败: %s :: %s" % (name, e))


def _stash_contents(src_dir):
    
    stash = "%s_old_%d" % (src_dir, int(time.time()))
    os.makedirs(stash, exist_ok=True)
    moved = 0
    skipped = 0
    for name in os.listdir(src_dir):
        s = os.path.join(src_dir, name)
        d = os.path.join(stash, name)
        ok = False
        for _ in range(3):
            try:
                os.rename(s, d)
                ok = True
                break
            except PermissionError:
                time.sleep(0.5)
        if ok:
            moved += 1
        else:
            skipped += 1
            print("    [skip] 暂无法移走(被占用): %s" % name)

    if skipped == 0:
        for _ in range(5):
            try:
                os.rmdir(src_dir)
                print("  stashed %d 项并移除旧目录 -> %s" % (moved, stash))
                return True
            except OSError:
                time.sleep(0.5)
        print("  stashed %d 项（旧目录暂留）-> %s" % (moved, stash))
        return False
    print("  stashed %d 项，%d 项仍被占用未移走 -> %s" % (moved, skipped, stash))
    return False


def _orphan_dir():
    
    d = r"D:\AI\_deleted_orphans_%s" % time.strftime("%Y-%m-%d")
    os.makedirs(d, exist_ok=True)
    return d


def _try_delete_or_orphan(path, orphan_dir):
    
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        return "removed", ""
    except OSError as e:
        try:
            base = os.path.basename(path)
            dst = os.path.join(orphan_dir, base)
            if os.path.exists(dst):
                dst = os.path.join(orphan_dir, "%s_%d" % (base, int(time.time()) % 100000))
            os.rename(path, dst)
            return "orphaned", "已移出项目(待本机清空): %s" % base
        except OSError as e2:
            return "failed", "无法清理(被占用): %s :: %s" % (base, e2)


def _purge_old_stashes(dist_dir):
    
    orphan_dir = _orphan_dir()
    parent = os.path.dirname(dist_dir)
    app_basename = os.path.basename(dist_dir)
    removed = 0
    orphaned = 0
    freed = 0.0

    def _consider(path):
        nonlocal removed, orphaned, freed
        name = os.path.basename(path)
        if not (("_old_" in name) or name.endswith(".pending_del")
                or name.startswith(app_basename + "_old_")):
            return
        if not os.path.exists(path):
            return
        sz = 0.0
        try:
            if os.path.isdir(path):
                for r, _, fs in os.walk(path):
                    for f in fs:
                        try:
                            sz += os.path.getsize(os.path.join(r, f))
                        except OSError:
                            pass
            else:
                sz = os.path.getsize(path)
        except OSError:
            pass
        status, note = _try_delete_or_orphan(path, orphan_dir)
        if status == "removed":
            removed += 1
            freed += sz
            print("    [清理] 删除旧残留: %s (%.2f GB)" % (name, sz / 1024 ** 3))
        elif status == "orphaned":
            orphaned += 1
            freed += sz
            print("    [清理] %s" % note)
        else:
            print("    [warn] %s" % note)


    if os.path.isdir(dist_dir):
        for name in os.listdir(dist_dir):
            _consider(os.path.join(dist_dir, name))

    if os.path.isdir(parent):
        for name in os.listdir(parent):
            _consider(os.path.join(parent, name))

    build_root = os.path.dirname(BUILD_OUT)  # D:\
    if os.path.isdir(build_root):
        for name in os.listdir(build_root):
            if name.startswith("build_out_old_"):
                _consider(os.path.join(build_root, name))

    if os.path.isdir(BUILD_TEMP):
        for name in os.listdir(BUILD_TEMP):
            _consider(os.path.join(BUILD_TEMP, name))

    if removed or orphaned:
        print(">>> [6/5] 清理历史旧暂存：删除 %d / 移出项目 %d，释放约 %.2f GB"
              % (removed, orphaned, freed / 1024 ** 3))


def _copy_tree_into(src, dst):
    
    if not os.path.isdir(src):
        return
    os.makedirs(dst, exist_ok=True)
    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        tgt_root = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(tgt_root, exist_ok=True)
        for f in files:
            s = os.path.join(root, f)
            d = os.path.join(tgt_root, f)
            shutil.copy2(s, d)


def _clear_dist_best_effort():
    
    if not os.path.isdir(DIST):
        return



    try:
        _rename_aside_quick(DIST)
    except Exception:
        pass
    if not os.path.isdir(DIST):
        return

    for name in os.listdir(DIST):
        try:
            _rename_aside(os.path.join(DIST, name))
        except Exception:
            pass


def _rename_aside_quick(path):
    
    if not os.path.exists(path):
        return
    new = "%s_old_%d" % (path, int(time.time() * 1000))
    os.rename(path, new)


def _rename_aside(path):
    
    if not os.path.exists(path):
        return
    new = "%s_old_%d" % (path, int(time.time()))

    for attempt in range(40):
        try:
            os.rename(path, new)
            print("  stashed:", path, "->", new)
            return
        except PermissionError:
            if attempt == 0:
                print("  [warn] 整目录改名被占用，重试中(杀软可能在扫描)...: %s" % path)
            time.sleep(1.5)

    print("  [warn] 改名重试失败，改移内容到暂存目录: %s" % path)
    _stash_contents(path)


def main():





    print(">>> [0/5] 移走旧 build/ 产物，best-effort 清理 DIST 旧内容 ...")

    _SNAP = tempfile.mkdtemp(prefix="cv_user_snap_")
    _snapshot_user_artifacts(DIST, _SNAP)
    _rename_aside(os.path.join(BUILD_TEMP, "build"))
    _clear_dist_best_effort()




    print(">>> [1/5] PyInstaller 构建（输出到 %s）..." % BUILD_OUT)
    os.makedirs(BUILD_OUT, exist_ok=True)
    built_app = os.path.join(BUILD_OUT, APPNAME)
    if os.path.isdir(built_app):
        _rename_aside(built_app)
    r = subprocess.run(
        [PY, "-m", "PyInstaller", "--noconfirm", "--distpath", BUILD_OUT, SPEC],
        cwd=BUILD_TEMP,
    )
    if r.returncode != 0:
        print("PYINSTALLER FAILED, exit=%d" % r.returncode)
        return r.returncode
    if not os.path.isdir(built_app):
        print("PYINSTALLER 未产出预期目录:", built_app)
        return 1



    print(">>> [1.5/5] 写入式把基座 app 复制到被锁定的 DIST ...")
    _copy_tree_into(built_app, DIST)


    print(">>> [2/5] 复制 torch / torchaudio / torchgen 完整包 ...")
    subprocess.run([PY, os.path.join(BUILD_TEMP, "copy_torch_to_dist.py")], check=True)


    print(">>> [3/5] 补回克隆音色包 ...")
    subprocess.run([PY, os.path.join(BUILD_TEMP, "copy_voicepack_to_dist.py")], check=True)



    print(">>> [4/5] 打进 CosyVoice 依赖 + 仓库 + 权重（完全便携）...")
    subprocess.run([PY, os.path.join(BUILD_TEMP, "copy_cosyvoice_to_dist.py")], check=True)





    print(">>> [4.5/5] 补 stdlib 子模块 pyc（防止 logging.config / html.parser 漏拷）...")
    subprocess.run([PY, os.path.join(BUILD_TEMP, "copy_stdlib_pyc_to_dist.py")], check=True)


    print(">>> [5/5] 清理构建中间产物 ...")
    for rel in ("build", "__pycache__"):
        _rename_aside(os.path.join(BUILD_TEMP, rel))
    _rename_aside(os.path.join(BUILD_TEMP, "build_pyinstaller.log"))
    _rename_aside(BUILD_OUT)

    print("=== BUILD DONE ===")
    print("产物目录:", DIST)
    torch_dir = os.path.join(DIST, "torch")
    if os.path.isdir(torch_dir):
        n = sum(len(files) for _, _, files in os.walk(torch_dir))
        print("torch 文件数:", n)


    _purge_old_stashes(DIST)


    _restore_user_artifacts(_SNAP, DIST)
    shutil.rmtree(_SNAP, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
