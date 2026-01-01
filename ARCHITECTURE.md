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
│  │ Voice        │  │ Motion       │  │ State        │           │
│  │ Manager      │  │ Controller   │  │ Manager      │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│  ┌──────────────┐  ┌──────────────┐                           │
│  │ ESPHome      │  │ Event        │                           │
│  │ Handler      │  │ Dispatcher   │                           │
│  └──────────────┘  └──────────────┘                           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                        服务层 (Services)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Wake Word    │  │ Audio        │  │ Motion       │           │
│  │ Detector     │  │ Processor    │  │ Queue        │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│  ┌──────────────────────────────────────────────────────┐       │
│  │ ESPHome Protocol (Audio Streaming to/from HA)       │       │
│  └──────────────────────────────────────────────────────┘       │
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
│              Reachy Mini Hardware + Home Assistant              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Microphone   │  │ Head Motors  │  │ Camera       │           │
│  │ Array (4)    │  │ (6 DOF)      │  │ (Wide)       │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│  ┌──────────────┐  ┌──────────────┐                           │
│  │ Speaker      │  │ Antennas     │                           │
│  │ (5W)         │  │ (2)          │                           │
│  └──────────────┘  └──────────────┘                           │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ Home Assistant (STT/TTS Processing)                 │    │
│  └──────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## 2. 核心设计原则

