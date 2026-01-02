# Reachy Mini Home Assistant Voice Assistant 项目计划

## 📋 参考资源分析

### 1. OHF-Voice/linux-voice-assistant
- **核心功能**：基于 ESPHome 协议的 Home Assistant 语音助手
- **关键组件**：
  - 唤醒词检测（microWakeWord/openWakeWord）
  - ESPHome 协议通信（端口 6053）
  - 音频处理（16KHz 单声道麦克风）
- **技术栈**：Python 3.11/3.13, ESPHome, PulseAudio

### 2. Reachy Mini SDK
- **硬件能力**：4 麦克风、5W 扬声器、广角摄像头、6 自由度头部运动、2 个动画天线
- **Python API**：简单的运动控制接口
- **应用架构**：基于 Hugging Face Spaces 的应用系统

### 3. reachy_mini_conversation_app
- **架构模式**：层次化架构（用户 → AI 服务 → 机器人硬件）
- **技术栈**：OpenAI realtime API, Gradio, SmolVLM2（本地视觉）
- **工具系统**：可扩展的工具系统（move_head, dance, play_emotion 等）

---

## 🎯 项目目标

将 linux-voice-assistant 移植到 Reachy Mini，创建一个可以通过 Home Assistant 控制的语音助手，同时集成 Reachy Mini 的运动和表情能力。

---

## 📊 项目计划（按优先级）

### 阶段一：研究和架构设计（高优先级）

1. **研究 linux-voice-assistant 的核心架构和代码结构**
   - 分析代码目录结构
   - 理解 ESPHome 协议实现
   - 识别可复用的核心模块
   - 评估依赖项和兼容性

2. **分析 Reachy Mini SDK 的硬件接口和 API**
   - 研究音频接口（麦克风/扬声器）
   - 了解运动控制 API（头部运动、表情）
   - 测试设备兼容性

3. **设计应用架构和接口层**
   - 设计模块化架构（音频层、语音层、运动层、通信层）
   - 定义接口规范
   - 设计配置系统
   - 规划错误处理机制

---

### 阶段二：核心功能实现（高优先级）

4. **实现音频设备适配层（麦克风/扬声器）**
   - 适配 Reachy Mini 的 4 麦克风阵列
   - 实现 16KHz 单声道音频处理
   - 集成回声消除（使用 PulseAudio 或替代方案）
   - 音频设备发现和管理

5. **移植唤醒词检测模块**
   - 集成 microWakeWord 或 openWakeWord
   - 支持自定义唤醒词
   - 优化检测性能（低延迟）

6. **实现语音转文字（STT）功能**
   - 选择 STT 引擎（可考虑 Whisper 或其他开源方案）
   - 实现实时语音识别
   - 优化识别准确率

---

### 阶段三：功能扩展（中优先级）

7. **实现文字转语音（TTS）功能**
   - 选择 TTS 引擎（Piper、espeak-ng 等）
   - 集成到 Reachy Mini 扬声器
   - 优化语音质量和速度

8. **集成 Reachy Mini 运动控制**
   - 实现头部运动控制（点头、摇头、转头）
   - 添加表情系统（基于 reachy_mini_dances_library）
   - 创建语音反应性动作（说话时的微动）

9. **实现 ESPHome 协议通信层**
   - 实现 ESPHome 服务器（端口 6053）
   - 支持 Home Assistant 集成
   - 实现命令和状态同步

---

### 阶段四：用户界面和配置（低优先级）

10. **开发 Web UI（Gradio）**
    - 创建设置界面
    - 显示实时状态（唤醒、识别、运动）
    - 支持配置修改
    - 日志查看

11. **实现配置管理系统**
    - 支持自定义唤醒词
    - 音频设备配置
    - 运动参数调整
    - ESPHome 连接设置

12. **编写测试用例和文档**
    - 单元测试
    - 集成测试
    - 用户文档
    - API 文档

13. **打包并发布到 Hugging Face Spaces**
    - 创建 pyproject.toml
    - 配置依赖项
    - 编写 README
    - 发布应用

---

## 🏗️ 建议的项目结构

```
reachy_mini_ha_voice/
├── src/
│   └── reachy_mini_ha_voice/
│       ├── __init__.py
│       ├── main.py              # 应用入口
│       ├── audio/               # 音频处理模块
│       │   ├── __init__.py
│       │   ├── microphone.py
│       │   ├── speaker.py
│       │   └── echo_cancel.py
│       ├── voice/               # 语音处理模块
│       │   ├── __init__.py
│       │   ├── wakeword.py
│       │   ├── stt.py
│       │   └── tts.py
│       ├── motion/              # 运动控制模块
│       │   ├── __init__.py
│       │   ├── head_control.py
│       │   └── emotions.py
│       ├── esphome/             # ESPHome 通信模块
│       │   ├── __init__.py
│       │   └── protocol.py
│       └── config/              # 配置管理
│           ├── __init__.py
│           └── settings.py
├── profiles/                    # 个性化配置
│   └── default/
│       ├── instructions.txt
│       └── tools.txt
├── wakewords/                   # 唤醒词模型
├── pyproject.toml
├── README.md
├── index.html                   # Hugging Face Space 首页
└── style.css
```

---

## 🔑 关键技术决策

1. **音频处理**：使用 Reachy Mini 的 4 麦克风阵列，可能需要麦克风阵列处理算法
2. **STT 引擎**：建议使用 Whisper（开源、准确率高）或 Vosk（轻量级）
3. **TTS 引擎**：建议使用 Piper（高质量、低延迟）
4. **ESPHome 协议**：需要实现完整的 ESPHome API
5. **运动控制**：基于 Reachy Mini SDK，添加语音反应性动作

---

## ⚠️ 潜在挑战

1. **音频设备兼容性**：Reachy Mini 的麦克风阵列可能需要特殊处理
2. **性能优化**：在 Raspberry Pi 4 上运行需要优化性能
3. **ESPHome 协议实现**：需要完整实现 ESPHome API
4. **延迟控制**：语音识别到运动响应的延迟需要最小化
5. **音频流同步**：确保音频流与 Home Assistant 的 STT/TTS 处理同步
6. **网络稳定性**：ESPHome 连接需要稳定的网络环境