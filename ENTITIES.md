# Reachy Mini Home Assistant 实体使用指南

本文档介绍如何在 Home Assistant 中使用 Reachy Mini 暴露的 ESPHome 实体来控制机器人。

## 概述

Reachy Mini HA Voice 应用通过 ESPHome 协议向 Home Assistant 暴露了多个实体，允许你完全控制机器人的运动、电机状态和系统信息。

## 实体列表

### 📊 Phase 1: 基础状态与音量控制

#### 1. Daemon State (文本传感器)
- **实体 ID**: `sensor.reachy_mini_daemon_state`
- **类型**: 只读文本传感器
- **说明**: 显示 Reachy Mini Daemon 的当前状态
- **可能的值**:
  - `not_initialized` - 未初始化
  - `starting` - 启动中
  - `running` - 运行中
  - `stopping` - 停止中
  - `stopped` - 已停止
  - `error` - 错误状态
  - `not_available` - 机器人不可用（独立模式）

#### 2. Backend Ready (二进制传感器)
- **实体 ID**: `binary_sensor.reachy_mini_backend_ready`
- **类型**: 只读布尔传感器
- **说明**: 指示后端服务是否就绪
- **值**: `on` (就绪) / `off` (未就绪)

#### 3. Error Message (文本传感器)
- **实体 ID**: `sensor.reachy_mini_error_message`
- **类型**: 只读文本传感器
- **说明**: 显示当前的错误信息（如果有）

#### 4. Speaker Volume (数字控制)
- **实体 ID**: `number.reachy_mini_speaker_volume`
- **类型**: 可读写数字控制
- **范围**: 0-100%
- **说明**: 控制扬声器音量
- **使用示例**:
  ```yaml
  # 设置音量为 80%
  service: number.set_value
  target:
    entity_id: number.reachy_mini_speaker_volume
  data:
    value: 80
  ```

---

### ⚙️ Phase 2: 电机控制

#### 5. Motors Enabled (开关)
- **实体 ID**: `switch.reachy_mini_motors_enabled`
- **类型**: 可读写开关
- **说明**: 启用或禁用所有电机的扭矩
- **使用示例**:
  ```yaml
  # 启用电机
  service: switch.turn_on
  target:
    entity_id: switch.reachy_mini_motors_enabled

  # 禁用电机
  service: switch.turn_off
  target:
    entity_id: switch.reachy_mini_motors_enabled
  ```

#### 6. Motor Mode (选择器)
- **实体 ID**: `select.reachy_mini_motor_mode`
- **类型**: 可读写选择器
- **选项**:
  - `enabled` - 电机启用，位置控制
  - `disabled` - 电机禁用，无扭矩
  - `gravity_compensation` - 重力补偿模式
- **使用示例**:
  ```yaml
  # 设置为重力补偿模式
  service: select.select_option
  target:
    entity_id: select.reachy_mini_motor_mode
  data:
    option: gravity_compensation
  ```

#### 7. Wake Up (按钮)
- **实体 ID**: `button.reachy_mini_wake_up`
- **类型**: 按钮
- **说明**: 执行唤醒动画
- **使用示例**:
  ```yaml
  service: button.press
  target:
    entity_id: button.reachy_mini_wake_up
  ```

#### 8. Go to Sleep (按钮)
- **实体 ID**: `button.reachy_mini_go_to_sleep`
- **类型**: 按钮
- **说明**: 执行睡眠动画
- **使用示例**:
  ```yaml
  service: button.press
  target:
    entity_id: button.reachy_mini_go_to_sleep
  ```

---

### 🎯 Phase 3: 姿态控制

#### 头部位置控制 (X, Y, Z)

##### 9. Head X Position (数字控制)
- **实体 ID**: `number.reachy_mini_head_x`
- **范围**: -50mm ~ +50mm
- **说明**: 控制头部在 X 轴的位置

##### 10. Head Y Position (数字控制)
- **实体 ID**: `number.reachy_mini_head_y`
- **范围**: -50mm ~ +50mm
- **说明**: 控制头部在 Y 轴的位置

##### 11. Head Z Position (数字控制)
- **实体 ID**: `number.reachy_mini_head_z`
- **范围**: -50mm ~ +50mm
- **说明**: 控制头部在 Z 轴的位置

**使用示例**:
```yaml
# 移动头部到指定位置
service: number.set_value
target:
  entity_id:
    - number.reachy_mini_head_x
    - number.reachy_mini_head_y
    - number.reachy_mini_head_z
data:
  value: 10  # 每个轴移动 10mm
```

