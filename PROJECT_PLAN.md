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
│   ├── __init__.py             # 包初始化
│   ├── __main__.py             # 命令行入口
│   ├── main.py                 # ReachyMiniApp 入口
│   ├── voice_assistant.py      # 语音助手服务
│   ├── satellite.py            # ESPHome 协议处理
│   ├── audio_player.py         # 音频播放器
│   ├── motion.py               # 运动控制
│   ├── models.py               # 数据模型
│   ├── entity.py               # ESPHome 基础实体
│   ├── entity_extensions.py    # 扩展实体类型 (NEW)
│   ├── reachy_controller.py    # Reachy Mini 控制器包装 (NEW)
│   ├── api_server.py           # API 服务器
│   ├── zeroconf.py             # mDNS 发现
│   └── util.py                 # 工具函数
├── wakewords/                  # 唤醒词模型（自动下载）
│   ├── okay_nabu.json
│   ├── okay_nabu.tflite
│   ├── hey_jarvis.json
│   ├── hey_jarvis.tflite
│   ├── stop.json
│   └── stop.tflite
├── sounds/                     # 音效文件（自动下载）
│   ├── wake_word_triggered.flac
│   └── timer_finished.flac
├── pyproject.toml              # 项目配置
├── README.md                   # 说明文档
├── ENTITIES.md                 # 实体使用文档 (NEW)
└── PROJECT_PLAN.md             # 项目计划
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

## ESPHome 实体规划

基于 Reachy Mini SDK 深入分析，以下实体已暴露给 Home Assistant：

### 已实现实体

| 实体类型 | 名称 | 说明 |
|---------|------|------|
| Media Player | `media_player` | 音频播放控制 |
| Voice Assistant | `voice_assistant` | 语音助手管道 |

### 已实现的控制实体 (Controls) - 可读写

#### Phase 1-3: 基础控制与姿态

| ESPHome 实体类型 | 名称 | SDK API | 范围/选项 | 说明 |
|-----------------|------|---------|----------|------|
| `Number` | `speaker_volume` | `AudioPlayer.set_volume()` | 0-100 | 扬声器音量 |
| `Select` | `motor_mode` | `set_motor_control_mode()` | enabled/disabled/gravity_compensation | 电机模式选择 |
| `Switch` | `motors_enabled` | `enable_motors()` / `disable_motors()` | on/off | 电机扭矩开关 |
| `Button` | `wake_up` | `mini.wake_up()` | - | 唤醒机器人动作 |
| `Button` | `go_to_sleep` | `mini.goto_sleep()` | - | 睡眠机器人动作 |
| `Number` | `head_x` | `goto_target(head=...)` | ±50mm | 头部 X 位置控制 |
| `Number` | `head_y` | `goto_target(head=...)` | ±50mm | 头部 Y 位置控制 |
| `Number` | `head_z` | `goto_target(head=...)` | ±50mm | 头部 Z 位置控制 |
| `Number` | `head_roll` | `goto_target(head=...)` | -40° ~ +40° | 头部翻滚角控制 |
| `Number` | `head_pitch` | `goto_target(head=...)` | -40° ~ +40° | 头部俯仰角控制 |
| `Number` | `head_yaw` | `goto_target(head=...)` | -180° ~ +180° | 头部偏航角控制 |
| `Number` | `body_yaw` | `goto_target(body_yaw=...)` | -160° ~ +160° | 身体偏航角控制 |
| `Number` | `antenna_left` | `goto_target(antennas=...)` | -90° ~ +90° | 左天线角度控制 |
| `Number` | `antenna_right` | `goto_target(antennas=...)` | -90° ~ +90° | 右天线角度控制 |

#### Phase 4: 注视控制

| ESPHome 实体类型 | 名称 | SDK API | 范围/选项 | 说明 |
|-----------------|------|---------|----------|------|
| `Number` | `look_at_x` | `look_at_world(x, y, z)` | 世界坐标 | 注视点 X 坐标 |
| `Number` | `look_at_y` | `look_at_world(x, y, z)` | 世界坐标 | 注视点 Y 坐标 |
| `Number` | `look_at_z` | `look_at_world(x, y, z)` | 世界坐标 | 注视点 Z 坐标 |

