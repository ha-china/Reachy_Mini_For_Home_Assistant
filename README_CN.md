# Reachy Mini Home Assistant 语音助手

一个运行在 **Reachy Mini 机器人**上的语音助手应用，通过 ESPHome 协议与 Home Assistant 集成。

> **注意**: 此应用直接运行在 Reachy Mini 机器人（Raspberry Pi 4）上，而不是在 Hugging Face Spaces 上运行。Hugging Face Space 仅用于代码托管和文档。

## 功能特性

- 🎤 **离线唤醒词检测**: 使用 microWakeWord 或 openWakeWord 进行本地唤醒词检测
- 🔄 **ESPHome 集成**: 通过 ESPHome 协议与 Home Assistant 无缝集成
- 🤖 **运动控制**: 完整控制 Reachy Mini 的头部运动和天线动画
- ⚡ **低延迟**: 针对实时语音交互优化
- 🎭 **表现力**: 语音反应性动作和手势

## 架构设计

本项目基于 [OHF-Voice/linux-voice-assistant](https://github.com/OHF-Voice/linux-voice-assistant) 并适配 Reachy Mini 机器人。

**核心设计**:
- STT（语音转文字）和 TTS（文字转语音）由 Home Assistant 处理
- 音频流通过 ESPHome 协议传输
- 唤醒词检测在机器人本地处理
- 运动控制增强语音交互体验

## 安装

### 前置要求

- Python 3.8 或更高版本
- Reachy Mini 机器人
- 配置了 ESPHome 集成的 Home Assistant

### 一键安装（推荐 - 无需输入命令！）

**选项 1: Web 界面（最简单）**
```bash
# 克隆仓库
git clone https://github.com/yourusername/reachy_mini_ha_voice.git
cd reachy_mini_ha_voice

# 运行安装界面
python start.py
```

然后在浏览器中打开 `http://localhost:7860`，点击 **"🚀 Start Installation"** 按钮即可！

安装将自动完成：
- ✓ 检查 Python 版本
- ✓ 创建虚拟环境
- ✓ 安装所有依赖
- ✓ 下载唤醒词模型和声音效果
- ✓ 创建配置文件
- ✓ 检查 Reachy Mini SDK 安装
- ✓ 检查音频设备

**选项 2: 命令行**
```bash
# 克隆仓库
git clone https://github.com/yourusername/reachy_mini_ha_voice.git
cd reachy_mini_ha_voice

# 运行自动安装脚本
# Linux/Mac:
./install.sh

# Windows:
powershell -ExecutionPolicy Bypass -File install.ps1
```

### 手动安装

```bash
# 克隆仓库
git clone https://github.com/yourusername/reachy_mini_ha_voice.git
cd reachy_mini_ha_voice

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -e .

# 下载唤醒词模型和声音效果
# Linux/Mac:
./download_models.sh

# Windows:
powershell -ExecutionPolicy Bypass -File download_models.ps1

# 复制环境变量模板
cp .env.example .env

# 配置设置
# 编辑 .env 文件
```

## 使用方法

### 基本使用

```bash
# 启动语音助手
python -m reachy_mini_ha_voice

# 使用自定义配置
python -m reachy_mini_ha_voice \
  --name "我的 Reachy Mini" \
  --audio-input-device "麦克风名称" \
  --audio-output-device "扬声器名称" \
  --wake-model okay_nabu
```

### 列出音频设备

```bash
# 列出可用输入设备
python -m reachy_mini_ha_voice --list-input-devices

# 列出可用输出设备
python -m reachy_mini_ha_voice --list-output-devices
```

### Web 界面

```bash
# 使用 Gradio Web 界面启动
python -m reachy_mini_ha_voice --gradio
```

### 无线版本

```bash
# 用于无线版 Reachy Mini
python -m reachy_mini_ha_voice --wireless
```

## 配置

### 环境变量

创建 `.env` 文件（从 `.env.example` 复制）：

```env
# 音频配置
AUDIO_INPUT_DEVICE=
AUDIO_OUTPUT_DEVICE=
AUDIO_SAMPLE_RATE=16000
AUDIO_CHANNELS=1
AUDIO_BLOCK_SIZE=1024

# 语音配置
WAKE_WORD=okay_nabu
WAKE_WORD_DIR=wakewords

# 运动配置
MOTION_ENABLED=true
SPEECH_REACTIVE=true

# ESPHome 配置
ESPHOME_HOST=0.0.0.0
ESPHOME_PORT=6053
ESPHOME_NAME=Reachy Mini

# 机器人配置
ROBOT_HOST=localhost
ROBOT_WIRELESS=false

# 日志
LOG_LEVEL=INFO
```

### 配置文件

您也可以使用 `config.json` 文件：

```json
{
  "audio": {
    "input_device": null,
    "output_device": null,
    "sample_rate": 16000,
    "channels": 1,
    "block_size": 1024
  },
  "voice": {
    "wake_word": "okay_nabu",
    "wake_word_dirs": ["wakewords"]
  },
  "motion": {
    "enabled": true,
    "speech_reactive": true
  },
  "esphome": {
    "host": "0.0.0.0",
    "port": 6053,
    "name": "Reachy Mini"
  },
  "robot": {
    "host": "localhost",
    "wireless": false
  }
}
```

## Home Assistant 集成

### 步骤 1: 添加 ESPHome 集成

1. 进入 Home Assistant → 设置 → 设备与服务
2. 点击"添加集成"
3. 搜索"ESPHome"
4. 点击"设置另一个 ESPHome 实例"
5. 输入 Reachy Mini 的 IP 地址和端口（默认：6053）
6. 点击"提交"

### 步骤 2: 配置语音助手

Home Assistant 应该会自动检测到语音助手。然后您可以：

- 设置语音命令
- 创建自动化
- 配置 STT/TTS 服务

### 步骤 3: 测试

1. 说出唤醒词（默认："Okay Nabu"）
2. 说出您的命令
3. Reachy Mini 应该会通过动作和语音回应

## 项目结构

```
reachy_mini_ha_voice/
├── src/
│   └── reachy_mini_ha_voice/
│       ├── __init__.py
│       ├── main.py              # 入口点
│       ├── app.py               # 主应用
│       ├── state.py             # 状态管理
│       ├── audio/               # 音频处理
│       │   ├── adapter.py       # 音频设备适配器
│       │   └── processor.py     # 音频处理器
│       ├── voice/               # 语音处理
│       │   ├── detector.py      # 唤醒词检测
│       │   ├── stt.py           # STT（备用）
│       │   └── tts.py           # TTS（备用）
│       ├── motion/              # 运动控制
│       │   ├── controller.py    # 运动控制器
│       │   └── queue.py         # 运动队列
│       ├── esphome/             # ESPHome 协议
│       │   ├── protocol.py      # 协议定义
│       │   └── server.py        # ESPHome 服务器
│       └── config/              # 配置
│           └── manager.py        # 配置管理器
├── profiles/                    # 个性化配置
│   └── default/
├── wakewords/                   # 唤醒词模型
├── pyproject.toml               # 项目配置
├── PROJECT_PLAN.md              # 项目计划
├── ARCHITECTURE.md              # 架构文档
├── REQUIREMENTS.md              # 需求文档
└── README.md                    # 本文件
```

## 开发

### 运行测试

```bash
# 安装开发依赖
pip install -e .[dev]

# 运行测试
pytest

# 运行覆盖率测试
pytest --cov=reachy_mini_ha_voice
```

### 代码风格

```bash
# 格式化代码
ruff format .

# 检查代码
ruff check .
```

## 文档

- [项目计划](PROJECT_PLAN.md) - 详细的项目计划
- [架构设计](ARCHITECTURE.md) - 系统架构和设计
- [需求文档](REQUIREMENTS.md) - 功能和技术需求

## 贡献

欢迎贡献！请随时提交 Pull Request。

## 许可证

本项目采用 Apache 2.0 许可证 - 详见 LICENSE 文件。

## 致谢

- [OHF-Voice/linux-voice-assistant](https://github.com/OHF-Voice/linux-voice-assistant) - 原始项目
- [Pollen Robotics](https://www.pollen-robotics.com/) - Reachy Mini 机器人
- [Hugging Face](https://huggingface.co/) - 平台和工具

## 支持

如有问题和疑问：
- 在 GitHub 上提 issue
- 加入 Discord 社区
- 查看文档

---

用 ❤️ 为 Reachy Mini 和 Home Assistant 社区打造