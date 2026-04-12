# Reachy Mini 语音助手 - 用户手册

## 系统要求

### 硬件
- Reachy Mini 机器人（带 ReSpeaker XVF3800 麦克风）
- WiFi 网络连接

### 软件
- Home Assistant（2024.1 或更高版本）
- Home Assistant 中已启用 ESPHome 集成

---

## 安装步骤

### 第一步：安装应用
从 Reachy Mini 应用商店安装 `reachy_mini_home_assistant`。

### 第二步：启动应用
应用将自动：
- 在端口 6053 启动 ESPHome 服务器
- 加载预打包的唤醒词模型
- 通过 mDNS 注册以便自动发现
- 如果网络上有 Sendspin 服务器则自动连接

### 第三步：连接 Home Assistant
**自动连接（推荐）：**
Home Assistant 会通过 mDNS 自动发现 Reachy Mini。

**手动连接：**
1. 进入 设置 → 设备与服务
2. 点击"添加集成"
3. 选择"ESPHome"
4. 输入机器人的 IP 地址和端口 6053

---

## 功能介绍

### 语音助手
- **唤醒词检测**：说 "Okay Nabu" 激活（本地处理）
- **停止词**：说 "Stop" 结束对话
- **连续对话模式**：无需重复唤醒词即可持续对话
- **语音识别/合成**：使用 Home Assistant 配置的语音引擎

**支持的唤醒词：**
- Okay Nabu（默认）
- Hey Jarvis
- Alexa
- Hey Luna

### 人脸追踪
- 基于 YOLO 的人脸检测
- 头部跟随检测到的人脸
- 头部转动时身体随之旋转
- 自适应帧率：活跃时 15fps，空闲时 2fps
- 可在 Home Assistant 中运行时开关

### 手势检测
检测到的手势会作为实体状态同步到 Home Assistant。
当前默认运行时不会直接用手势触发机器人动作。

| 输出 | 说明 |
|------|------|
| `gesture_detected` | 当前识别到的手势标签 |
| `gesture_confidence` | 手势识别置信度 |

### 情绪响应
机器人可播放 35 种不同情绪：
- 基础：开心、难过、愤怒、恐惧、惊讶、厌恶
- 扩展：大笑、爱慕、骄傲、感激、热情、好奇、惊叹、害羞、困惑、沉思、焦虑、害怕、沮丧、烦躁、狂怒、轻蔑、无聊、疲倦、精疲力竭、孤独、沮丧、顺从、不确定、不舒服

### 音频功能
- 扬声器音量控制（0-100%）
- 静音开关，可暂停/恢复语音链路
- 支持唤醒提示音与计时器完成提示音
- STT/TTS 由 Home Assistant 负责

### Sendspin 多房间音频
- 通过 mDNS 自动发现 Sendspin 服务器
- 同步多房间音频播放
- Reachy Mini 作为 PLAYER 接收音频流
- 语音对话时自动暂停
- 无需用户配置

### DOA 声源追踪
- 声源方向检测
- 唤醒时机器人转向声源
- 可通过开关启用/禁用

---

## Home Assistant 实体

### 阶段 1：基础状态
| 实体 | 类型 | 说明 |
|------|------|------|
| Daemon State | 文本传感器 | 机器人守护进程状态 |
| Backend Ready | 二进制传感器 | 后端连接状态 |
| Mute | 开关 | 暂停/恢复语音链路 |
| Speaker Volume | 数值 (0-100%) | 扬声器音量控制 |
| Disable Camera | 开关 | 暂停/恢复摄像头服务 |
| Idle Behavior | 开关 | 统一空闲行为：头部、天线、微动作 |
| Sendspin | 开关 | 启用/禁用 Sendspin 发现与播放 |
| Face Tracking | 开关 | 启用/禁用人脸跟踪 |
| Gesture Detection | 开关 | 启用/禁用手势检测 |
| Face Confidence | 数值 (0-1) | 人脸跟踪置信度阈值 |

### 阶段 2：睡眠与运行状态
| 实体 | 类型 | 说明 |
|------|------|------|
| Sleep Control | 开关 | 打开表示进入睡眠，关闭表示唤醒 |
| Sleep Mode | 二进制传感器 | 运行中表示唤醒，非运行表示睡眠 |
| Services Suspended | 二进制传感器 | 运行中表示服务活跃 |

### 阶段 3：姿态控制
| 实体 | 类型 | 范围 |
|------|------|------|
| Head X/Y/Z | 数值 | ±50mm |
| Head Roll/Pitch/Yaw | 数值 | ±40° |
| Body Yaw | 数值 | ±160° |
| Antenna Left/Right | 数值 | ±90° |

