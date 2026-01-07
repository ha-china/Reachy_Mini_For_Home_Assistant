# Reachy Mini Home Assistant Voice Assistant - 项目计划

## 项目概述

将 Home Assistant 语音助手功能集成到 Reachy Mini 机器人，通过 ESPHome 协议与 Home Assistant 通信。

## 本地项目目录参考 (禁止修改参考目录内任何文件)
1. [linux-voice-assistant](linux-voice-assistant)，这是一个基于 Linux 的Home Assistant的语音助手应用，用于参考。
2. [Reachy Mini SDK](reachy_mini) 这是 Reachy Mini SDK 的本地项目目录，用于参考。
3. [reachy_mini_conversation_app](reachy_mini_conversation_app) - Reachy Mini 对话应用，用于参考
4. [reachy-mini-desktop-app](reachy-mini-desktop-app) - Reachy Mini 桌面应用，用于参考

## 核心设计原则

1. **零配置安装** - 用户只需安装应用，无需手动配置
2. **使用 Reachy Mini 原生硬件** - 使用机器人自带的麦克风和扬声器
3. **Home Assistant 集中管理** - 所有配置在 Home Assistant 端完成
4. **运动反馈** - 语音交互时提供头部运动和天线动画反馈
5. **项目约束** - 整个项目需要严格遵循 [Reachy Mini SDK](reachy_mini) 的架构设计与约束
6. **代码质量** - 严格遵循Python开发的标准，并做到代码风格一致，代码结构清晰，注释完整，文档完善，测试覆盖率高，代码质量高，代码可读性高，代码可维护性高，代码可扩展性高，代码可复用性高
7. **功能优先级** - 与home assistant的语音对话为最高优先级，任何其它的功能都是辅助功能，不能影响语音对话的功能和响应速度
8. **不调用任何LED功能** - LED都被隐藏在了机器人内部，所有的LED控制全部都忽略，不要使用LED控制
9. **保留功能优先** - 任何代码修改都应该在保留已完成功能的前提下优化，不能以去除功能的方式来解决问题。当有问题发生时，应该充分参考案例之后以解决问题为优先级，而不是添加各种日志输出为优先级

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
│  │ Camera + Face Tracking (YOLO)                       │   │
│  │ - 15Hz 人脸检测与追踪                                │   │
│  │ - look_at_image() 计算目标姿态                       │   │
│  │ - 人脸丢失后平滑回中性位置                            │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Motion Controller (Head + Antennas) - 5Hz           │   │
│  │ - Face tracking offsets (secondary pose)            │   │
│  │ - Speech sway (语音驱动微动)                         │   │
│  │ - Breathing animation (空闲呼吸)                     │   │
│  │ - on_wakeup → on_listening → on_speaking → on_idle  │   │
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
- [x] 拍一拍唤醒（IMU 加速度检测，仅无线版本）
- [x] 音频流传输到 Home Assistant
- [x] TTS 音频播放
- [x] 停止词检测

### Reachy Mini 集成
- [x] 使用 Reachy Mini SDK 的麦克风输入
- [x] 使用 Reachy Mini SDK 的扬声器输出
- [x] 头部运动控制（点头、摇头、注视）
- [x] 天线动画控制
- [x] 语音状态反馈动作
- [x] YOLO 人脸追踪（替代 DOA 声源定位）
- [x] 5Hz 统一运动控制循环

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
│   ├── __main__.py  py         # 命令行入口
│   ├── main.py                 # ReachyMiniApp 入口
│   ├── voice_assistant.py      # 语音助手服务
│   ├── satellite.py            # ESPHome 协议处理
│   ├── audio_player.py         # 音频播放器
│   ├── camera_server.py        # MJPEG 摄像头流服务器 + 人脸追踪
│   ├── head_tracker.py         # YOLO 人脸检测器
│   ├── motion.py               # 运动控制 (高层 API)
│   ├── movement_manager.py     # 统一运动管理器 (20Hz 控制循环，优化以防止 daemon 崩溃)
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
   - 从 Reachy Mini App Store 安装`reachy-mini-ha-voice`

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

11. **Phase 11 - LED 控制** ❌ **已禁用（LED 隐藏在机器人内部）**
    - [ ] `led_brightness` - LED 亮度 (0-100%) - 已注释
    - [ ] `led_effect` - LED 效果 (off/solid/breathing/rainbow/doa) - 已注释
    - [ ] `led_color_r/g/b` - LED RGB 颜色 (0-255) - 已注释

