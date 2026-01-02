# Reachy Mini Home Assistant Voice Assistant - 项目计划

## 项目概述

将 Home Assistant 语音助手功能集成到 Reachy Mini 机器人，通过 ESPHome 协议与 Home Assistant 通信。

## 核心设计原则

1. **零配置安装** - 用户只需安装应用，无需手动配置
2. **使用 Reachy Mini 原生硬件** - 使用机器人自带的麦克风和扬声器
3. **Home Assistant 集中管理** - 所有配置在 Home Assistant 端完成
4. **运动反馈** - 语音交互时提供头部运动和天线动画反馈

## 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                      Reachy Mini                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ Microphone  │→ │ Wake Word   │→ │ ESPHome Protocol    │ │
│  │ (ReSpeaker) │  │ Detection   │  │ Server (Port 6053)  │ │
│  └─────────────┘  └─────────────┘  └──────────┬──────────┘ │
│                                                │            │
│  ┌─────────────┐  ┌─────────────┐             │            │
│  │ Speaker     │← │ Audio       │←────────────┘            │
│  │ (ReSpeaker) │  │ Player      │                          │
│  └─────────────┘  └─────────────┘                          │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Motion Controller (Head + Antennas)                 │   │
│  │ - on_wakeup: 点头确认                                │   │
│  │ - on_listening: 注视用户                             │   │
│  │ - on_thinking: 抬头思考                              │   │
│  │ - on_speaking: 说话时微动                            │   │
│  │ - on_idle: 返回中立位置                              │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ ESPHome Protocol
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Home Assistant                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ STT Engine  │  │ Intent      │  │ TTS Engine          │ │
│  │ (Whisper)   │  │ Processing  │  │ (Piper/Cloud)       │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## 已完成功能

### 核心功能
- [x] ESPHome 协议服务器实现
- [x] mDNS 服务发现（自动被 Home Assistant 发现）
- [x] 本地唤醒词检测（microWakeWord）
- [x] 音频流传输到 Home Assistant
- [x] TTS 音频播放
- [x] 停止词检测

### Reachy Mini 集成
- [x] 使用 Reachy Mini SDK 的麦克风输入
- [x] 使用 Reachy Mini SDK 的扬声器输出
- [x] 头部运动控制（点头、摇头、注视）
- [x] 天线动画控制
- [x] 语音状态反馈动作

### 应用架构
- [x] 符合 Reachy Mini App 架构
- [x] 自动下载唤醒词模型
- [x] 自动下载音效文件
- [x] 无需 .env 配置文件

## 文件清单

```
reachy_mini_ha_voice/
├── reachy_mini_ha_voice/
│   ├── __init__.py          # 包初始化
│   ├── __main__.py          # 命令行入口
│   ├── main.py              # ReachyMiniApp 入口
│   ├── voice_assistant.py   # 语音助手服务
│   ├── satellite.py         # ESPHome 协议处理
│   ├── audio_player.py      # 音频播放器
│   ├── motion.py            # 运动控制
│   ├── models.py            # 数据模型
│   ├── entity.py            # ESPHome 实体
│   ├── api_server.py        # API 服务器
│   ├── zeroconf.py          # mDNS 发现
│   └── util.py              # 工具函数
├── wakewords/               # 唤醒词模型（自动下载）
│   ├── okay_nabu.json
│   ├── okay_nabu.tflite
│   ├── hey_jarvis.json
│   ├── hey_jarvis.tflite
│   ├── stop.json
│   └── stop.tflite
├── sounds/                  # 音效文件（自动下载）
│   ├── wake_word_triggered.flac
│   └── timer_finished.flac
├── pyproject.toml           # 项目配置
├── README.md                # 说明文档
└── PROJECT_PLAN.md          # 项目计划
```

## 依赖项

```toml
dependencies = [
    "reachy-mini",           # Reachy Mini SDK
    "sounddevice>=0.4.6",    # 音频处理（备用）
    "soundfile>=0.12.0",     # 音频文件读取
    "numpy>=1.24.0",         # 数值计算
    "pymicro-wakeword>=2.0.0,<3.0.0",  # 唤醒词检测
    "pyopen-wakeword>=1.0.0,<2.0.0",   # 备用唤醒词
    "aioesphomeapi>=42.0.0", # ESPHome 协议
    "zeroconf>=0.100.0",     # mDNS 发现
    "scipy>=1.10.0",         # 运动控制
    "pydantic>=2.0.0",       # 数据验证
]
```

## 使用流程

1. **安装应用**
   - 从 Reachy Mini App Store 安装
   - 或 `pip install reachy-mini-ha-voice`

2. **启动应用**
   - 应用自动启动 ESPHome 服务器（端口 6053）
   - 自动下载所需模型和音效

3. **连接 Home Assistant**
   - Home Assistant 自动发现设备（mDNS）
   - 或手动添加：设置 → 设备与服务 → 添加集成 → ESPHome

4. **使用语音助手**
   - 说 "Okay Nabu" 唤醒
   - 说出命令
   - Reachy Mini 会做出运动反馈

## 参考项目

- [OHF-Voice/linux-voice-assistant](https://github.com/OHF-Voice/linux-voice-assistant)
- [pollen-robotics/reachy_mini](https://github.com/pollen-robotics/reachy_mini)