### 2.1 基于 linux-voice-assistant
本项目基于 [OHF-Voice/linux-voice-assistant](https://github.com/OHF-Voice/linux-voice-assistant) 的架构设计，主要特点：

- **STT/TTS 由 Home Assistant 处理**：音频数据通过 ESPHome 协议传输到 Home Assistant，由 HA 进行语音识别和合成
- **本地唤醒词检测**：使用 microWakeWord 或 openWakeWord 进行离线唤醒词检测
- **ESPHome 协议通信**：通过 ESPHome 协议与 Home Assistant 通信
- **运动控制增强**：集成 Reachy Mini 的运动控制能力

### 2.2 架构特点
- **模块化设计**：音频、语音、运动、ESPHome 各模块独立
- **异步处理**：使用 asyncio 实现高性能异步处理
- **状态管理**：集中的状态管理（ServerState）
- **事件驱动**：基于事件的通信机制

## 3. 模块设计

### 3.1 音频模块 (audio/)

**职责**：
- 音频设备管理（麦克风、扬声器）
- 音频录制和播放
- 音频格式转换（16KHz 单声道 PCM）

**接口**：

```python
class AudioAdapter(ABC):
    """音频设备适配器抽象基类"""
    
    @abstractmethod
    async def list_input_devices(self) -> List[AudioDevice]:
        """列出可用的音频输入设备"""
        pass
    
    @abstractmethod
    async def start_recording(
        self,
        device_id: str,
        callback: Callable[[bytes], None],
        sample_rate: int = 16000,
        channels: int = 1,
        block_size: int = 1024
    ):
        """开始录制音频"""
        pass
    
    @abstractmethod
    async def play_audio(
        self,
        audio_data: bytes,
        device_id: str,
        sample_rate: int = 16000,
        channels: int = 1
    ):
        """播放音频"""
        pass


class MicrophoneArray(AudioAdapter):
    """麦克风阵列适配器（Reachy Mini 的 4 麦克风阵列）"""
    
    def __init__(self, sample_rate: int = 16000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        self._stream = None
        self._is_recording = False
        self._callback = None
        self._loop = None


class Speaker(AudioAdapter):
    """扬声器适配器（Reachy Mini 的 5W 扬声器）"""
    
    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
```

**音频处理器**：

```python
class AudioProcessor:
    """处理音频块，用于唤醒词检测和流式传输"""
    
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        block_size: int = 1024
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_size = block_size
        
        self._wake_word_callbacks: list[Callable[[bytes], None]] = []
        self._stream_callbacks: list[Callable[[bytes], None]] = []
    
    def add_wake_word_callback(self, callback: Callable[[bytes], None]):
        """添加唤醒词检测回调"""
        self._wake_word_callbacks.append(callback)
    
    def add_stream_callback(self, callback: Callable[[bytes], None]):
        """添加音频流回调（发送到 Home Assistant）"""
        self._stream_callbacks.append(callback)
    
    async def process_audio_chunk(self, audio_chunk: bytes):
        """处理音频块"""
        # 调用唤醒词检测回调
        for callback in self._wake_word_callbacks:
            callback(audio_chunk)
        
        # 调用流式传输回调
        for callback in self._stream_callbacks:
            callback(audio_chunk)
```

### 3.2 语音模块 (voice/)

**职责**：
- 唤醒词检测（本地离线）
- STT/TTS 由 Home Assistant 处理（不在此模块）

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


class MicroWakeWordDetector(WakeWordDetector):
    """microWakeWord 检测器（轻量级，适合 Raspberry Pi）"""
    
    def __init__(self, model_path: str):
        self.model = None
        self.features = None
        self.model_path = Path(model_path)
        self._confidence = 0.0
        self._loaded = False
    
    async def load_model(self, model_path: str):
        """加载 microWakeWord 模型"""
        from pymicro_wakeword import MicroWakeWord, MicroWakeWordFeatures
        
        self.features = MicroWakeWordFeatures()
        self.model = MicroWakeWord.from_config(model_path)
        self._loaded = True
    
    async def process_audio(self, audio_chunk: bytes) -> bool:
        """处理音频块"""
        import numpy as np
        audio_array = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0
        
        features = self.features.process_streaming(audio_array)
        for feature in features:
            score = self.model.process_streaming(feature)
            if score is not None and score >= 0.5:
                return True
        return False


class OpenWakeWordDetector(WakeWordDetector):
    """openWakeWord 检测器（更多唤醒词选择）"""
    
    def __init__(self, model_path: str):
        self.model = None
        self.features = None
        self.model_path = Path(model_path)
        self._confidence = 0.0
        self._loaded = False
    
    async def load_model(self, model_path: str):
        """加载 openWakeWord 模型"""
        from pyopen_wakeword import OpenWakeWord, OpenWakeWordFeatures
        
        self.features = OpenWakeWordFeatures.from_builtin()
        self.model = OpenWakeWord(model_path)
        self._loaded = True
    
    async def process_audio(self, audio_chunk: bytes) -> bool:
        """处理音频块"""
        import numpy as np
        audio_array = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0
        
        features = self.features.process_streaming(audio_array)
        for feature in features:
            scores = self.model.process_streaming(feature)
            for score in scores:
                if score >= 0.5:
                    return True
        return False
```

### 3.3 运动模块 (motion/)

**职责**：
- 头部运动控制（6 自由度）
- 天线控制（2 个天线）
- 运动队列管理
- 语音反应性运动

**接口**：

```python
class MotionController(ABC):
    """运动控制器抽象基类"""
    
    @abstractmethod
    async def connect(self, host: str = 'localhost'):
        """连接到机器人"""
        pass
    
    @abstractmethod
    async def wake_up(self):
        """唤醒机器人"""
        pass
    
    @abstractmethod
    async def turn_off(self):
        """关闭机器人"""
        pass
    
    @abstractmethod
    async def move_head(self, pose: np.ndarray, duration: float = 1.0):
        """移动头部到姿态"""
        pass
    
    @abstractmethod
    async def move_antennas(self, left: float, right: float, duration: float = 1.0):
        """移动天线"""
        pass
    
    @abstractmethod
    async def nod(self, count: int = 1, duration: float = 0.5):
        """点头"""
        pass
    
    @abstractmethod
    async def shake(self, count: int = 1, duration: float = 0.5):
        """摇头"""
        pass
    
    @abstractmethod
    async def start_speech_reactive_motion(self):
        """开始语音反应性运动"""
        pass
    
    @abstractmethod
    async def stop_speech_reactive_motion(self):
        """停止语音反应性运动"""
        pass


class ReachyMiniMotionController(MotionController):
    """Reachy Mini 运动控制器"""
    
    def __init__(self):
        self.reachy_mini = None
        self._connected = False
        self._speech_reactive = False
        self._speech_task = None
    
    async def connect(self, host: str = 'localhost'):
        """连接到 Reachy Mini"""
        from reachy_mini import ReachyMini
        
        self.reachy_mini = ReachyMini(host=host)
        self._connected = True
    
    async def wake_up(self):
        """唤醒机器人"""
        self.reachy_mini.wake_up()
    
    async def turn_off(self):
        """关闭机器人"""
        self.reachy_mini.turn_off()
    
    async def move_head(self, pose: np.ndarray, duration: float = 1.0):
        """移动头部到姿态"""
        self.reachy_mini.goto_target(head=pose, duration=duration)
    
    async def move_antennas(self, left: float, right: float, duration: float = 1.0):
        """移动天线"""
        self.reachy_mini.goto_target(antennas=[left, right], duration=duration)
    
    async def nod(self, count: int = 1, duration: float = 0.5):
        """点头"""
        import numpy as np
        from scipy.spatial.transform import Rotation as R
        
        for _ in range(count):
            # 点头
            pose_down = np.eye(4)
            pose_down[:3, :3] = R.from_euler('xyz', [15, 0, 0], degrees=True).as_matrix()
            await self.move_head(pose_down, duration=duration / 2)
            
            pose_up = np.eye(4)
            pose_up[:3, :3] = R.from_euler('xyz', [-15, 0, 0], degrees=True).as_matrix()
            await self.move_head(pose_up, duration=duration / 2)
    
    async def shake(self, count: int = 1, duration: float = 0.5):
        """摇头"""
        import numpy as np
        from scipy.spatial.transform import Rotation as R
        
        for _ in range(count):
            # 摇头
            pose_left = np.eye(4)
            pose_left[:3, :3] = R.from_euler('xyz', [0, 0, -20], degrees=True).as_matrix()
            await self.move_head(pose_left, duration=duration / 2)
            
            pose_right = np.eye(4)
            pose_right[:3, :3] = R.from_euler('xyz', [0, 0, 20], degrees=True).as_matrix()
            await self.move_head(pose_right, duration=duration / 2)
    
    async def start_speech_reactive_motion(self):
        """开始语音反应性运动（说话时的微动）"""
        self._speech_reactive = True
        self._speech_task = asyncio.create_task(self._speech_reactive_loop())
    
    async def stop_speech_reactive_motion(self):
        """停止语音反应性运动"""
        self._speech_reactive = False
        if self._speech_task:
            self._speech_task.cancel()
    
    async def _speech_reactive_loop(self):
        """语音反应性运动循环"""
        import numpy as np
        from scipy.spatial.transform import Rotation as R
        
        while self._speech_reactive:
            # 生成微小的摆动
            roll = np.sin(asyncio.get_event_loop().time() * 2) * 3
            pose = np.eye(4)
            pose[:3, :3] = R.from_euler('xyz', [0, 0, roll], degrees=True).as_matrix()
            
            await self.move_head(pose, duration=0.1)
            await asyncio.sleep(0.1)
```

**运动队列**：

```python
class MotionQueue:
    """运动队列管理器"""
    
    def __init__(self):
        self.high_priority = asyncio.Queue()
        self.medium_priority = asyncio.Queue()
        self.low_priority = asyncio.Queue()
        self.is_running = False
        self._current_motion = None
        self._task = None
    
    async def add_motion(self, motion: Motion):
        """添加运动到队列"""
        if motion.priority == MotionPriority.HIGH:
            await self.high_priority.put(motion)
        elif motion.priority == MotionPriority.MEDIUM:
            await self.medium_priority.put(motion)
        elif motion.priority == MotionPriority.LOW:
            await self.low_priority.put(motion)
    
    async def start(self):
        """开始处理运动队列"""
        self.is_running = True
        self._task = asyncio.create_task(self._process_queue())
    
    async def stop(self):
        """停止处理运动队列"""
        self.is_running = False
        if self._task:
            self._task.cancel()
    
    async def _process_queue(self):
        """处理运动队列"""
        while self.is_running:
            # 优先级：HIGH > MEDIUM > LOW
            motion = await self._get_next_motion()
            
            if motion is None:
                await asyncio.sleep(0.01)
                continue
            
            self._current_motion = motion
            await motion.execute()
            self._current_motion = None
    
    async def _get_next_motion(self) -> Optional[Motion]:
        """获取下一个运动"""
        if not self.high_priority.empty():
            return await self.high_priority.get()
        elif not self.medium_priority.empty():
            return await self.medium_priority.get()
        elif not self.low_priority.empty():
            return await self.low_priority.get()
        else:
            return None
```

### 3.4 ESPHome 模块 (esphome/)

**职责**：
- ESPHome 协议实现
- 与 Home Assistant 通信
- 音频流传输
- 事件处理

**接口**：

```python
class ESPHomeServer:
    """ESPHome 协议服务器"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 6053):
        self.host = host
        self.port = port
        self._server = None
        self._is_running = False
        self._clients = []
        self._audio_callback = None
        self._event_callback = None
    
    async def start(self):
        """启动 ESPHome 服务器"""
        self._server = await asyncio.start_server(
            self._handle_client,
            self.host,
            self.port
        )
        self._is_running = True
    
    async def stop(self):
        """停止 ESPHome 服务器"""
        self._is_running = False
        
        for client in self._clients:
            client.close()
        self._clients.clear()
        
        if self._server:
            self._server.close()
            await self._server.wait_closed()
    
    def set_audio_callback(self, callback: Callable[[bytes], None]):
        """设置音频回调（接收来自 Home Assistant 的 TTS 音频）"""
        self._audio_callback = callback
    
    def set_event_callback(self, callback: Callable[[VoiceAssistantEventType, dict], None]):
        """设置事件回调（接收来自 Home Assistant 的事件）"""
        self._event_callback = callback
    
    async def send_audio(self, audio_data: bytes):
        """发送音频数据到 Home Assistant（STT 输入）"""
        for client in self._clients:
            try:
                client.write(audio_data)
                await client.drain()
            except Exception as e:
                logger.error(f"Error sending audio to client: {e}")
    
    async def send_event(self, event_type: VoiceAssistantEventType, data: dict):
        """发送事件到 Home Assistant"""
        if self._event_callback:
            self._event_callback(event_type, data)
    
    async def _handle_client(self, reader, writer):
        """处理客户端连接"""
        client_addr = writer.get_extra_info('peername')
        self._clients.append(writer)
        
        try:
            while self._is_running:
                data = await reader.read(4096)
                if not data:
                    break
                
                # 处理来自 Home Assistant 的数据
                await self._process_data(data)
        except Exception as e:
            logger.error(f"Error handling client {client_addr}: {e}")
        finally:
            self._clients.remove(writer)
            writer.close()
            await writer.wait_closed()


class VoiceSatelliteProtocol:
    """语音卫星协议处理器"""
    
    def __init__(self, state: ServerState):
        self.state = state
        self._is_streaming = False
        self._refractory_period = 2.0
        self._last_wake_word_time = 0.0
    
    async def handle_audio(self, audio_chunk: bytes):
        """处理音频块（发送到 Home Assistant）"""
        if self._is_streaming and self.state.esphome_server:
            await self.state.esphome_server.send_audio(audio_chunk)
    
    async def handle_wake_word(self):
        """处理唤醒词检测"""
        current_time = asyncio.get_event_loop().time()
        
        # 检查冷却期
        if current_time - self._last_wake_word_time < self._refractory_period:
            return
        
        self._last_wake_word_time = current_time
        
        # 发送唤醒词事件到 Home Assistant
        if self.state.esphome_server:
            await self.state.esphome_server.send_event(
                VoiceAssistantEventType.VOICE_ASSISTANT_WAKE_WORD_END,
                {"wake_word": "detected"}
            )
        
        # 开始流式传输
        self._is_streaming = True
    
    async def stop_streaming(self):
        """停止流式传输"""
        self._is_streaming = False


class VoiceAssistantEventType(Enum):
    """语音助手事件类型"""
    VOICE_ASSISTANT_START = 0
    VOICE_ASSISTANT_END = 1
    VOICE_ASSISTANT_ERROR = 2
    VOICE_ASSISTANT_STT_START = 3
    VOICE_ASSISTANT_STT_END = 4
    VOICE_ASSISTANT_TTS_START = 5
    VOICE_ASSISTANT_TTS_END = 6
    VOICE_ASSISTANT_WAKE_WORD_START = 9
    VOICE_ASSISTANT_WAKE_WORD_END = 10
```

### 3.5 配置模块 (config/)

**职责**：
- 配置文件管理
- 用户偏好存储
- 运行时配置

**接口**：

```python
class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self.config = self.load_config()
    
    def load_config(self) -> dict:
        """加载配置文件"""
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return self.get_default_config()
    
    def save_config(self):
        """保存配置文件"""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
    
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
                "wake_word_dirs": ["wakewords"]
            },
            "motion": {
                "enabled": True,
                "speech_reactive": True
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
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值（支持嵌套键）"""
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, default)
            else:
                return default
        return value
    
    def set(self, key: str, value: Any):
        """设置配置值（支持嵌套键）"""
        keys = key.split('.')
        config = self.config
        for k in keys[:-1]:
            config = config.setdefault(k, {})
        config[keys[-1]] = value
        self.save_config()