### 已实现的传感器实体 (Sensors) - 只读

#### Phase 1 & 5: 基础状态与音频传感器

| ESPHome 实体类型 | 名称 | SDK API | 说明 |
|-----------------|------|---------|------|
| `Text Sensor` | `daemon_state` | `DaemonStatus.state` | Daemon 状态 |
| `Binary Sensor` | `backend_ready` | `backend_status.ready` | 后端是否就绪 |
| `Text Sensor` | `error_message` | `DaemonStatus.error` | 当前错误信息 |
| `Sensor` | `doa_angle` | `DoAInfo.angle` | 声源方向角度 (°) |
| `Binary Sensor` | `speech_detected` | `DoAInfo.speech_detected` | 是否检测到语音 |

#### Phase 6: 诊断信息

| ESPHome 实体类型 | 名称 | SDK API | 说明 |
|-----------------|------|---------|------|
| `Sensor` | `control_loop_frequency` | `control_loop_stats` | 控制循环频率 (Hz) |
| `Text Sensor` | `sdk_version` | `DaemonStatus.version` | SDK 版本号 |
| `Text Sensor` | `robot_name` | `DaemonStatus.robot_name` | 机器人名称 |
| `Binary Sensor` | `wireless_version` | `DaemonStatus.wireless_version` | 是否为无线版本 |
| `Binary Sensor` | `simulation_mode` | `DaemonStatus.simulation_enabled` | 是否在仿真模式 |
| `Text Sensor` | `wlan_ip` | `DaemonStatus.wlan_ip` | 无线网络 IP |

#### Phase 7: IMU 传感器 (仅无线版本)

| ESPHome 实体类型 | 名称 | SDK API | 说明 |
|-----------------|------|---------|------|
| `Sensor` | `imu_accel_x` | `mini.imu["accelerometer"][0]` | X 轴加速度 (m/s²) |
| `Sensor` | `imu_accel_y` | `mini.imu["accelerometer"][1]` | Y 轴加速度 (m/s²) |
| `Sensor` | `imu_accel_z` | `mini.imu["accelerometer"][2]` | Z 轴加速度 (m/s²) |
| `Sensor` | `imu_gyro_x` | `mini.imu["gyroscope"][0]` | X 轴角速度 (rad/s) |
| `Sensor` | `imu_gyro_y` | `mini.imu["gyroscope"][1]` | Y 轴角速度 (rad/s) |
| `Sensor` | `imu_gyro_z` | `mini.imu["gyroscope"][2]` | Z 轴角速度 (rad/s) |
| `Sensor` | `imu_temperature` | `mini.imu["temperature"]` | IMU 温度 (°C) |

> **注意**: 头部位置 (x/y/z) 和角度 (roll/pitch/yaw)、身体偏航角、天线角度都是**可控制**的实体，
> 使用 `Number` 类型实现双向控制。设置新值时调用 `goto_target()`，读取当前值时调用 `get_current_head_pose()` 等。

### 实现优先级

1. **Phase 1 - 基础状态与音量** (高优先级) ✅ **已完成**
   - [x] `daemon_state` - Daemon 状态传感器
   - [x] `backend_ready` - 后端就绪状态
   - [x] `error_message` - 错误信息
   - [x] `speaker_volume` - 扬声器音量控制

2. **Phase 2 - 电机控制** (高优先级) ✅ **已完成**
   - [x] `motors_enabled` - 电机开关
   - [x] `motor_mode` - 电机模式选择 (enabled/disabled/gravity_compensation)
   - [x] `wake_up` / `go_to_sleep` - 唤醒/睡眠按钮

3. **Phase 3 - 姿态控制** (中优先级) ✅ **已完成**
   - [x] `head_x/y/z` - 头部位置控制
   - [x] `head_roll/pitch/yaw` - 头部角度控制
   - [x] `body_yaw` - 身体偏航角控制
   - [x] `antenna_left/right` - 天线角度控制

