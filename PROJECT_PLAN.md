# Reachy Mini Home Assistant Voice Assistant - 项目计划

## 项目概述

将 Home Assistant 语音助手功能集成到 Reachy Mini 机器人，通过 ESPHome 协议与 Home Assistant 通信。

## 本地项目目录参考 (禁止修改参考目录内任何文件)
1. [linux-voice-assistant](linux-voice-assistant)
2. [Reachy Mini SDK](reachy_mini)
3. [reachy_mini_conversation_app](reachy_mini_conversation_app)
4. [reachy-mini-desktop-app](reachy-mini-desktop-app)

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
│  │             │  │ Processing  │  │                     │ │
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
│   ├── camera_server.py        # MJPEG 摄像头流服务器
│   ├── motion.py               # 运动控制
│   ├── models.py               # 数据模型
│   ├── entity.py               # ESPHome 基础实体
│   ├── entity_extensions.py    # 扩展实体类型
│   ├── reachy_controller.py    # Reachy Mini 控制器包装
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

#### Phase 8-12: 扩展功能

| ESPHome 实体类型 | 名称 | 说明 |
|-----------------|------|------|
| `Select` | `emotion` | 表情选择器 (Happy/Sad/Angry/Fear/Surprise/Disgust) |
| `Number` | `microphone_volume` | 麦克风音量 (0-100%) |
| `Camera` | `camera` | ESPHome Camera 实体（实时预览） |
| `Number` | `led_brightness` | LED 亮度 (0-100%) |
| `Select` | `led_effect` | LED 效果 (off/solid/breathing/rainbow/doa) |
| `Number` | `led_color_r` | LED 红色分量 (0-255) |
| `Number` | `led_color_g` | LED 绿色分量 (0-255) |
| `Number` | `led_color_b` | LED 蓝色分量 (0-255) |
| `Switch` | `agc_enabled` | 自动增益控制开关 |
| `Number` | `agc_max_gain` | AGC 最大增益 (0-30 dB) |
| `Number` | `noise_suppression` | 噪声抑制级别 (0-100%) |
| `Binary Sensor` | `echo_cancellation_converged` | 回声消除收敛状态 |

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

8. **Phase 8 - 表情控制** ✅ **已完成**
   - [x] `emotion` - 表情选择器 (Happy/Sad/Angry/Fear/Surprise/Disgust)

9. **Phase 9 - 音频控制** ✅ **已完成**
   - [x] `microphone_volume` - 麦克风音量控制 (0-100%)

10. **Phase 10 - 摄像头集成** ✅ **已完成**
    - [x] `camera` - ESPHome Camera 实体（实时预览）

11. **Phase 11 - LED 控制** ✅ **已完成**
    - [x] `led_brightness` - LED 亮度 (0-100%)
    - [x] `led_effect` - LED 效果 (off/solid/breathing/rainbow/doa)
    - [x] `led_color_r/g/b` - LED RGB 颜色 (0-255)

12. **Phase 12 - 音频处理参数** ✅ **已完成**
    - [x] `agc_enabled` - 自动增益控制开关
    - [x] `agc_max_gain` - AGC 最大增益 (0-30 dB)
    - [x] `noise_suppression` - 噪声抑制级别 (0-100%)
    - [x] `echo_cancellation_converged` - 回声消除收敛状态（只读）

---

## 🎉 Phase 1-12 实体已完成！

**已完成总计：45+ 个实体**
- Phase 1: 4 个实体 (基础状态与音量)
- Phase 2: 4 个实体 (电机控制)
- Phase 3: 9 个实体 (姿态控制)
- Phase 4: 3 个实体 (注视控制)
- Phase 5: 2 个实体 (音频传感器)
- Phase 6: 6 个实体 (诊断信息)
- Phase 7: 7 个实体 (IMU 传感器)
- Phase 8: 1 个实体 (表情控制)
- Phase 9: 1 个实体 (麦克风音量)
- Phase 10: 1 个实体 (摄像头)
- Phase 11: 5 个实体 (LED 控制)
- Phase 12: 4 个实体 (音频处理参数)

---

## 🚀 语音助手增强功能计划 (基于 SDK 最新分析)

以下功能将 Reachy Mini SDK 能力与语音助手体验深度整合，提升交互的自然性和表现力。

### Phase 13 - 情感动作反馈系统 (高优先级)

**目标**: 根据语音助手的响应内容，自动播放匹配的情感动作，让机器人更有"灵魂"。

**SDK 支持**:
- `RecordedMoves` - 从 HuggingFace 加载预录制情感动作库
- `pollen-robotics/reachy-mini-emotions-library` - 官方情感动作库
- `pollen-robotics/reachy-mini-dances-library` - 舞蹈动作库

