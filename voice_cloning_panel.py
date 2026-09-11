# -*- coding: utf-8 -*-

import os




try:
    import torch  # noqa: F401
except Exception:
    torch = None

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QListWidget, QListWidgetItem,
                             QFrame, QMessageBox, QProgressBar)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor

from voice_clone import (is_supported, VoiceCloner,
                         load_cloned_voices, rebuild_cloned_voices)


class CloneWorker(QThread):
    
    phase_signal = pyqtSignal(str)
    busy_signal = pyqtSignal(bool)
    progress_signal = pyqtSignal(int, str, str)
    value_signal = pyqtSignal(int)
    done_signal = pyqtSignal(int, int)

    def __init__(self, files):
        super().__init__()
        self.files = files

    def run(self):
        success = 0
        fail = 0
        total = len(self.files)


        self.busy_signal.emit(True)
        self.phase_signal.emit("正在加载 OpenVoice 模型…（首次约需十几秒，请稍候）")
        try:
            cloner = VoiceCloner.get_instance()
        except FileNotFoundError:
            self.busy_signal.emit(False)
            self.value_signal.emit(0)
            for i in range(total):
                self.progress_signal.emit(i, "❌失败", "未找到模型：请先运行「下载模型.bat」")
            self.done_signal.emit(0, total)
            return
        except Exception as e:
            self.busy_signal.emit(False)
            self.value_signal.emit(0)
            for i in range(total):
                self.progress_signal.emit(i, "❌失败", "模型初始化失败: %s" % str(e))
            self.done_signal.emit(0, total)
            return


        self.busy_signal.emit(False)
        self.phase_signal.emit("模型已就绪，开始处理文件…")


        frac_map = {"audio": 0.5, "se": 0.8, "save": 0.95}
        desc_map = {"audio": "提取音频中…", "se": "提取声纹中…", "save": "保存音色包中…"}

        def make_cb(i):
            def cb(stage):
                frac = frac_map.get(stage, 0.5)
                self.value_signal.emit(int((i + frac) / total * 100))
                self.progress_signal.emit(i, "处理中", desc_map.get(stage, stage))
            return cb

        for i, f in enumerate(self.files):
            self.value_signal.emit(int(i / total * 100))
            try:
                pt, err = cloner.extract_voice_pack(f, step_cb=make_cb(i))
                if err:
                    self.progress_signal.emit(i, "❌失败", err)
                    self.value_signal.emit(int((i + 1) / total * 100))
                    fail += 1
                else:
                    self.progress_signal.emit(
                        i, "✅完成", "已生成 %s" % os.path.basename(pt))
                    self.value_signal.emit(int((i + 1) / total * 100))
                    success += 1
            except Exception as e:
                self.progress_signal.emit(i, "❌失败", "异常: %s" % str(e))
                self.value_signal.emit(int((i + 1) / total * 100))
                fail += 1


        try:
            rebuild_cloned_voices()
        except Exception:
            pass
        self.done_signal.emit(success, fail)