```

### 3.6 状态管理 (state.py)

**职责**：
- 全局状态管理
- 组件生命周期管理

**接口**：

```python
@dataclass
class ServerState:
    """全局服务器状态"""
    name: str
    
    # 配置
    config: Optional[ConfigManager] = None
    
    # 音频
    microphone: Optional[MicrophoneArray] = None
    speaker: Optional[Speaker] = None
    audio_queue: Queue = field(default_factory=Queue)
    
    # 语音
    wake_word_detector: Optional[WakeWordDetector] = None
    active_wake_words: list = field(default_factory=list)
    
    # 运动
    motion_controller: Optional[MotionController] = None
    motion_queue: Optional[MotionQueue] = None
    
    # ESPHome
    esphome_server: Optional[ESPHomeServer] = None
    voice_satellite: Optional[VoiceSatelliteProtocol] = None
    
    # 状态
    is_running: bool = False
    is_streaming: bool = False
    
    # 回调
    on_wake_word: Optional[callable] = None
    on_stt_result: Optional[callable] = None
    on_tts_audio: Optional[callable] = None
    
    async def cleanup(self):
        """清理资源"""
        if self.microphone:
            await self.microphone.stop_recording()
        
        if self.motion_controller:
            await self.motion_controller.stop_speech_reactive_motion()
            await self.motion_controller.turn_off()
            await self.motion_controller.disconnect()
        
        if self.motion_queue:
            await self.motion_queue.stop()
        
        if self.esphome_server:
            await self.esphome_server.stop()