### 阶段 4：注视控制
| 实体 | 类型 | 说明 |
|------|------|------|
| Look At X/Y/Z | 数值 | 注视目标的世界坐标 |

### 阶段 5：DOA（声源定位）
| 实体 | 类型 | 说明 |
|------|------|------|
| DOA Angle | 传感器 (°) | 声源方向 |
| Speech Detected | 二进制传感器 | 语音活动检测 |
| DOA Sound Tracking | 开关 | 启用/禁用 DOA 追踪 |

### 阶段 6：诊断信息
| 实体 | 类型 | 说明 |
|------|------|------|
| Control Loop Frequency | 传感器 (Hz) | 运动控制循环频率 |
| SDK Version | 文本传感器 | Reachy Mini SDK 版本 |
| Robot Name | 文本传感器 | 设备名称 |
| Wireless Version | 二进制传感器 | 无线版本标志 |
| Simulation Mode | 二进制传感器 | 仿真模式标志 |
| WLAN IP | 文本传感器 | WiFi IP 地址 |
| Error Message | 文本传感器 | 当前错误 |

### 阶段 7：IMU 传感器（仅无线版本）
| 实体 | 类型 | 说明 |
|------|------|------|
| IMU Accel X/Y/Z | 传感器 (m/s²) | 加速度计 |
| IMU Gyro X/Y/Z | 传感器 (rad/s) | 陀螺仪 |
| IMU Temperature | 传感器 (°C) | IMU 温度 |

### 阶段 8：情绪控制
| 实体 | 类型 | 说明 |
|------|------|------|
| Emotion | 选择器 | 选择要播放的情绪（35 个选项）|

### 阶段 10：摄像头
| 实体 | 类型 | 说明 |
|------|------|------|
| Camera | 摄像头 | 实时 MJPEG 流 |

### 3D 可视化卡片
可在 Home Assistant 中安装自定义 Lovelace 卡片，实时 3D 可视化 Reachy Mini 机器人。

安装地址：[ha-reachy-mini](https://github.com/Desmond-Dong/ha-reachy-mini)

功能：
- 实时 3D 机器人可视化
- 交互式机器人状态视图
- 连接机器人守护进程获取实时更新

### 阶段 21：对话
| 实体 | 类型 | 说明 |
|------|------|------|
| Continuous Conversation | 开关 | 多轮对话模式 |

### 阶段 22：手势检测
| 实体 | 类型 | 说明 |
|------|------|------|
| Gesture Detected | 文本传感器 | 当前手势名称 |
| Gesture Confidence | 传感器 (%) | 检测置信度 |

### 阶段 23：人脸检测
| 实体 | 类型 | 说明 |
|------|------|------|
| Face Detected | 二进制传感器 | 视野中是否有人脸 |

### 阶段 24：系统诊断
| 实体 | 类型 | 说明 |
|------|------|------|
| CPU Percent | 传感器 (%) | CPU 使用率 |
| CPU Temperature | 传感器 (°C) | CPU 温度 |
| Memory Percent | 传感器 (%) | 内存使用率 |
| Memory Used | 传感器 (GB) | 已用内存 |
| Disk Percent | 传感器 (%) | 磁盘使用率 |
| Disk Free | 传感器 (GB) | 磁盘可用空间 |
| Uptime | 传感器 (hours) | 系统运行时间 |
| Process CPU | 传感器 (%) | 应用 CPU 使用率 |
| Process Memory | 传感器 (MB) | 应用内存使用 |

---

## 睡眠模式

运行时反应是零配置的：语音阶段、计时器提醒和 HA 状态触发情绪，共用同一套内建行为模型。

### 进入睡眠
- 在 Home Assistant 中打开 `Sleep Control` 开关
- 机器人放松电机、停止摄像头、暂停语音检测

### 唤醒
- 在 Home Assistant 中关闭 `Sleep Control` 开关
- 或说唤醒词
- 机器人恢复所有功能

---

## 故障排除

| 问题 | 解决方案 |
|------|----------|
| 不响应唤醒词 | 检查 Mute 是否关闭，减少背景噪音，并确认已连接 Home Assistant |
| 人脸追踪不工作 | 确保光线充足，检查 Face Detected 传感器 |
| 没有音频输出 | 检查 Speaker Volume，验证 HA 中的 TTS 引擎 |
| 无法连接 HA | 确认在同一网络，检查端口 6053 |
| 手势检测不到 | 确保光线充足，正对摄像头 |

---

## 快速参考

```
唤醒词：       "Okay Nabu"
停止词：       "Stop"
ESPHome 端口： 6053
摄像头端口：   8081 (MJPEG)
```

---

*Reachy Mini 语音助手 v1.0.4*
