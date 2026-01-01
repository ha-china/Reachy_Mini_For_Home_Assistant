# Reachy Mini Home Assistant Voice Assistant - 架构设计

## 1. 系统架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        应用层 (Application Layer)                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Home         │  │ Web UI       │  │ Console      │           │
│  │ Assistant    │  │ (Gradio)     │  │ Interface    │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      业务逻辑层 (Business Logic)                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Voice        │  │ Motion       │  │ Vision       │           │
│  │ Manager      │  │ Controller   │  │ Processor    │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ ESPHome      │  │ State        │  │ Event        │           │
│  │ Handler      │  │ Manager      │  │ Dispatcher   │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                        服务层 (Services)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Wake Word    │  │ STT Engine   │  │ TTS Engine   │           │
│  │ Detector     │  │ (Whisper)    │  │ (Piper)      │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Audio        │  │ Motion       │  │ Face         │           │
│  │ Processor    │  │ Queue        │  │ Tracker      │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      硬件抽象层 (HAL)                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Audio        │  │ Motion       │  │ Camera       │           │
│  │ Adapter      │  │ Adapter      │  │ Adapter      │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│  ┌──────────────┐  ┌──────────────┐                           │
│  │ Reachy Mini  │  │ ESPHome      │                           │
│  │ SDK Wrapper  │  │ Protocol     │                           │
│  └──────────────┘  └──────────────┘                           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Reachy Mini Hardware                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Microphone   │  │ Head Motors  │  │ Camera       │           │
│  │ Array (4)    │  │ (6 DOF)      │  │ (Wide)       │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│  ┌──────────────┐  ┌──────────────┐                           │
│  │ Speaker      │  │ Antennas     │                           │
│  │ (5W)         │  │ (2)          │                           │
│  └──────────────┘  └──────────────┘                           │
└─────────────────────────────────────────────────────────────────┘
```

## 2. 模块设计

### 2.1 音频模块 (audio/)

**职责**：
- 音频设备管理（麦克风、扬声器）
- 音频录制和播放
- 音频格式转换
- 回声消除

**接口**：

```python
class AudioAdapter(ABC):
    """音频设备适配器抽象基类"""
    
    @abstractmethod
    async def list_input_devices(self) -> List[AudioDevice]:
        """列出可用的音频输入设备"""
        pass
    
    @abstractmethod
    async def list_output_devices(self) -> List[AudioDevice]:
        """列出可用的音频输出设备"""
        pass
    
    @abstractmethod
    async def start_recording(self, device_id: str, callback: Callable[[bytes], None]):
        """开始录制音频"""
        pass
    
    @abstractmethod
    async def stop_recording(self):
        """停止录制音频"""
        pass
    
    @abstractmethod
    async def play_audio(self, audio_data: bytes, device_id: str):
        """播放音频"""
        pass