```

### 3.7 主应用 (app.py)

**职责**：
- 应用生命周期管理
- 组件初始化和协调
- 事件处理

**接口**：

```python
class ReachyMiniVoiceApp:
    """主应用类"""
    
    def __init__(
        self,
        name: str,
        config: ConfigManager,
        audio_input_device: Optional[str] = None,
        audio_output_device: Optional[str] = None,
        wake_model: Optional[str] = None,
        wake_word_dirs: Optional[list] = None,
        host: str = "0.0.0.0",
        port: int = 6053,
        robot_host: str = "localhost",
        wireless: bool = False,
        gradio: bool = False
    ):
        self.name = name
        self.config = config
        self.audio_input_device = audio_input_device
        self.audio_output_device = audio_output_device
        self.wake_model = wake_model
        self.wake_word_dirs = wake_word_dirs
        self.host = host
        self.port = port
        self.robot_host = robot_host
        self.wireless = wireless
        self.gradio = gradio
        
        self.state = ServerState(name)
        self._is_running = False
    
    async def start(self):
        """启动应用"""
        # 初始化状态
        await self.state.initialize(self.config)
        
        # 设置回调
        self._setup_callbacks()
        
        # 启动音频录制
        await self.state.microphone.start_recording(
            self.audio_input_device,
            self._audio_callback,
            sample_rate=self.config.get("audio.sample_rate", 16000),
            channels=self.config.get("audio.channels", 1),
            block_size=self.config.get("audio.block_size", 1024)
        )
        
        # 启动 ESPHome 服务器
        await self.state.esphome_server.start()
        
        # 注册 mDNS 发现
        await self._register_mdns()
        
        self._is_running = True
        
        # 保持运行
        while self._is_running:
            await asyncio.sleep(1)
    
    async def stop(self):
        """停止应用"""
        self._is_running = False
        await self.state.cleanup()
    
    def _setup_callbacks(self):
        """设置回调"""
        self.state.audio_processor.add_wake_word_callback(self._on_audio_chunk)
        self.state.audio_processor.add_stream_callback(self._on_stream_audio)
    
    async def _audio_callback(self, audio_chunk: bytes):
        """音频录制回调"""
        await self.state.audio_processor.process_audio_chunk(audio_chunk)
    
    async def _on_audio_chunk(self, audio_chunk: bytes):
        """唤醒词检测回调"""
        if self.state.wake_word_detector:
            detected = await self.state.wake_word_detector.process_audio(audio_chunk)
            if detected:
                await self._on_wake_word_detected()
    
    async def _on_stream_audio(self, audio_chunk: bytes):
        """音频流传输回调（发送到 Home Assistant）"""
        if self.state.voice_satellite:
            await self.state.voice_satellite.handle_audio(audio_chunk)
    
    async def _on_wake_word_detected(self):
        """唤醒词检测回调"""
        # 点头确认
        if self.state.motion_controller:
            await self.state.motion_controller.nod(count=1, duration=0.3)
        
        # 触发语音卫星
        if self.state.voice_satellite:
            await self.state.voice_satellite.handle_wake_word()
    
    async def handle_tts_audio(self, audio_data: bytes):
        """处理来自 Home Assistant 的 TTS 音频"""
        # 播放音频
        if self.state.speaker:
            await self.state.speaker.play_audio(
                audio_data,
                self.audio_output_device,
                sample_rate=self.config.get("audio.sample_rate", 16000),
                channels=self.config.get("audio.channels", 1)
            )
    
    async def handle_stt_result(self, text: str):
        """处理来自 Home Assistant 的 STT 结果"""
        # 处理文本（添加自定义逻辑）
        pass
    
    async def _register_mdns(self):
        """注册 mDNS 服务发现"""
        from zeroconf import ServiceInfo, Zeroconf
        
        info = ServiceInfo(
            "_esphomelib._tcp.local.",
            f"{self.name}._esphomelib._tcp.local.",
            addresses=[],
            port=self.port,
            properties={
                "version": "1.0",
                "name": self.name,
                "platform": "reachy_mini"
            }
        )
        
        zeroconf = Zeroconf()
        zeroconf.register_service(info)