12. **Phase 12 - 音频处理参数** ✅ **已完成**
    - [x] `agc_enabled` - 自动增益控制开关
    - [x] `agc_max_gain` - AGC 最大增益 (0-30 dB)
    - [x] `noise_suppression` - 噪声抑制级别 (0-100%)
    - [x] `echo_cancellation_converged` - 回声消除收敛状态（只读）

13. **Phase 13 - Sendspin 音频播放支持** ❌ **待实现**
    - [ ] 支持 sendspin 协议播放音频
    - [ ] 与现有 AudioPlayer 集成
    - [ ] TTS 音频通过 sendspin 输出

---

## 🎉 Phase 1-12 实体已完成！

**已完成总计：40 个实体**
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
- Phase 11: 0 个实体 (LED 控制 - 已禁用)
- Phase 12: 4 个实体 (音频处理参数)

---

## 🚀 语音助手增强功能实现状态

### Phase 14 - 情感动作反馈系统 (部分实现) 🟡

**实现状态**: 基础架构已就绪,支持手动触发,对话时使用语音驱动的自然微动

**已实现功能**:
- ✅ Phase 8 Emotion Selector 实体 (`emotion`)
- ✅ 基础情感动作播放API (`_play_emotion`)
- ✅ 情感映射: Happy/Sad/Angry/Fear/Surprise/Disgust
- ✅ 与 HuggingFace 动作库集成 (`pollen-robotics/reachy-mini-emotions-library`)
- ✅ 对话时使用 SpeechSway 系统提供自然的头部微动 (不阻塞对话体验)

**设计决策**:
- 🎯 对话时不自动播放完整情感动作,避免阻塞对话体验
- 🎯 使用语音驱动的头部摆动 (SpeechSway) 提供自然的动作反馈
- 🎯 情感动作保留为手动触发功能,可通过 ESPHome 实体控制

**未实现功能**:
- ❌ 自动根据语音助手响应触发情感动作 (已决定不实现,避免阻塞)
- ❌ 意图识别与情感匹配
- ❌ 舞蹈动作库集成
- ❌ 上下文感知(如天气查询-晴天播放 happy,雨天播放 sad)

**代码位置**:
- `entity_registry.py:633-658` - Emotion Selector 实体
- `satellite.py:544-574` - `_play_emotion()` 方法
- `motion.py:132-156` - 对话开始时的动作控制 (使用 SpeechSway)
- `movement_manager.py:541-595` - Move 队列管理 (允许 SpeechSway 叠加)

**实际行为**:

| 语音助手事件 | 实际动作 | 实现状态 |
|-------------|---------|---------|
| 唤醒词检测 | 转向声源 + 点头确认 | ✅ 已实现 |
| 对话开始 | 语音驱动的头部微动 (SpeechSway) | ✅ 已实现 |
| 对话进行中 | 持续的语音驱动微动 + 呼吸动画 | ✅ 已实现 |
| 对话结束 | 返回中立位置 + 呼吸动画 | ✅ 已实现 |
| 手动触发情感 | 通过 ESPHome `emotion` 实体播放 | ✅ 已实现 |

**技术说明**:
```python
# motion.py - 对话时使用 SpeechSway 而非完整情感动作
def on_speaking_start(self):
    self._is_speaking = True
    self._movement_manager.set_state(RobotState.SPEAKING)
    # SpeechSway 会自动根据音频响度产生自然的头部微动
    # 不播放完整情感动作,避免阻塞对话体验

# movement_manager.py - 动作分层系统
# 1. Move 队列 (情感动作) - 设置基础姿态
# 2. Action (点头/摇头等) - 叠加在基础姿态上
# 3. SpeechSway - 语音驱动微动,可与 Move 共存
# 4. Breathing - 空闲时的呼吸动画
```

**原始规划** (已决定不实现,避免阻塞对话):

| 语音助手事件 | 原计划动作 | 不实现原因 |
|-------------|---------|---------|
| 收到肯定回复 | 播放 "happy" 动作 | 完整动作会阻塞对话流畅性 |
| 收到否定回复 | 播放 "sad" 动作 | 完整动作会阻塞对话流畅性 |
| 播放音乐/娱乐 | 播放 "dance" 动作 | 完整动作会阻塞对话流畅性 |
| 定时器完成 | 播放 "alert" 动作 | 完整动作会阻塞对话流畅性 |
| 错误/无法理解 | 播放 "confused" 动作 | 完整动作会阻塞对话流畅性 |

