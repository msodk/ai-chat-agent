# -*- mode: python ; coding: utf-8 -*-

import os

PROJ = os.path.abspath(SPECPATH)










a = Analysis(
    [os.path.join(PROJ, 'main_desktop.py')],
    pathex=[PROJ],
    binaries=[],








    datas=[(os.path.join(PROJ, 'checkpoints_v2'), 'checkpoints_v2')],
    hiddenimports=[

        'openvoice', 'openvoice.api', 'openvoice.se_extractor', 'openvoice.text',

        'numpy', 'scipy', 'scipy._cyutility', 'librosa', 'soundfile', 'numba',
        'inflect', 'unidecode', 'pypinyin', 'cn2an', 'jieba', 'langid',
        'eng_to_ipa', 'wavmark', 'imageio_ffmpeg', 'pydub',
        # GUI / TTS
        'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets', 'PyQt5.QtMultimedia',
        'PyQt5.sip', 'pyttsx3', 'comtypes',

        'win32job', 'win32api', 'win32con',


        'backports', 'backports.tarfile',

        'voice_clone', 'voice_cloning_panel',


        'typing_extensions', 'sympy', 'filelock', 'jinja2', 'networkx',
        'fsspec', 'mpmath', 'markupsafe', 'yaml', 'pickletools',

        'filecmp',




        'tqdm', 'tqdm.contrib', 'tqdm.contrib.concurrent', 'tqdm.contrib.itertools',
        'tqdm.contrib.logging', 'tqdm.contrib.bells', 'tqdm.contrib.utils_worker',
        'tqdm.contrib.discord', 'tqdm.contrib.slack', 'tqdm.contrib.telegram',




        #   · logging.config / html.parser / xmlrpc.server


        #   · _markupbase


        #   · compileall

        #   · zoneinfo.{__init__,_common,_tzpath}



        'logging.config', 'html.parser', 'xmlrpc.server',
        '_markupbase', 'compileall',
        'zoneinfo', 'zoneinfo._common', 'zoneinfo._tzpath',
    ],
    hookspath=[],
    hooksconfig={},


    runtime_hooks=['pyi_rth_torch_dll.py', 'pyi_rth_inspect_source.py'],


    excludes=['sklearn', 'tensorflow', 'tensorboard', 'keras', 'pandas',
              'matplotlib', 'nose', 'pytest', 'Cython',
              'torch', 'torchaudio',
              'torch.distributed', 'torch.testing', 'torch.utils.tensorboard',




              'transformers', 'sentencepiece', 'modelscope', 'x_transformers'],







    module_collection_mode={'openvoice': 'pyz+py'},



    noarchive=True,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AI聊天智能体桌面版',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=os.path.join(PROJ, 'version_info.txt'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='AI聊天智能体桌面版',
)