```

## 4. 数据流

### 4.1 音频输入流程

```
麦克风阵列 (4 麦克风)
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
│  开始流式传输   │
│  (ESPHome)      │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  发送到 HA      │
│  (STT 输入)     │
└─────────────────┘
```

### 4.2 音频输出流程

```
Home Assistant (TTS 输出)
    ↓
┌─────────────────┐
│  ESPHome 服务器  │
│  (接收音频)     │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  播放音频       │
│  (扬声器)       │
└─────────────────┘
```

### 4.3 运动控制流程

```
唤醒词检测 / STT 结果 / TTS 事件
    ↓
┌─────────────────┐
│  运动队列管理   │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  高优先级运动   │
│  (唤醒词确认)   │
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
│  (语音反应)     │
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

## 5. 依赖项

### 5.1 核心依赖

```toml
dependencies = [
    # Reachy Mini SDK
    "reachy-mini",
    
    # 音频处理
    "sounddevice>=0.4.6",
    "numpy>=1.24.0",
    
    # 语音处理
    "pymicro-wakeword>=2.0.0,<3.0.0",
    "pyopen-wakeword>=1.0.0,<2.0.0",
    
    # ESPHome
    "aioesphomeapi>=42.0.0",
    "zeroconf>=0.100.0",
    
    # 运动控制
    "scipy>=1.10.0",
    
    # Web UI (可选)
    "gradio>=4.0.0",
]
```