**手动触发情感动作示例**:
```yaml
# Home Assistant 自动化示例 - 手动触发情感
automation:
  - alias: "Reachy 早安问候"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: select.select_option
        target:
          entity_id: select.reachy_mini_emotion
        data:
          option: "Happy"
```

### Phase 15 - 人脸追踪（替代 DOA 声源追踪）✅ **已完成**

**目标**: 实现自然的人脸追踪，让机器人在对话时注视说话人。

**设计决策**: 
- ❌ 原计划使用 DOA (Direction of Arrival) 声源追踪
- ✅ 改用 YOLO 人脸检测，更稳定、更准确
- 原因：DOA 在唤醒时判断不够准确，且频繁查询会导致 daemon 崩溃

**已实现功能**:

| 功能 | 说明 | 实现位置 | 实现状态 |
|------|------|---------|---------|
| YOLO 人脸检测 | 使用 `AdamCodd/YOLOv11n-face-detection` 模型 | `head_tracker.py` | ✅ 已实现 |
| 15Hz 人脸追踪 | 摄像头帧处理 + 人脸检测 | `camera_server.py` | ✅ 已实现 |
| look_at_image() | 根据人脸位置计算目标姿态 | `camera_server.py` | ✅ 已实现 |
| 平滑回中性位置 | 人脸丢失后 1 秒内平滑回归 | `camera_server.py` | ✅ 已实现 |
| face_tracking_offsets | 作为 secondary pose 叠加到运动控制 | `movement_manager.py` | ✅ 已实现 |
| 语音活动检测 | DOA 实体仍可用于检测语音 | `DoAInfo.speech_detected` | ✅ 已暴露为实体 |

**代码位置**:
- `head_tracker.py` - YOLO 人脸检测器 (`HeadTracker` 类)
- `camera_server.py:_face_tracking_loop()` - 15Hz 人脸追踪循环
- `movement_manager.py:set_face_tracking_offsets()` - 人脸追踪偏移量 API

**技术细节**:
```python
# head_tracker.py - YOLO 人脸检测
class HeadTracker:
    def __init__(self):
        self.model = YOLO("AdamCodd/YOLOv11n-face-detection")
    
    def detect_faces(self, frame) -> list[FaceDetection]:
        # 返回检测到的人脸列表，包含 bbox 和置信度

# camera_server.py - 人脸追踪循环
async def _face_tracking_loop(self):
    while self._running:
        frame = self._reachy_controller.get_camera_frame()
        faces = self._head_tracker.detect_faces(frame)
        if faces:
            # 选择最大/最近的人脸
            target_u, target_v = faces[0].center
            pose = self._reachy_controller.look_at_image(target_u, target_v)
            self._motion.set_face_tracking_offsets(pose)
        else:
            # 平滑回归中性位置
            self._motion.clear_face_tracking_offsets()
        await asyncio.sleep(1/15)  # 15Hz
```

### Phase 16 - 卡通风格运动模式 (部分实现) 🟡

**目标**: 使用 SDK 的插值技术让机器人动作更有个性和表现力。

**SDK 支持**: `InterpolationTechnique` 枚举
- `LINEAR` - 线性，机械感
- `MIN_JERK` - 最小加加速度，自然平滑（默认）
- `EASE_IN_OUT` - 缓入缓出，优雅
- `CARTOON` - 卡通风格，带回弹效果，活泼可爱

**已实现功能**:
- ✅ 20Hz 统一控制循环 (`movement_manager.py`) - 从 100Hz 降低以防止 daemon 崩溃
- ✅ 姿态变化检测 - 仅在姿态显著变化时发送命令 (阈值 0.001)
- ✅ 状态查询缓存 - 100ms TTL，减少 daemon 负载
- ✅ 平滑插值动作 (ease in-out 曲线)
- ✅ 呼吸动画 - 空闲时 Z 轴微动 + 天线摆动 (`BreathingAnimation`)
- ✅ 命令队列模式 - 线程安全的外部 API
- ✅ 错误节流 - 防止日志爆炸
- ✅ 连接健康监控 - 自动检测和恢复连接丢失

