---
title: Reachy Mini Home Assistant Voice Assistant
emoji: 🤖
colorFrom: blue
colorTo: indigo
sdk: static
pinned: false
short_description: Home Assistant Voice Assistant for Reachy Mini
tags:
 - reachy_mini
 - reachy_mini_python_app
---

# Reachy Mini Home Assistant Voice Assistant

基于 ESPHome 协议的 Reachy Mini 语音助手，用于连接 Home Assistant。可通过 Hugging Face Spaces 一键安装和部署。

## 功能特性

- 🎤 唤醒词检测（支持多个唤醒词）
- 🔊 语音识别和合成
- 🏠 Home Assistant 指令执行
- 🤖 Reachy Mini 机器人集成
- ⏰ 定时器功能
- 📢 广播通知

## 快速开始

### 通过 Hugging Face Spaces 安装

1. 访问 [Hugging Face Spaces](https://huggingface.co/spaces)
2. 创建新的 Space，选择 Docker 模板
3. 将此仓库克隆到你的 Space
4. 等待构建完成，服务将自动启动

### 本地运行

```bash
# 克隆仓库
git clone https://huggingface.co/spaces/djhui5710/reachy_mini_ha_voice
cd reachy_mini_ha_voice

# 安装系统依赖（Linux）
sudo apt-get install portaudio19-dev build-essential libportaudio2

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装 Python 依赖
pip install -r requirements.txt
pip install -e .

# 运行
python -m reachy_mini_ha_voice --name "ReachyMini"
```

## 连接到 Home Assistant

1. 在 Home Assistant 中，进入 "设置" -> "设备与服务"
2. 点击 "添加集成" 按钮
3. 选择 "ESPHome" 然后选择 "设置另一个 ESPHome 实例"
4. 输入语音助手的 IP 地址和端口 6053
5. 点击 "提交"

## 命令行选项

```
python -m reachy_mini_ha_voice --help

选项:
  --name NAME                    设备名称（必需）
  --host HOST                    服务器地址（默认: 0.0.0.0）
  --port PORT                    服务器端口（默认: 6053）
  --audio-input-device DEVICE    音频输入设备
  --list-input-devices           列出可用的音频输入设备
  --audio-output-device DEVICE   音频输出设备
  --list-output-devices          列出可用的音频输出设备
  --wake-model MODEL             唤醒词模型（默认: okay_nabu）
  --stop-model MODEL             停止词模型（默认: stop）
  --refractory-seconds SECONDS   唤醒词冷却时间（默认: 2.0）
  --debug                        启用调试日志
```

## 包含的 Assets

项目已经包含了所有必需的唤醒词模型和声音文件，无需额外下载：

### 唤醒词模型（microWakeWord）

- `okay_nabu.tflite` - "Okay Nabu"（默认）
- `stop.tflite` - "Stop"
- `alexa.tflite` - "Alexa"
- `hey_jarvis.tflite` - "Hey Jarvis"
- `hey_home_assistant.tflite` - "Hey Home Assistant"
- `hey_luna.tflite` - "Hey Luna"
- `hey_mycroft.tflite` - "Hey Mycroft"
- `okay_computer.tflite` - "Okay Computer"
- `choo_choo_homie.tflite` - "Choo Choo Homie"

### 唤醒词模型（openWakeWord）

在 `wakewords/openWakeWord/` 目录中：
- `alexa_v0.1.tflite` - Alexa
- `hey_jarvis_v0.1.tflite` - Hey Jarvis
- `hey_mycroft_v0.1.tflite` - Hey Mycroft
- `hey_rhasspy_v0.1.tflite` - Hey Rhasspy
- `ok_nabu_v0.1.tflite` - Okay Nabu

### 声音文件

- `wake_word_triggered.flac` - 唤醒词触发时播放
- `timer_finished.flac` - 定时器结束时播放

## 音频设备配置

### 查看可用设备

```bash
# 列出音频输入设备
python -m reachy_mini_ha_voice --name Test --list-input-devices

# 列出音频输出设备
python -m reachy_mini_ha_voice --name Test --list-output-devices
```

### 指定音频设备

```bash
python -m reachy_mini_ha_voice \
  --name "ReachyMini" \
  --audio-input-device "麦克风名称" \
  --audio-output-device "扬声器名称"
```

**注意**：麦克风设备必须支持 16KHz 单声道音频。

## 唤醒词

### 默认唤醒词

- `okay_nabu`（默认）

### 使用其他唤醒词

项目已经包含了多个唤醒词模型，你可以直接使用：

```bash
# 使用 "Hey Jarvis"
python -m reachy_mini_ha_voice --name "ReachyMini" --wake-model hey_jarvis

# 使用 "Alexa"
python -m reachy_mini_ha_voice --name "ReachyMini" --wake-model alexa

# 使用 openWakeWord 版本的 "Hey Jarvis"
python -m reachy_mini_ha_voice --name "ReachyMini" \
  --wake-model hey_jarvis_v0.1 \
  --wake-word-dir wakewords/openWakeWord
```

### 添加自定义唤醒词

如果你想添加其他唤醒词：

更多唤醒词模型请访问：[home-assistant-wakewords-collection](https://github.com/fwartner/home-assistant-wakewords-collection)

## Reachy Mini 集成

### 动作反馈

语音助手会根据不同状态触发 Reachy Mini 的动作：

- **唤醒时**：头部抬起，眼睛闪烁
- **监听中**：头部轻微摆动
- **响应中**：点头或摇头
- **错误时**：头部倾斜

### 自定义动作

编辑 `reachy_mini_ha_voice/reachy_integration.py` 来自定义 Reachy Mini 的动作反馈。

## 故障排除

### 音频设备问题

如果无法检测到音频设备：

```bash
# 检查 PulseAudio 服务
systemctl --user status pulseaudio

# 重新加载 PulseAudio
pulseaudio --kill
pulseaudio --start
```

### 回声消除

启用 PulseAudio 的回声消除模块：

```bash
pactl load-module module-echo-cancel \
  aec_method=webrtc \
  aec_args="analog_gain_control=0 digital_gain_control=1 noise_suppression=1"
```

查看设备：

```bash
pactl list short sources
pactl list short sinks
```

使用回声消除设备：

```bash
python -m reachy_mini_ha_voice \
  --name "ReachyMini" \
  --audio-input-device 'Echo-Cancel Source' \
  --audio-output-device 'pipewire/echo-cancel-sink'
```

### Hugging Face Spaces 部署问题

如果构建失败：

1. 检查 Dockerfile 中的依赖是否正确
2. 确保 requirements.txt 中的版本兼容
3. 查看构建日志中的错误信息
4. 确保没有使用需要系统特权的功能

## 开发

### 运行测试

```bash
pip install -e ".[dev]"
pytest
```

### 代码格式化

```bash
black reachy_mini_ha_voice/
flake8 reachy_mini_ha_voice/
```

## 许可证

Apache License 2.0

## 致谢

本项目基于 [OHF-Voice/linux-voice-assistant](https://github.com/OHF-Voice/linux-voice-assistant) 修改而来，适配 Reachy Mini 机器人和 Hugging Face Spaces 环境。

## 相关链接

- [Home Assistant](https://www.home-assistant.io/)
- [ESPHome](https://esphome.io/)
- [Reachy Mini](https://github.com/pollen-robotics/reachy)
- [Hugging Face Spaces](https://huggingface.co/spaces)
- [Source Code](https://huggingface.co/spaces/djhui5710/reachy_mini_ha_voice)