class MicrophoneArray(AudioAdapter):
    """麦克风阵列适配器"""
    
    def __init__(self, sample_rate: int = 16000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        self._stream = None
    
    async def start_recording(self, device_id: str, callback: Callable[[bytes], None]):
        """开始从麦克风阵列录制音频"""
        # 使用 sounddevice 或 pyaudio
        pass


class Speaker(AudioAdapter):
    """扬声器适配器"""
    
    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
    
    async def play_audio(self, audio_data: bytes, device_id: str):
        """播放音频到扬声器"""
        pass
```

### 2.2 语音模块 (voice/)

**职责**：
- 唤醒词检测
- 语音转文字（STT）
- 文字转语音（TTS）

**接口**：

```python
class WakeWordDetector(ABC):
    """唤醒词检测器抽象基类"""
    
    @abstractmethod
    async def load_model(self, model_path: str):
        """加载唤醒词模型"""
        pass
    
    @abstractmethod
    async def process_audio(self, audio_chunk: bytes) -> bool:
        """处理音频块，返回是否检测到唤醒词"""
        pass
    
    @abstractmethod
    async def get_confidence(self) -> float:
        """获取检测置信度"""
        pass


class MicroWakeWordDetector(WakeWordDetector):
    """microWakeWord 检测器"""
    
    def __init__(self, model_path: str):
        self.model = None
        self.features = None
    
    async def load_model(self, model_path: str):
        """加载 microWakeWord 模型"""
        from pymicro_wakeword import MicroWakeWord
        self.model = MicroWakeWord.from_config(model_path)
        self.features = MicroWakeWordFeatures()


class OpenWakeWordDetector(WakeWordDetector):
    """openWakeWord 检测器"""
    
    def __init__(self, model_path: str):
        self.model = None
        self.features = None
    
    async def load_model(self, model_path: str):
        """加载 openWakeWord 模型"""
        from pyopen_wakeword import OpenWakeWord
        self.model = OpenWakeWord(model_path)
        self.features = OpenWakeWordFeatures.from_builtin()


class STTEngine(ABC):
    """语音转文字引擎抽象基类"""
    
    @abstractmethod
    async def transcribe(self, audio_data: bytes) -> str:
        """将音频转换为文字"""
        pass


class WhisperSTT(STTEngine):
    """Whisper STT 引擎"""
    
    def __init__(self, model_name: str = "base"):
        self.model = None
        self.model_name = model_name
    
    async def load_model(self):
        """加载 Whisper 模型"""
        import whisper
        self.model = whisper.load_model(self.model_name)
    
    async def transcribe(self, audio_data: bytes) -> str:
        """将音频转换为文字"""
        # 转换音频格式
        audio = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
        result = self.model.transcribe(audio)
        return result["text"]


class TTSEngine(ABC):
    """文字转语音引擎抽象基类"""
    
    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """将文字转换为音频"""
        pass


class PiperTTS(TTSEngine):
    """Piper TTS 引擎"""
    
    def __init__(self, model_path: str):
        self.model = None
        self.model_path = model_path
    
    async def load_model(self):
        """加载 Piper 模型"""
        from piper import PiperVoice
        self.model = PiperVoice.load(self.model_path)
    
    async def synthesize(self, text: str) -> bytes:
        """将文字转换为音频"""
        # 使用 Piper 合成语音
        pass
```

### 2.3 运动模块 (motion/)

**职责**：
- 头部运动控制
- 表情系统
- 运动队列管理
- 语音反应性运动

**接口**：

```python
class MotionController(ABC):
    """运动控制器抽象基类"""
    
    @abstractmethod
    async def wake_up(self):
        """唤醒机器人"""
        pass
    
    @abstractmethod
    async def turn_off(self):
        """关闭机器人"""
        pass
    
    @abstractmethod
    async def move_head(self, pose: np.ndarray, duration: float):
        """移动头部到指定姿态"""
        pass
    
    @abstractmethod
    async def move_antennas(self, left: float, right: float, duration: float):
        """移动天线"""
        pass


class ReachyMiniMotionController(MotionController):
    """Reachy Mini 运动控制器"""
    
    def __init__(self):
        self.reachy_mini = None
        self.motion_queue = MotionQueue()
    
    async def connect(self, host: str = 'localhost'):
        """连接到 Reachy Mini"""
        from reachy_mini import ReachyMini
        self.reachy_mini = ReachyMini(host=host)
        await self.wake_up()
    
    async def wake_up(self):
        """唤醒机器人"""
        self.reachy_mini.wake_up()
    
    async def turn_off(self):
        """关闭机器人"""
        self.reachy_mini.turn_off()
    
    async def move_head(self, pose: np.ndarray, duration: float):
        """移动头部到指定姿态"""
        self.reachy_mini.goto_target(head=pose, duration=duration)
    
    async def move_antennas(self, left: float, right: float, duration: float):
        """移动天线"""
        self.reachy_mini.goto_target(antennas=[left, right], duration=duration)


class MotionQueue:
    """运动队列管理器"""
    
    def __init__(self):
        self.high_priority = asyncio.Queue()
        self.medium_priority = asyncio.Queue()
        self.low_priority = asyncio.Queue()
        self.is_running = False
    
    async def add_high_priority(self, motion: Motion):
        """添加高优先级运动"""
        await self.high_priority.put(motion)
    
    async def add_medium_priority(self, motion: Motion):
        """添加中优先级运动"""
        await self.medium_priority.put(motion)
    
    async def add_low_priority(self, motion: Motion):
        """添加低优先级运动"""
        await self.low_priority.put(motion)
    
    async def process(self):
        """处理运动队列"""
        self.is_running = True
        while self.is_running:
            # 优先级：高 > 中 > 低
            if not self.high_priority.empty():
                motion = await self.high_priority.get()
            elif not self.medium_priority.empty():
                motion = await self.medium_priority.get()
            elif not self.low_priority.empty():
                motion = await self.low_priority.get()
            else:
                await asyncio.sleep(0.01)
                continue
            
            await motion.execute()
```

### 2.4 ESPHome 模块 (esphome/)

**职责**：
- ESPHome 协议实现
- 与 Home Assistant 通信
- 语音事件处理

**接口**：

```python
class ESPHomeServer(ABC):
    """ESPHome 服务器抽象基类"""
    
    @abstractmethod
    async def start(self, host: str, port: int):
        """启动 ESPHome 服务器"""
        pass
    
    @abstractmethod
    async def stop(self):
        """停止 ESPHome 服务器"""
        pass
    
    @abstractmethod
    async def send_audio(self, audio_data: bytes):
        """发送音频数据到 Home Assistant"""
        pass
    
    @abstractmethod
    async def send_event(self, event_type: VoiceAssistantEventType, data: dict):
        """发送语音事件"""
        pass


class VoiceSatelliteProtocol(ESPHomeServer):
    """语音卫星协议处理器"""
    
    def __init__(self, state: ServerState):
        self.state = state
        self._is_streaming = False
    
    async def handle_message(self, msg: message.Message):
        """处理 ESPHome 消息"""
        if isinstance(msg, VoiceAssistantRequest):
            if msg.start:
                self._is_streaming = True
            else:
                self._is_streaming = False
        
        elif isinstance(msg, VoiceAssistantEventResponse):
            event_type = VoiceAssistantEventType(msg.event_type)
            await self.handle_voice_event(event_type, msg.data)
    
    async def handle_audio(self, audio_chunk: bytes):
        """处理音频数据"""
        if self._is_streaming:
            await self.send_audio(audio_chunk)
    
    async def handle_voice_event(self, event_type: VoiceAssistantEventType, data: dict):
        """处理语音事件"""
        if event_type == VoiceAssistantEventType.VOICE_ASSISTANT_STT_END:
            # STT 完成
            text = data.get('text', '')
            await self.state.voice_manager.process_text(text)
        
        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_TTS_START:
            # TTS 开始
            await self.state.motion_controller.start_speech_reactive_motion()
        
        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_TTS_END:
            # TTS 结束
            await self.state.motion_controller.stop_speech_reactive_motion()
```

### 2.5 配置模块 (config/)

**职责**：
- 配置文件管理
- 用户偏好存储
- 运行时配置

**接口**：

```python
class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config = self.load_config()
    
    def load_config(self) -> dict:
        """加载配置文件"""
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                return json.load(f)
        return self.get_default_config()
    
    def save_config(self):
        """保存配置文件"""
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def get_default_config(self) -> dict:
        """获取默认配置"""
        return {
            "audio": {
                "input_device": None,
                "output_device": None,
                "sample_rate": 16000,
                "channels": 1,
                "block_size": 1024
            },
            "voice": {
                "wake_word": "okay_nabu",
                "stt_engine": "whisper",
                "stt_model": "base",
                "tts_engine": "piper",
                "tts_model": "en_US-lessac-medium"
            },
            "motion": {
                "enabled": True,
                "speech_reactive": True,
                "face_tracking": False
            },
            "esphome": {
                "host": "0.0.0.0",
                "port": 6053,
                "name": "Reachy Mini"
            },
            "robot": {
                "host": "localhost",
                "wireless": False
            }
        }
    
    def get(self, key: str, default=None):
        """获取配置值"""
        keys = key.split('.')
        value = self.config
        for k in keys:
            value = value.get(k, default)
        return value
    
    def set(self, key: str, value):
        """设置配置值"""
        keys = key.split('.')
        config = self.config
        for k in keys[:-1]:
            config = config.setdefault(k, {})
        config[keys[-1]] = value
        self.save_config()
```

## 3. 数据流设计

### 3.1 音频处理流程

```
麦克风阵列
    ↓ (16KHz PCM)
音频块 (1024 samples)
    ↓
┌─────────────────┐
│  唤醒词检测     │
│  (micro/oww)    │
└────────┬────────┘
         │
         ↓ (检测到唤醒词)
    触发唤醒事件
         │
         ↓
┌─────────────────┐
│  发送到 HA      │
│  (ESPHome)      │
└────────┬────────┘
         │
         ↓ (HA 返回 TTS)
┌─────────────────┐
│  播放音频       │
│  (扬声器)       │
└─────────────────┘
```

### 3.2 运动控制流程

```
语音事件
    ↓
┌─────────────────┐
│  运动队列管理   │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  高优先级运动   │
│  (舞蹈、表情)   │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  中优先级运动   │
│  (用户命令)     │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  低优先级运动   │
│  (呼吸、微动)   │
└────────┬────────┘
         │
         ↓
    执行运动
         │
         ↓
┌─────────────────┐
│  Reachy Mini    │
│  SDK            │
└─────────────────┘
```

## 4. 错误处理

### 4.1 错误类型

```python
class AudioDeviceError(Exception):
    """音频设备错误"""
    pass


class MotionError(Exception):
    """运动控制错误"""
    pass


class ESPHomeError(Exception):
    """ESPHome 协议错误"""
    pass


class WakeWordError(Exception):
    """唤醒词检测错误"""
    pass


class STTError(Exception):
    """语音识别错误"""
    pass


class TTSError(Exception):
    """语音合成错误"""
    pass
```

### 4.2 错误处理策略

1. **音频设备错误**：
   - 记录错误日志
   - 尝试重新连接设备
   - 降级到备用设备（如果有）
   - 通知用户

2. **运动控制错误**：
   - 记录错误日志
   - 停止当前运动
   - 检查机器人连接状态
   - 恢复到安全姿态

3. **ESPHome 错误**：
   - 记录错误日志
   - 尝试重新连接 Home Assistant
   - 缓存未发送的消息
   - 通知用户

4. **唤醒词错误**：
   - 记录错误日志
   - 重新加载模型
   - 通知用户

## 5. 性能优化

### 5.1 音频处理

- 使用异步 I/O 减少阻塞
- 音频块大小优化（1024 samples）
- 使用 numpy 加速数值计算
- 预分配缓冲区减少内存分配

### 5.2 运动控制

- 运动队列优先级管理
- 运动平滑插值
- 批量运动命令合并
- 延迟预算管理

### 5.3 网络

- ESPHome 连接池
- 消息批量发送
- 压缩音频数据
- 心跳检测

## 6. 安全考虑

1. **音频隐私**：
   - 不存储用户音频（除非明确授权）
   - 本地处理优先
   - 加密传输

2. **运动安全**：
   - 角度限制
   - 速度限制
   - 碰撞检测
   - 紧急停止

3. **网络安全**：
   - ESPHome 认证
   - TLS 加密
   - 防火墙配置
   - 访问控制

## 7. 测试策略

### 7.1 单元测试

- 音频模块测试
- 语音模块测试
- 运动模块测试
- ESPHome 模块测试

### 7.2 集成测试

- 端到端音频流程
- 运动控制流程
- ESPHome 通信流程

### 7.3 硬件测试

- Reachy Mini 连接测试
- 音频设备测试
- 运动功能测试

## 8. 部署

### 8.1 依赖项

```toml
[project]
name = "reachy-mini-ha-voice"
version = "0.1.0"
requires-python = ">=3.8"

dependencies = [
    # Reachy Mini SDK
    "reachy-mini",
    
    # 音频处理
    "sounddevice>=0.4.6",
    "numpy>=1.24.0",
    
    # 语音处理
    "pymicro-wakeword>=2,<3",
    "pyopen-wakeword>=1,<2",
    "openai-whisper>=20231117",
    "piper-tts>=1.2.0",
    
    # ESPHome
    "aioesphomeapi>=42.0.0",
    "zeroconf>=0.100.0",
    
    # 运动控制
    "scipy>=1.10.0",
    
    # Web UI
    "gradio>=4.0.0",
    
    # 计算机视觉（可选）
    "opencv-python>=4.8.0",
    "mediapipe>=0.10.0",
    
    # 通信
    "websockets>=12.0",
    
    # 配置
    "pydantic>=2.0.0",
]

[project.optional-dependencies]
wireless = [
    "reachy-mini[wireless]",
]

vision = [
    "pollen-vision",
    "torch>=2.0.0",
    "transformers>=4.30.0",
]

dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.21.0",
    "ruff>=0.1.0",
]
```

### 8.2 安装步骤

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate

# 安装基础依赖
pip install -e .

# 安装可选依赖
pip install -e .[wireless,vision,dev]
```

### 8.3 运行

```bash
# 启动应用
python -m reachy_mini_ha_voice

# 启动 Web UI
python -m reachy_mini_ha_voice --gradio

# 启动无线版本
python -m reachy_mini_ha_voice --wireless
```