**实现方案**:

| 语音助手事件 | 触发动作 | SDK API |
|-------------|---------|---------|
| 唤醒词检测 | 播放 "greeting" 动作 | `play_move(moves.get("greeting"))` |
| 收到肯定回复 | 播放 "happy" / "nod" 动作 | `play_move(moves.get("happy"))` |
| 收到否定回复 | 播放 "sad" / "shake" 动作 | `play_move(moves.get("sad"))` |
| 播放音乐/娱乐 | 播放 "dance" 动作 | `play_move(moves.get("dance"))` |
| 定时器完成 | 播放 "alert" 动作 | `play_move(moves.get("surprised"))` |
| 错误/无法理解 | 播放 "confused" 动作 | `play_move(moves.get("confused"))` |
| 天气查询-晴天 | 播放 "happy" 动作 | 根据天气类型选择 |
| 天气查询-雨天 | 播放 "sad" 动作 | 根据天气类型选择 |

**代码示例**:
```python
from reachy_mini.motion.recorded_move import RecordedMoves

class EmotionMotionController:
    def __init__(self, reachy_mini):
        self.reachy = reachy_mini
        # 预加载情感动作库
        self.emotions = RecordedMoves("pollen-robotics/reachy-mini-emotions-library")
        self.dances = RecordedMoves("pollen-robotics/reachy-mini-dances-library")

    def on_intent_response(self, intent: str, sentiment: str):
        """根据意图和情感选择动作"""
        if sentiment == "positive":
            self.reachy.play_move(self.emotions.get("happy"), sound=True)
        elif sentiment == "negative":
            self.reachy.play_move(self.emotions.get("sad"), sound=True)
        elif intent == "play_music":
            self.reachy.play_move(self.dances.get("dance_1"), sound=True)
```

### Phase 14 - 智能声源追踪增强 (高优先级)

**目标**: 利用 DOA (Direction of Arrival) 实现更自然的声源追踪和多人对话支持。

**当前实现**: 唤醒时转向声源
**增强方案**:

| 功能 | 说明 | SDK API |
|------|------|---------|
| 持续声源追踪 | 对话过程中持续跟踪说话人位置 | `media.get_DoA()` |
| 多人对话切换 | 检测到新说话人时平滑转向 | `goto_target(head=..., method=MIN_JERK)` |
| 声源可视化 | LED 指示当前声源方向 | `LED_DOA_COLOR` 参数 |
| 语音活动检测 | 只在检测到语音时追踪 | `DoAInfo.speech_detected` |

**代码示例**:
```python
async def continuous_doa_tracking(self):
    """持续追踪声源方向"""
    while self.is_listening:
        doa_result = self.reachy.media.get_DoA()
        if doa_result and doa_result[1]:  # speech_detected
            angle_rad, _ = doa_result
            # 平滑转向声源
            yaw_deg = math.degrees(angle_rad - math.pi/2)
            self.reachy.look_at_world(
                x=math.cos(angle_rad),
                y=math.sin(angle_rad),
                z=0.3,
                duration=0.3
            )
        await asyncio.sleep(0.1)
```

### Phase 15 - 卡通风格运动模式 (中优先级)

**目标**: 使用 SDK 的插值技术让机器人动作更有个性和表现力。

**SDK 支持**: `InterpolationTechnique` 枚举
- `LINEAR` - 线性，机械感
- `MIN_JERK` - 最小加加速度，自然平滑（默认）
- `EASE_IN_OUT` - 缓入缓出，优雅
- `CARTOON` - 卡通风格，带回弹效果，活泼可爱

**应用场景**:

| 场景 | 推荐插值 | 效果 |
|------|---------|------|
| 唤醒点头 | `CARTOON` | 活泼的回弹效果 |
| 思考抬头 | `EASE_IN_OUT` | 优雅的过渡 |
| 说话时微动 | `MIN_JERK` | 自然流畅 |
| 错误摇头 | `CARTOON` | 夸张的否定 |
| 返回中立 | `MIN_JERK` | 平滑归位 |

**代码示例**:
```python
from reachy_mini.utils.interpolation import InterpolationTechnique

def on_wakeup_cartoon(self):
    """卡通风格的唤醒动作"""
    # 使用卡通插值，带回弹效果
    self.reachy.goto_target(
        head=nod_pose,
        duration=0.4,
        method=InterpolationTechnique.CARTOON
    )
```

### Phase 16 - 说话时天线同步动画 (中优先级)

**目标**: TTS 播放时，天线随音频节奏摆动，模拟"说话"效果。