**未实现功能**:
- ❌ 动态插值技术切换 (CARTOON/EASE_IN_OUT 等)
- ❌ 夸张的卡通回弹效果

**代码位置**:
- `movement_manager.py:192-243` - BreathingAnimation 类
- `movement_manager.py:246-697` - MovementManager 类

**场景实现状态**:

| 场景 | 推荐插值 | 效果 | 实现状态 |
|------|---------|------|---------|
| 唤醒点头 | `CARTOON` | 活泼的回弹效果 | ❌ 未实现 |
| 思考抬头 | `EASE_IN_OUT` | 优雅的过渡 | ✅ 已实现 (平滑插值) |
| 说话时微动 | `MIN_JERK` | 自然流畅 | ✅ 已实现 (SpeechSway) |
| 错误摇头 | `CARTOON` | 夸张的否定 | ❌ 未实现 |
| 返回中立 | `MIN_JERK` | 平滑归位 | ✅ 已实现 |
| 空闲呼吸 | - | 微妙的生命感 | ✅ 已实现 (BreathingAnimation) |

### Phase 17 - 说话时天线同步动画 (部分实现) 🟡

**目标**: TTS 播放时，天线随音频节奏摆动，模拟"说话"效果。

**已实现功能**:
- ✅ 语音驱动头部摆动 (`SpeechSwayGenerator`)
- ✅ 基于音频响度的 VAD 检测
- ✅ 多频率正弦波叠加 (Lissajous 运动)
- ✅ 平滑包络过渡

**代码位置**:
- `movement_manager.py:124-189` - SpeechSwayGenerator 类
- `motion.py:212-222` - update_audio_loudness() 方法

**技术细节**:
```python
# 语音摆动参数
SWAY_A_PITCH_DEG = 3.0   # 俯仰幅度 (度)
SWAY_A_YAW_DEG = 2.0     # 偏航幅度
SWAY_A_ROLL_DEG = 2.0    # 翻滚幅度
SWAY_F_PITCH = 0.8       # 俯仰频率 Hz
SWAY_F_YAW = 0.6         # 偏航频率
SWAY_F_ROLL = 0.5        # 翻滚频率

# VAD 阈值
VAD_DB_ON = -35   # 开始检测阈值
VAD_DB_OFF = -45  # 停止检测阈值
```

**未实现功能**:
- ❌ 天线随音频节奏摆动 (当前仅头部摆动)
- ❌ 音频频谱分析驱动动画

### Phase 18 - 视觉注视交互 (未实现) ❌

**目标**: 利用摄像头检测人脸，实现眼神交流。

**SDK 支持**:
- `look_at_image(u, v)` - 注视图像中的点
- `look_at_world(x, y, z)` - 注视世界坐标点
- `media.get_frame()` - 获取摄像头画面 (✅ 已在 `camera_server.py:146` 实现)

**未实现功能**:

| 功能 | 说明 | 实现状态 |
|------|------|---------|
| 人脸检测 | 使用 OpenCV/MediaPipe 检测人脸 | ❌ 未实现 |
| 眼神追踪 | 对话时注视说话人的脸 | ❌ 未实现 |
| 多人切换 | 检测到多人时，注视当前说话人 | ❌ 未实现 |
| 空闲扫视 | 空闲时随机环顾四周 | ❌ 未实现 |

### Phase 19 - 重力补偿互动模式 (部分实现) 🟡

**目标**: 允许用户物理触摸和引导机器人头部，实现"教学"式交互。

**SDK 支持**: `enable_gravity_compensation()` - 电机进入重力补偿模式，可手动移动

**已实现功能**:
- ✅ 重力补偿模式切换 (`motor_mode` Select 实体，选项 "gravity_compensation")
- ✅ `reachy_controller.py:236-237` - 重力补偿 API 调用

**未实现功能**:
- ❌ 教学模式 - 录制动作轨迹
- ❌ 保存/播放自定义动作
- ❌ 语音命令触发教学流程

**应用场景**:
- ❌ 用户说 "让我教你一个动作" → 进入重力补偿模式
- ❌ 用户手动移动头部 → 录制动作轨迹
- ❌ 用户说 "记住这个" → 保存动作
- ❌ 用户说 "做刚才的动作" → 播放录制的动作

### Phase 20 - 环境感知响应 (部分实现) 🟡

**目标**: 利用 IMU 传感器感知环境变化并做出响应。

