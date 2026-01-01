# 快速开始指南

本指南将帮助您快速设置 Reachy Mini Home Assistant 语音助手。

## 前置要求

- Reachy Mini 机器人（已连接并开机）
- 配置了 ESPHome 集成的 Home Assistant 实例
- Reachy Mini 上安装了 Python 3.8 或更高版本
- Reachy Mini 与 Home Assistant 之间的网络连接

## 步骤 1: 安装依赖

```bash
# SSH 连接到您的 Reachy Mini
ssh reachy@<reachy-ip>

# 克隆仓库
git clone https://github.com/yourusername/reachy_mini_ha_voice.git
cd reachy_mini_ha_voice

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -e .
```

## 步骤 2: 下载唤醒词模型

```bash
# 下载 Okay Nabu 模型（默认）
cd wakewords
wget https://github.com/kah0st/microWakeWord/raw/main/models/okay_nabu.tflite -O okay_nabu.tflite
cp okay_nabu.json.example okay_nabu.json

# 可选：下载 Hey Jarvis 模型
wget https://github.com/kah0st/microWakeWord/raw/main/models/hey_jarvis.tflite -O hey_jarvis.tflite
wget https://github.com/kah0st/microWakeWord/raw/main/models/hey_jarvis.json -O hey_jarvis.json

cd ..
```

## 步骤 3: 配置音频设备

```bash
# 列出可用的音频设备
python -m reachy_mini_ha_voice --list-input-devices
python -m reachy_mini_ha_voice --list-output-devices

# 记下您想使用的设备名称
```

## 步骤 4: 创建配置

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件
nano .env
```

添加您的配置：

```env
# 音频配置
AUDIO_INPUT_DEVICE=Reachy Microphone
AUDIO_OUTPUT_DEVICE=Reachy Speaker
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

## 步骤 5: 启动应用

```bash
# 启动语音助手
python -m reachy_mini_ha_voice

# 或使用自定义配置
python -m reachy_mini_ha_voice \
  --name "我的 Reachy Mini" \
  --audio-input-device "Reachy Microphone" \
  --audio-output-device "Reachy Speaker" \
  --wake-model okay_nabu
```

## 步骤 6: 连接到 Home Assistant

1. 打开 Home Assistant
2. 进入 **设置** → **设备与服务**
3. 点击 **添加集成**
4. 搜索 **ESPHome**
5. 点击 **设置另一个 ESPHome 实例**
6. 输入 Reachy Mini 的 IP 地址和端口（默认：6053）
7. 点击 **提交**

## 步骤 7: 测试

1. 说出唤醒词：**"Okay Nabu"**
2. Reachy Mini 应该会点头确认
3. 说出您的命令
4. Reachy Mini 应该会通过动作和语音回应（如果已配置）

## 故障排除

### 唤醒词未被检测到

- 检查唤醒词模型是否已下载：`ls wakewords/`
- 验证配置中的模型名称与文件匹配
- 检查麦克风是否工作：`python -m reachy_mini_ha_voice --list-input-devices`
- 如有需要，增加麦克风音量

### 无音频输出

- 检查扬声器是否工作：`python -m reachy_mini_ha_voice --list-output-devices`
- 验证配置中的音频输出设备名称
- 检查扬声器音量

### 无法连接到 Home Assistant

- 验证网络连接：`ping <home-assistant-ip>`
- 检查 ESPHome 端口（6053）是否被防火墙阻止
- 确保已安装 Home Assistant ESPHome 集成
- 检查 Home Assistant 日志中的连接错误

### 运动不工作

- 验证 Reachy Mini 已连接：检查机器人是否响应基本命令
- 检查配置中的机器人主机
- 确保 Reachy Mini SDK 已安装：`pip show reachy-mini`
- 检查机器人未处于睡眠模式

## 高级配置

### 自定义唤醒词

1. 训练您自己的唤醒词模型（参见 wakewords/README.md）
2. 将模型文件放在 wakewords/ 目录中
3. 更新配置以使用您的模型

### 多个唤醒词

```bash
# 在 wakewords/ 目录中添加其他唤醒词模型
# 更新配置以启用多个唤醒词
```

### Web 界面

```bash
# 使用 Gradio Web 界面启动
python -m reachy_mini_ha_voice --gradio

# 访问 http://<reachy-ip>:7860
```

### 无线版 Reachy Mini

```bash
# 用于无线版本
python -m reachy_mini_ha_voice --wireless
```

## 下一步

- 阅读完整的 [README_CN.md](README_CN.md) 获取详细文档
- 查看 [ARCHITECTURE_CN.md](ARCHITECTURE.md) 了解系统架构
- 查看 [REQUIREMENTS_CN.md](REQUIREMENTS.md) 了解详细需求
- 探索 [profiles/](profiles/) 进行个性化定制

## 支持

- GitHub Issues: https://github.com/yourusername/reachy_mini_ha_voice/issues
- 文档: https://github.com/yourusername/reachy_mini_ha_voice#readme
- 社区：加入我们的 Discord 服务器

---

**祝您与 Reachy Mini 交谈愉快！** 🤖