**实现方案**:
```python
async def speech_antenna_sync(self, audio_data: np.ndarray):
    """根据音频能量驱动天线摆动"""
    # 计算音频能量
    energy = np.abs(audio_data).mean()

    # 映射到天线角度 (±30度范围)
    amplitude = min(energy * 100, 30)

    # 左右天线交替摆动
    left_angle = math.radians(amplitude)
    right_angle = math.radians(-amplitude)

    self.reachy.set_target(antennas=[right_angle, left_angle])
```

### Phase 17 - 视觉注视交互 (中优先级)

**目标**: 利用摄像头检测人脸，实现眼神交流。

**SDK 支持**:
- `look_at_image(u, v)` - 注视图像中的点
- `look_at_world(x, y, z)` - 注视世界坐标点
- `media.get_frame()` - 获取摄像头画面

**实现方案**:

| 功能 | 说明 |
|------|------|
| 人脸检测 | 使用 OpenCV/MediaPipe 检测人脸 |
| 眼神追踪 | 对话时注视说话人的脸 |
| 多人切换 | 检测到多人时，注视当前说话人 |
| 空闲扫视 | 空闲时随机环顾四周 |

**代码示例**:
```python
import cv2

async def face_tracking_loop(self):
    """人脸追踪循环"""
    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    )

    while self.is_active:
        frame = self.reachy.media.get_frame()
        if frame is None:
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)

        if len(faces) > 0:
            x, y, w, h = faces[0]
            # 注视人脸中心
            self.reachy.look_at_image(x + w//2, y + h//2, duration=0.3)

        await asyncio.sleep(0.1)
```

### Phase 18 - 重力补偿互动模式 (低优先级)

**目标**: 允许用户物理触摸和引导机器人头部，实现"教学"式交互。

**SDK 支持**: `enable_gravity_compensation()` - 电机进入重力补偿模式，可手动移动

**应用场景**:
- 用户说 "让我教你一个动作" → 进入重力补偿模式
- 用户手动移动头部 → 录制动作轨迹
- 用户说 "记住这个" → 保存动作
- 用户说 "做刚才的动作" → 播放录制的动作

**代码示例**:
```python
async def teaching_mode(self):
    """教学模式 - 用户可手动引导机器人"""
    self.reachy.enable_gravity_compensation()
    self.reachy.start_recording()

    # 等待用户完成教学
    await self.wait_for_command("记住这个")

    recorded_data = self.reachy.stop_recording()
    self.reachy.enable_motors()

    # 保存为自定义动作
    self.save_custom_move(recorded_data)
```

### Phase 19 - 环境感知响应 (低优先级，仅无线版本)

**目标**: 利用 IMU 传感器感知环境变化并做出响应。

**SDK 支持**:
- `mini.imu["accelerometer"]` - 加速度计
- `mini.imu["gyroscope"]` - 陀螺仪

**应用场景**:

| 检测事件 | 响应动作 |
|---------|---------|
| 被拍打/敲击 | 播放惊讶动作 + 语音 "哎呀!" |
| 被摇晃 | 播放晕眩动作 + 语音 "别晃我~" |
| 倾斜/倒下 | 播放求助动作 + 语音 "我倒了，帮帮我" |
| 长时间静止 | 进入休眠动画 |

### Phase 20 - Home Assistant 场景联动 (低优先级)

**目标**: 根据 Home Assistant 的场景/自动化触发机器人动作。

**实现方案**: 通过 ESPHome 服务调用

| HA 场景 | 机器人响应 |
|--------|-----------|
| 早安场景 | 播放唤醒动作 + "早上好!" |
| 晚安场景 | 播放睡眠动作 + "晚安~" |
| 有人回家 | 转向门口 + 挥手 + "欢迎回家!" |
| 门铃响起 | 转向门口 + 警觉动作 |
| 播放音乐 | 随音乐节奏摆动 |

---

## 功能优先级总结

### 高优先级 (已完成)
- ✅ Phase 1-12: 基础 ESPHome 实体 (45+ 个)

### 高优先级 (近期实现)
- ⏳ **Phase 13**: 情感动作反馈系统 - 让机器人有"灵魂"
- ⏳ **Phase 14**: 智能声源追踪增强 - 更自然的对话体验

### 中优先级 (计划中)
- ⏳ **Phase 15**: 卡通风格运动模式 - 更有个性的动作
- ⏳ **Phase 16**: 说话时天线同步 - 模拟说话效果
- ⏳ **Phase 17**: 视觉注视交互 - 眼神交流

### 低优先级 (未来考虑)
- ⏳ **Phase 18**: 重力补偿互动模式 - 教学式交互
- ⏳ **Phase 19**: 环境感知响应 - IMU 触发动作
- ⏳ **Phase 20**: Home Assistant 场景联动 - 智能家居整合

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