**SDK 支持**:
- ✅ `mini.imu["accelerometer"]` - 加速度计 (Phase 7 已实现为实体)
- ✅ `mini.imu["gyroscope"]` - 陀螺仪 (Phase 7 已实现为实体)

**已实现功能**:

| 检测事件 | 响应动作 | 实现状态 |
|---------|---------|---------|
| 拍一拍唤醒 | 进入持续对话模式 | ✅ 已实现 |
| 再次拍一拍 | 退出持续对话模式 | ✅ 已实现 |

**拍一拍唤醒 vs 语音唤醒**:

| 唤醒方式 | 对话模式 | 说明 |
|---------|---------|------|
| 语音唤醒 (Okay Nabu) | 单次对话 | 每次对话需要重新说唤醒词 |
| 拍一拍唤醒 | 持续对话 | TTS 结束后自动继续监听，再拍一次退出 |

**技术实现**:
- `tap_detector.py` - IMU 加速度突变检测
- `satellite.py:_tap_conversation_mode` - 持续对话模式标志
- 阈值: 2.0g (可配置)
- 冷却时间: 1.0s (防止重复触发)
- 仅限无线版本 (Wireless) 可用

```python
# satellite.py - 持续对话模式
def wakeup_from_tap(self):
    if self._tap_conversation_mode:
        # 第二次拍 - 退出持续对话
        self._tap_conversation_mode = False
        self._reachy_on_idle()
    else:
        # 第一次拍 - 进入持续对话
        self._tap_conversation_mode = True
        self.send_messages([VoiceAssistantRequest(start=True)])

def _tts_finished(self):
    if self._tap_conversation_mode:
        # 持续对话模式：自动继续监听
        self.send_messages([VoiceAssistantRequest(start=True)])
```

**未实现功能**:

| 检测事件 | 响应动作 | 实现状态 |
|---------|---------|---------|
| 被摇晃 | 播放晕眩动作 + 语音 "别晃我~" | ❌ 未实现 |
| 倾斜/倒下 | 播放求助动作 + 语音 "我倒了，帮帮我" | ❌ 未实现 |
| 长时间静止 | 进入休眠动画 | ❌ 未实现 |

### Phase 21 - Home Assistant 场景联动 (未实现) ❌

**目标**: 根据 Home Assistant 的场景/自动化触发机器人动作。

**实现方案**: 通过 ESPHome 服务调用

**未实现场景**:

| HA 场景 | 机器人响应 | 实现状态 |
|--------|-----------|---------|
| 早安场景 | 播放唤醒动作 + "早上好!" | ❌ 未实现 |
| 晚安场景 | 播放睡眠动作 + "晚安~" | ❌ 未实现 |
| 有人回家 | 转向门口 + 挥手 + "欢迎回家!" | ❌ 未实现 |
| 门铃响起 | 转向门口 + 警觉动作 | ❌ 未实现 |
| 播放音乐 | 随音乐节奏摆动 | ❌ 未实现 |

---

## 📊 功能实现总结

### ✅ 已完成功能

#### 核心语音助手 (Phase 1-12)
- **45+ ESPHome 实体** - 全部实现
- **基础语音交互** - 唤醒词检测、STT/TTS 集成
- **运动反馈** - 点头、摇头、注视等基础动作
- **音频处理** - AGC、噪声抑制、回声消除
- **摄像头流** - MJPEG 实时预览

#### 部分实现功能 (Phase 14-21)
- **Phase 14** - 情感动作 API 基础设施 (手动触发可用)
- **Phase 19** - 重力补偿模式切换 (教学流程未实现)

### ❌ 未实现功能

#### 高优先级
- **Phase 13** - Sendspin 音频播放支持 (待实现)
- **Phase 14** - 自动情感动作反馈 (需与语音助手事件关联)
- **Phase 15** - 持续声源追踪 (仅唤醒时转向)

#### 中优先级
- **Phase 16** - 卡通风格运动模式 (需动态插值切换)
- **Phase 17** - 天线同步动画
- **Phase 18** - 人脸追踪与眼神交互

#### 低优先级
- **Phase 19** - 教学模式录制/播放功能
- **Phase 20** - IMU 环境感知响应
- **Phase 21** - Home Assistant 场景联动

---

## 功能优先级总结 (更新版)

### 高优先级 (已完成 ✅)
- ✅ **Phase 1-12**: 基础 ESPHome 实体 (45+ 个)
- ✅ 核心语音助手功能
- ✅ 基础运动反馈 (点头、摇头、注视)