#### 头部角度控制 (Roll, Pitch, Yaw)

##### 12. Head Roll (数字控制)
- **实体 ID**: `number.reachy_mini_head_roll`
- **范围**: -40° ~ +40°
- **说明**: 控制头部翻滚角（左右倾斜）

##### 13. Head Pitch (数字控制)
- **实体 ID**: `number.reachy_mini_head_pitch`
- **范围**: -40° ~ +40°
- **说明**: 控制头部俯仰角（上下点头）

##### 14. Head Yaw (数字控制)
- **实体 ID**: `number.reachy_mini_head_yaw`
- **范围**: -180° ~ +180°
- **说明**: 控制头部偏航角（左右转头）

**使用示例**:
```yaml
# 让机器人点头（pitch = -20°）
service: number.set_value
target:
  entity_id: number.reachy_mini_head_pitch
data:
  value: -20

# 让机器人摇头（yaw 左右摆动）
service: number.set_value
target:
  entity_id: number.reachy_mini_head_yaw
data:
  value: 30
```

#### 身体控制

##### 15. Body Yaw (数字控制)
- **实体 ID**: `number.reachy_mini_body_yaw`
- **范围**: -160° ~ +160°
- **说明**: 控制身体的偏航角（旋转）

**使用示例**:
```yaml
# 旋转身体 45 度
service: number.set_value
target:
  entity_id: number.reachy_mini_body_yaw
data:
  value: 45
```

#### 天线控制

##### 16. Left Antenna (数字控制)
- **实体 ID**: `number.reachy_mini_antenna_left`
- **范围**: -90° ~ +90°
- **说明**: 控制左天线角度

##### 17. Right Antenna (数字控制)
- **实体 ID**: `number.reachy_mini_antenna_right`
- **范围**: -90° ~ +90°
- **说明**: 控制右天线角度

**使用示例**:
```yaml
# 让天线竖起来表示兴奋
service: number.set_value
target:
  entity_id:
    - number.reachy_mini_antenna_left
    - number.reachy_mini_antenna_right
data:
  value: 45
```

---

## 自动化示例

### 示例 1: 早晨唤醒机器人

```yaml
automation:
  - alias: "早晨唤醒 Reachy Mini"
    trigger:
      - platform: time
        at: "08:00:00"
    action:
      - service: button.press
        target:
          entity_id: button.reachy_mini_wake_up
      - service: number.set_value
        target:
          entity_id: number.reachy_mini_speaker_volume
        data:
          value: 70
```

### 示例 2: 晚上让机器人睡觉

```yaml
automation:
  - alias: "晚上 Reachy Mini 睡觉"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: button.press
        target:
          entity_id: button.reachy_mini_go_to_sleep
      - service: switch.turn_off
        target:
          entity_id: switch.reachy_mini_motors_enabled
```

### 示例 3: 有人回家时打招呼

```yaml
automation:
  - alias: "Reachy Mini 打招呼"
    trigger:
      - platform: state
        entity_id: binary_sensor.front_door
        to: "on"
    condition:
      - condition: state
        entity_id: binary_sensor.reachy_mini_backend_ready
        state: "on"
    action:
      # 点头
      - service: number.set_value
        target:
          entity_id: number.reachy_mini_head_pitch
        data:
          value: -20
      - delay: "00:00:01"
      - service: number.set_value
        target:
          entity_id: number.reachy_mini_head_pitch
        data:
          value: 0
      # 天线摆动
      - service: number.set_value
        target:
          entity_id:
            - number.reachy_mini_antenna_left
            - number.reachy_mini_antenna_right
        data:
          value: 45
      - delay: "00:00:01"
      - service: number.set_value
        target:
          entity_id:
            - number.reachy_mini_antenna_left
            - number.reachy_mini_antenna_right
        data:
          value: 0
```

### 示例 4: 根据后端状态显示通知

```yaml
automation:
  - alias: "Reachy Mini 错误通知"
    trigger:
      - platform: state
        entity_id: sensor.reachy_mini_daemon_state
        to: "error"
    action:
      - service: notify.mobile_app
        data:
          title: "Reachy Mini 错误"
          message: "{{ states('sensor.reachy_mini_error_message') }}"
```

### 示例 5: 创建自定义动作序列