### 5.2 可选依赖

```toml
[project.optional-dependencies]
wireless = [
    "reachy-mini[wireless]",
]

vision = [
    "pollen-vision",
    "opencv-python>=4.8.0",
    "mediapipe>=0.10.0",
]

dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.21.0",
    "ruff>=0.1.0",
]
```

## 6. 性能优化

### 6.1 音频处理
- 使用异步 I/O 减少阻塞
- 音频块大小优化（1024 samples）
- 使用 numpy 加速数值计算
- 预分配缓冲区减少内存分配

### 6.2 运动控制
- 运动队列优先级管理
- 运动平滑插值
- 批量运动命令合并
- 延迟预算管理

### 6.3 网络
- ESPHome 连接池
- 消息批量发送
- 压缩音频数据
- 心跳检测

## 7. 安全考虑

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

## 8. 部署

### 8.1 安装步骤

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate

# 安装基础依赖
pip install -e .

# 安装可选依赖
pip install -e .[wireless,vision,dev]
```

### 8.2 运行

```bash
# 启动应用
python -m reachy_mini_ha_voice

# 启动 Web UI
python -m reachy_mini_ha_voice --gradio

# 启动无线版本
python -m reachy_mini_ha_voice --wireless
```

### 8.3 Home Assistant 集成

1. 在 Home Assistant 中添加 ESPHome 集成
2. 输入 Reachy Mini 的 IP 地址和端口（6053）
3. 配置 STT/TTS 服务
4. 创建自动化和脚本