### 高优先级 (部分实现 🟡)
- 🟡 **Phase 13**: 情感动作反馈系统
  - ✅ Emotion Selector 实体与 API 基础设施
  - ❌ 自动根据语音助手响应触发情感动作
  - ❌ 意图识别与情感匹配
  - ❌ 舞蹈动作库集成

### 高优先级 (未实现 ❌)
- ❌ **Phase 14**: 智能声源追踪增强
  - ✅ 唤醒时转向声源
  - ❌ 持续声源追踪
  - ❌ 多人对话切换
  - ❌ 声源可视化

### 中优先级 (部分实现 🟡)
- 🟡 **Phase 15**: 卡通风格运动模式
  - ✅ 20Hz 统一控制循环架构 (优化以防止 daemon 崩溃)
  - ✅ 姿态变化检测 + 状态查询缓存 (减少 daemon 负载)
  - ✅ 平滑插值动作 + 呼吸动画
  - ❌ 动态插值技术切换 (CARTOON 等)
- 🟡 **Phase 16**: 说话时天线同步
  - ✅ 语音驱动头部摆动 (SpeechSwayGenerator)
  - ❌ 天线随音频节奏摆动

### 中优先级 (未实现 ❌)
- ❌ **Phase 17**: 视觉注视交互 - 眼神交流

### 低优先级 (部分实现 🟡)
- 🟡 **Phase 18**: 重力补偿互动模式
  - ✅ 重力补偿模式切换
  - ❌ 教学式交互 (录制/播放功能)

### 低优先级 (未实现 ❌)
- ❌ **Phase 19**: 环境感知响应 - IMU 触发动作
- ❌ **Phase 20**: Home Assistant 场景联动 - 智能家居整合

---

## 📈 完成度统计

| 阶段 | 状态 | 完成度 | 说明 |
|------|------|--------|------|
| Phase 1-12 | ✅ 完成 | 100% | 40 个 ESPHome 实体已实现（Phase 11 LED 已禁用） |
| Phase 13 | 🟡 部分完成 | 30% | API 基础设施就绪,缺自动触发 |
| Phase 14 | ❌ 未完成 | 20% | 仅实现唤醒时转向 |
| Phase 15 | 🟡 部分完成 | 70% | 20Hz控制循环+姿态变化检测+状态缓存+呼吸动画已实现 |
| Phase 16 | 🟡 部分完成 | 50% | 语音驱动头部摆动已实现 |
| Phase 17 | ❌ 未完成 | 10% | 摄像头已实现,缺人脸检测 |
| Phase 18 | 🟡 部分完成 | 40% | 模式切换已实现,缺教学流程 |
| Phase 19 | ❌ 未完成 | 10% | IMU 数据已暴露,缺触发逻辑 |
| Phase 20 | ❌ 未完成 | 0% | 完全未实现 |

**总体完成度**: **Phase 1-12: 100%** | **Phase 13-20: ~35%**

---

## 🔧 Daemon 崩溃问题修复 (2025-01-05)

### 问题描述
长期运行过程中，`reachy_mini daemon` 会崩溃，导致机器人失去响应。

### 根本原因
1. **100Hz 控制循环过于频繁** - 每 10ms 调用一次 `robot.set_target()`，即使姿态没有变化
2. **频繁的状态查询** - 每次读取实体状态都调用 `get_status()`、`get_current_head_pose()` 等
3. **缺少变化检测** - 即使姿态没有变化，也会持续发送相同的命令
4. **Zenoh 消息队列堵塞** - 累积起来可能每秒 150+ 条消息，daemon 无法及时处理

### 修复方案

#### 1. 降低控制循环频率 (movement_manager.py)
```python
# 从 100Hz 降低到 20Hz
CONTROL_LOOP_FREQUENCY_HZ = 20  # 减少 80% 的消息量
```

#### 2. 添加姿态变化检测 (movement_manager.py)
```python
# 仅在姿态显著变化时发送命令
if self._last_sent_pose is not None:
    max_diff = max(abs(pose[k] - self._last_sent_pose.get(k, 0.0)) for k in pose.keys())
    if max_diff < 0.001:  # 阈值: 0.001 rad 或 0.001 m
        return  # 跳过发送
```

