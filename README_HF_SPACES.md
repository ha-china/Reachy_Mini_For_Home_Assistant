# Reachy Mini Home Assistant Voice Assistant - Hugging Face Spaces

这是一个可以通过 Hugging Face Spaces 一键安装的 Reachy Mini 语音助手应用，用于连接 Home Assistant。

## 🚀 通过 Hugging Face Spaces 安装

1. 访问你的 Reachy Mini 仪表板
2. 进入 "Applications" -> "Install from Hugging Face"
3. 搜索 "reachy-mini-ha-voice"
4. 点击 "Install" 按钮
5. 等待安装完成

安装完成后，应用程序将出现在 "Applications" 列表中。

## ⚙️ 配置

安装后，点击应用设置图标进行配置：

- **Device Name**: 设备名称（默认: ReachyMini）
- **Enable Reachy**: 启用 Reachy Mini 机器人集成（默认: true）
- **Audio Input Device**: 音频输入设备索引
- **Audio Output Device**: 音频输出设备索引
- **Wake Word**: 唤醒词（默认: okay_nabu）

## 🔌 连接到 Home Assistant

1. 在 Home Assistant 中，进入 "设置" -> "设备与服务"
2. 点击 "添加集成" 按钮
3. 选择 "ESPHome" 然后选择 "设置另一个 ESPHome 实例"
4. 输入 Reachy Mini 的 IP 地址和端口 6053
5. 点击 "提交"

## 📝 使用说明

### 启动应用

在 Reachy Mini 仪表板中：
1. 找到 "reachy-mini-ha-voice" 应用
2. 点击 "Run" 按钮启动
3. 应用将在端口 6053 上运行

### 唤醒词

默认唤醒词是 "Okay Nabu"。你可以说：
- "Okay Nabu, turn on the lights"
- "Okay Nabu, what's the weather?"
- "Okay Nabu, set a timer for 5 minutes"

### Reachy Mini 动作

当启用 Reachy Mini 集成时，机器人会对不同的语音状态做出反应：
- **唤醒时**: 头部抬起
- **监听中**: 头部轻微摆动
- **响应中**: 点头
- **停止时**: 摇头

## 🔧 故障排除

### 音频设备问题

如果无法检测到音频设备：

1. 在 Reachy Mini 终端中运行：
   ```bash
   python -m reachy_mini_ha_voice --list-input-devices
   python -m reachy_mini_ha_voice --list-output-devices
   ```

2. 在应用配置中设置正确的设备索引

### 连接问题

如果无法连接到 Home Assistant：

1. 检查 Reachy Mini 和 Home Assistant 是否在同一网络
2. 确认端口 6053 未被防火墙阻止
3. 查看 Home Assistant 日志中的连接错误

### 调试模式

启用调试日志：

在应用配置中添加环境变量：
```
DEBUG=true
```

## 📚 更多信息

完整文档请访问: [README.md](README.md)

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

Apache License 2.0