class VoiceCloningPanel(QDialog):
    

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🎙️ 智能合成音色")
        self.setMinimumSize(580, 480)
        self.setAcceptDrops(True)

        self.files = []
        self.status_map = {}
        self.worker = None

        self._init_ui()
        self._refresh_existing_hint()

    # ------------------------------------------------------------------ UI
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        title = QLabel("🎙️ 智能合成音色")
        title.setStyleSheet("font-size: 21px; font-weight: bold; color: #1a202c;")
        layout.addWidget(title)

        hint = QLabel(
            "把视频（人声）或音频文件拖到下方虚线区域，可一次拖入多个。"
            "程序会自动识别声音，生成与源文件同名的音色包。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; font-size: 13px; line-height: 1.5;")
        layout.addWidget(hint)


        self.drop_frame = QFrame()
        self.drop_frame.setMinimumHeight(150)
        self.drop_frame.setFrameShape(QFrame.StyledPanel)
        self.drop_frame.setStyleSheet("""
            QFrame {
                border: 2px dashed #667eea;
                border-radius: 12px;
                background: rgba(102, 126, 234, 0.06);
            }
        """)
        df_layout = QVBoxLayout(self.drop_frame)
        df_layout.setAlignment(Qt.AlignCenter)
        self.drop_tip = QLabel("请拖入对应的视频和音频用于生成对应音色\n（支持 mp4 / mov / wav / mp3 / m4a / flac 等，可多选）")
        self.drop_tip.setAlignment(Qt.AlignCenter)
        self.drop_tip.setStyleSheet("color: #667eea; font-size: 15px; font-weight: bold;")
        df_layout.addWidget(self.drop_tip)
        layout.addWidget(self.drop_frame)


        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 8px;
                background: #fff;
                font-size: 13px;
            }
            QListWidget::item { padding: 6px 8px; }
        """)
        layout.addWidget(self.list_widget, 1)


        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("%p%")
        self.progress.setAlignment(Qt.AlignCenter)
        self.progress.setStyleSheet(
            "QProgressBar { border: none; background: #eee; border-radius: 4px; height: 8px; "
            "text-align: center; color: #555; font-size: 11px; }"
            "QProgressBar::chunk { background: #667eea; border-radius: 4px; }")
        layout.addWidget(self.progress)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #999; font-size: 12px;")
        layout.addWidget(self.status_label)


        btn_layout = QHBoxLayout()

        self.start_btn = QPushButton("🚀 开始生成音色包")
        self.start_btn.setFixedHeight(42)
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white; border: none; border-radius: 8px;
                font-size: 15px; font-weight: bold;
            }
            QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #5a7fd6, stop:1 #693d96); }
            QPushButton:disabled { background: #b9c0d6; }
        """)
        self.start_btn.clicked.connect(self.start_clone)
        btn_layout.addWidget(self.start_btn)

        self.clear_btn = QPushButton("🗑 清空列表")
        self.clear_btn.setFixedHeight(42)
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background: #f0f0f3; color: #444; border: none;
                border-radius: 8px; font-size: 15px; font-weight: bold;
            }
            QPushButton:hover { background: #e2e2e8; }
        """)
        self.clear_btn.clicked.connect(self.clear_list)
        btn_layout.addWidget(self.clear_btn)

        layout.addLayout(btn_layout)


    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        added = 0
        for u in urls:
            p = u.toLocalFile()
            if os.path.isdir(p):
                for root, _, fs in os.walk(p):
                    for fn in fs:
                        fp = os.path.join(root, fn)
                        if os.path.isfile(fp) and is_supported(fp) and fp not in self.files:
                            self.files.append(fp)
                            added += 1
            elif os.path.isfile(p) and is_supported(p) and p not in self.files:
                self.files.append(p)
                added += 1
        if added:
            for f in self.files:
                self.status_map.setdefault(f, ("排队", ""))
            self._render_list()
            self.status_label.setText(
                "已加入 %d 个文件，点击「开始生成音色包」。" % len(self.files))
        event.acceptProposedAction()


    def _render_list(self):
        self.list_widget.clear()
        for f in self.files:
            st, msg = self.status_map.get(f, ("排队", ""))
            name = os.path.basename(f)
            text = "%s    [%s]  %s" % (name, st, msg) if msg else "%s    [%s]" % (name, st)
            item = QListWidgetItem(text)
            if st == "✅完成":
                item.setForeground(QColor("#2f855a"))
            elif st == "❌失败":
                item.setForeground(QColor("#e53e3e"))
            elif st == "处理中":
                item.setForeground(QColor("#667eea"))
            self.list_widget.addItem(item)

    def _refresh_existing_hint(self):
        try:
            n = len(load_cloned_voices())
        except Exception:
            n = 0
        if n:
            self.status_label.setText("当前已有 %d 个克隆音色包，生成后可在「设置 → 语音」选用。" % n)
        else:
            self.status_label.setText("还没有克隆音色包，拖入音视频开始生成吧。")


    def start_clone(self):
        if not self.files:
            QMessageBox.information(self, "提示", "请先拖入视频或音频文件。")
            return

        if self.worker is not None and self.worker.isRunning():
            return
        self.start_btn.setEnabled(False)
        self.status_map = {f: ("排队", "") for f in self.files}
        self._render_list()
        self.status_label.setText("正在加载模型并生成音色包，请稍候…")
        self.progress.setValue(0)

        self.worker = CloneWorker(self.files)
        self.worker.phase_signal.connect(self.status_label.setText)
        self.worker.busy_signal.connect(self._on_busy)
        self.worker.progress_signal.connect(self._on_progress)
        self.worker.value_signal.connect(self.progress.setValue)
        self.worker.done_signal.connect(self._on_done)

        self.worker.finished.connect(self._cleanup_worker)
        self.worker.start()

    def _cleanup_worker(self):
        t = self.sender()
        if t is not None and t is self.worker and not t.isRunning():
            self.worker = None

    def _on_busy(self, busy):
        
        if busy:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(0)

    def _on_progress(self, index, status, msg):
        if 0 <= index < len(self.files):
            self.status_map[self.files[index]] = (status, msg)
        self._render_list()

    def _on_done(self, success, fail):
        self.start_btn.setEnabled(True)
        self.worker = None
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        if fail == 0:
            self.status_label.setText(
                "✅ 已生成 %d 个音色包！可在「设置 → 语音」中选用。" % success)
        else:
            self.status_label.setText(
                "生成完成：成功 %d，失败 %d（失败项见上方列表）。" % (success, fail))

    def clear_list(self):
        self.files = []
        self.status_map = {}
        self.list_widget.clear()
        self.progress.setValue(0)
        self._refresh_existing_hint()


if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    panel = VoiceCloningPanel()
    panel.exec_()