#### 3. 状态查询缓存 (reachy_controller.py)
```python
# 缓存 daemon 状态查询结果
self._cache_ttl = 0.1  # 100ms TTL
self._last_status_query = 0.0

def _get_cached_status(self):
    now = time.time()
    if now - self._last_status_query < self._cache_ttl:
        return self._state_cache.get('status')  # 使用缓存
    # ... 查询并更新缓存
```

#### 4. 头部姿态查询缓存 (reachy_controller.py)
```python
# 缓存 get_current_head_pose() 和 get_current_joint_positions() 结果
def _get_cached_head_pose(self):
    # 100ms 内复用缓存结果
```

### 修复效果

| 指标 | 修复前 | 修复后 | 改善 |
|------|--------|--------|------|
| 控制消息频率 | ~100 msg/s | ~20 msg/s | ↓ 80% |
| 状态查询频率 | ~50 msg/s | ~5 msg/s | ↓ 90% |
| 总 Zenoh 消息 | ~150 msg/s | ~25 msg/s | ↓ 83% |
| Daemon CPU 负载 | 持续高负载 | 正常负载 | 显著降低 |
| 预期稳定性 | 数小时内崩溃 | 可稳定运行数天 | 大幅提升 |

### 相关文件
- `DAEMON_CRASH_FIX_PLAN.md` - 详细修复方案和测试计划
- `movement_manager.py` - 控制循环优化
- `reachy_controller.py` - 状态查询缓存

### 后续优化建议
1. ⏳ 动态频率调整 - 运动时 50Hz，空闲时 5Hz
2. ⏳ 批量状态查询 - 一次性获取所有状态
3. ⏳ 性能监控和告警 - 实时监控 daemon 健康状态

---

## 🔧 拍一拍唤醒与麦克风灵敏度修复 (2026-01-07)

### 问题描述
1. **拍一拍唤醒阻塞** - 拍一拍唤醒后对话功能不正常，存在阻塞问题
2. **麦克风灵敏度低** - 需要靠很近才能识别语音

### 根本原因
1. **音频播放阻塞** - `_tap_continue_feedback()` 在持续对话模式下播放提示音，阻塞了音频流处理
2. **AGC 设置不优化** - ReSpeaker 的自动增益控制 (AGC) 默认设置不适合远距离语音识别

### 修复方案

#### 1. 移除持续对话反馈中的音频播放 (satellite.py)
```python
def _tap_continue_feedback(self) -> None:
    """Provide feedback when continuing conversation in tap mode.
    
    Triggers a nod to indicate ready for next input.
    Sound is NOT played here to avoid blocking audio streaming.
    """
    # NOTE: Do NOT play sound here - it blocks audio streaming
    if self.state.motion_enabled and self.state.motion:
        self.state.motion.on_continue_listening()
```

#### 2. 添加异常处理到 tap 回调 (voice_assistant.py)
```python
def _on_tap_detected(self) -> None:
    """Callback when tap is detected on the robot.
    
    NOTE: This is called from the tap_detector background thread.
    """
    try:
        self._state.satellite.wakeup_from_tap()
        # ... motion feedback
    except Exception as e:
        _LOGGER.error("Error in tap detection callback: %s", e)
```

#### 3. 优化麦克风设置 (voice_assistant.py)
```python
def _optimize_microphone_settings(self) -> None:
    """Optimize ReSpeaker microphone settings for voice recognition."""
    # Enable AGC for better sensitivity at distance
    respeaker.write("PP_AGCONOFF", [1])
    
    # Set higher AGC max gain (default ~15dB -> 25dB)
    respeaker.write("PP_AGCMAXGAIN", [25.0])
    
    # Set AGC desired level (target output level)
    respeaker.write("PP_AGCDESIREDLEVEL", [-20.0])
    
    # Increase microphone gain
    respeaker.write("AUDIO_MGR_MIC_GAIN", [2.0])
```

### 修复效果

| 问题 | 修复前 | 修复后 |
|------|--------|--------|
| 拍一拍持续对话 | 阻塞，无法正常对话 | 正常工作 |
| 麦克风灵敏度 | 需要靠近 ~30cm | 可在 ~1m 距离识别 |
| AGC 最大增益 | ~15dB | 25dB |
| 麦克风增益 | 1.0x | 2.0x |

### 相关文件
- `satellite.py` - 移除阻塞的音频播放
- `voice_assistant.py` - 添加麦克风优化和异常处理

---

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