```yaml
script:
  reachy_mini_dance:
    alias: "Reachy Mini 跳舞"
    sequence:
      # 启用电机
      - service: switch.turn_on
        target:
          entity_id: switch.reachy_mini_motors_enabled
      # 左右摇头
      - repeat:
          count: 3
          sequence:
            - service: number.set_value
              target:
                entity_id: number.reachy_mini_head_yaw
              data:
                value: 30
            - delay: "00:00:00.5"
            - service: number.set_value
              target:
                entity_id: number.reachy_mini_head_yaw
              data:
                value: -30
            - delay: "00:00:00.5"
      # 回到中心
      - service: number.set_value
        target:
          entity_id: number.reachy_mini_head_yaw
        data:
          value: 0
      # 天线摆动
      - service: number.set_value
        target:
          entity_id:
            - number.reachy_mini_antenna_left
            - number.reachy_mini_antenna_right
        data:
          value: 60
      - delay: "00:00:01"
      - service: number.set_value
        target:
          entity_id:
            - number.reachy_mini_antenna_left
            - number.reachy_mini_antenna_right
        data:
          value: 0
```

---

## Lovelace 仪表板示例

### 基础控制卡片

```yaml
type: vertical-stack
cards:
  - type: entities
    title: Reachy Mini 状态
    entities:
      - entity: sensor.reachy_mini_daemon_state
        name: Daemon 状态
      - entity: binary_sensor.reachy_mini_backend_ready
        name: 后端就绪
      - entity: sensor.reachy_mini_error_message
        name: 错误信息

  - type: entities
    title: 电机控制
    entities:
      - entity: switch.reachy_mini_motors_enabled
        name: 电机开关
      - entity: select.reachy_mini_motor_mode
        name: 电机模式
      - entity: button.reachy_mini_wake_up
        name: 唤醒
      - entity: button.reachy_mini_go_to_sleep
        name: 睡眠

  - type: entities
    title: 音量控制
    entities:
      - entity: number.reachy_mini_speaker_volume
        name: 扬声器音量
```

### 头部控制卡片

```yaml
type: vertical-stack
cards:
  - type: entities
    title: 头部位置 (mm)
    entities:
      - entity: number.reachy_mini_head_x
        name: X 轴
      - entity: number.reachy_mini_head_y
        name: Y 轴
      - entity: number.reachy_mini_head_z
        name: Z 轴

  - type: entities
    title: 头部角度 (°)
    entities:
      - entity: number.reachy_mini_head_roll
        name: 翻滚 (Roll)
      - entity: number.reachy_mini_head_pitch
        name: 俯仰 (Pitch)
      - entity: number.reachy_mini_head_yaw
        name: 偏航 (Yaw)

  - type: entities
    title: 身体与天线
    entities:
      - entity: number.reachy_mini_body_yaw
        name: 身体偏航
      - entity: number.reachy_mini_antenna_left
        name: 左天线
      - entity: number.reachy_mini_antenna_right
        name: 右天线
```

---

## 注意事项

1. **电机安全**: 在控制姿态之前，确保电机已启用 (`switch.reachy_mini_motors_enabled` 为 `on`)

2. **角度限制**: 所有角度控制都有安全限制，超出范围的值会被自动限制在有效范围内

3. **独立模式**: 如果机器人不可用（独立模式），控制命令不会产生错误，但也不会执行任何动作

4. **平滑运动**: 快速连续的控制命令可能导致不平滑的运动，建议在命令之间添加适当的延迟

5. **状态更新**: 实体状态会实时更新，但某些传感器可能有轻微延迟

---

## 故障排除

### 问题: 实体不显示在 Home Assistant 中
**解决方案**:
- 确认 Reachy Mini HA Voice 应用正在运行
- 检查 ESPHome 集成是否正确配置
- 重启 Home Assistant 或重新加载 ESPHome 集成

### 问题: 控制命令无响应
**解决方案**:
- 检查 `binary_sensor.reachy_mini_backend_ready` 是否为 `on`
- 查看 `sensor.reachy_mini_error_message` 是否有错误信息
- 确认电机已启用（对于运动控制）

### 问题: Daemon 状态显示 "error"
**解决方案**:
- 查看 `sensor.reachy_mini_error_message` 获取详细错误信息
- 检查 Reachy Mini 硬件连接
- 重启 Reachy Mini HA Voice 应用

---

## 更多信息

- [项目 GitHub](https://github.com/yourusername/reachy_mini_ha_voice)
- [Reachy Mini SDK 文档](https://github.com/pollen-robotics/reachy_mini)
- [Home Assistant ESPHome 集成](https://www.home-assistant.io/integrations/esphome/)