4. **Phase 4 - 注视控制** (中优先级) ✅ **已完成**
   - [x] `look_at_x/y/z` - 注视点坐标控制

5. **Phase 5 - 音频传感器** (低优先级) ✅ **已完成**
   - [x] `doa_angle` - 声源方向
   - [x] `speech_detected` - 语音检测

6. **Phase 6 - 诊断信息** (低优先级) ✅ **已完成**
   - [x] `control_loop_frequency` - 控制循环频率
   - [x] `sdk_version` - SDK 版本
   - [x] `robot_name` - 机器人名称
   - [x] `wireless_version` - 无线版本标识
   - [x] `simulation_mode` - 仿真模式标识
   - [x] `wlan_ip` - 无线 IP 地址

7. **Phase 7 - IMU 传感器** (可选，仅无线版本) ✅ **已完成**
   - [x] `imu_accel_x/y/z` - 加速度计
   - [x] `imu_gyro_x/y/z` - 陀螺仪
   - [x] `imu_temperature` - IMU 温度

---

## 🎉 所有实体已完成！

**总计：30+ 个实体**
- Phase 1: 4 个实体
- Phase 2: 4 个实体
- Phase 3: 9 个实体
- Phase 4: 3 个实体
- Phase 5: 2 个实体
- Phase 6: 6 个实体
- Phase 7: 7 个实体

### SDK 数据结构参考

```python
# 电机控制模式
class MotorControlMode(str, Enum):
    Enabled = "enabled"              # 扭矩开启，位置控制
    Disabled = "disabled"            # 扭矩关闭
    GravityCompensation = "gravity_compensation"  # 重力补偿模式

# Daemon 状态
class DaemonState(Enum):
    NOT_INITIALIZED = "not_initialized"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"

# 完整状态
class FullState:
    control_mode: MotorControlMode
    head_pose: XYZRPYPose  # x, y, z (m), roll, pitch, yaw (rad)
    head_joints: list[float]  # 7 个关节角度
    body_yaw: float
    antennas_position: list[float]  # [right, left]
    doa: DoAInfo  # angle (rad), speech_detected (bool)

# IMU 数据 (仅无线版本)
imu_data = {
    "accelerometer": [x, y, z],  # m/s²
    "gyroscope": [x, y, z],      # rad/s
    "quaternion": [w, x, y, z],  # 姿态四元数
    "temperature": float         # °C
}

# 安全限制
HEAD_PITCH_ROLL_LIMIT = [-40°, +40°]
HEAD_YAW_LIMIT = [-180°, +180°]
BODY_YAW_LIMIT = [-160°, +160°]
YAW_DELTA_MAX = 65°  # 头部与身体偏航角最大差值
```

### ESPHome 协议实现说明

ESPHome 协议通过 protobuf 消息与 Home Assistant 通信。需要实现以下消息类型：

```python
from aioesphomeapi.api_pb2 import (
    # Number 实体 (音量/角度控制)
    ListEntitiesNumberResponse,
    NumberStateResponse,
    NumberCommandRequest,

    # Select 实体 (电机模式)
    ListEntitiesSelectResponse,
    SelectStateResponse,
    SelectCommandRequest,

    # Button 实体 (唤醒/睡眠)
    ListEntitiesButtonResponse,
    ButtonCommandRequest,

    # Switch 实体 (电机开关)
    ListEntitiesSwitchResponse,
    SwitchStateResponse,
    SwitchCommandRequest,

    # Sensor 实体 (数值传感器)
    ListEntitiesSensorResponse,
    SensorStateResponse,

    # Binary Sensor 实体 (布尔传感器)
    ListEntitiesBinarySensorResponse,
    BinarySensorStateResponse,

    # Text Sensor 实体 (文本传感器)
    ListEntitiesTextSensorResponse,
    TextSensorStateResponse,
)
```

## 参考项目

- [OHF-Voice/linux-voice-assistant](https://github.com/OHF-Voice/linux-voice-assistant)
- [pollen-robotics/reachy_mini](https://github.com/pollen-robotics/reachy_mini)
