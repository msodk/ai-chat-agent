# AI 聊天智能体桌面版

一个运行在 Windows 上的通用 AI 聊天桌面客户端（界面层），基于 PyQt5。
支持本地 Ollama 大模型与云端 API 双通道对话，以及语音识别、语音克隆合成等交互能力。

## 功能

- 悬浮球 / 系统托盘 / 聊天主界面三种交互形态
- 大模型对话：内置本地 Ollama 模型预设（qwen2.5vl:7b），可在 `ai_models.json` 中自由添加任意 OpenAI 兼容端点（云端 API、本地服务等）
- 语音克隆 TTS：OpenVoice 与 CosyVoice 双后端，导入音频即可生成专属音色
- 语音识别（Whisper）与语音监听
- 朗读文字逐字跟随、屏幕监控、轻量情绪分析（关键词字典）

## 环境要求

- Windows 10/11，Python 3.12+
- 本地 Ollama 实例，或任意云端模型 API key
- OpenVoice / CosyVoice 模型权重不包含在仓库内（见 `.gitignore`），需另行下载放置

## 从源码运行

```bat
.venv\Scripts\python.exe main_desktop.py
```

## 打包为便携 exe

```bat
.venv\Scripts\python.exe build_desktop.py
```

产物输出到 `dist\AI聊天智能体桌面版\`。构建脚本会把完整 torch 包、音色包与
CosyVoice 后端一并打进目录，结果可在纯净 Windows 机器上直接运行。

## 目录结构

| 路径 | 说明 |
| --- | --- |
| `main_desktop.py` | 主程序（界面、对话、语音、托盘） |
| `voice_clone.py` / `voice_cloning_panel.py` | 语音克隆逻辑与面板 |
| `cosyvoice_tts.py` | CosyVoice TTS 后端 |
| `bridge_stt_server.py` / `bridge_tts_server.py` | 本地 STT / TTS 桥接服务 |
| `build_desktop.py` | PyInstaller 构建驱动 |
| `copy_*_to_dist.py` | 构建后的资源捆绑脚本 |
| `openvoice/` | 内置的 OpenVoice 源码 |

## 许可

仅供个人学习使用。
