# Reachy Mini 3D Card for Home Assistant

<div align="center">

[![HACS](https://img.shields.io/badge/HACS-Default-orange.svg)](https://hacs.xyz/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

**🤖 Real-time 3D visualization with visual configuration**

No YAML editing required! Everything configurable through the UI.

</div>

## ✨ Features

- **Real-time 3D Visualization** - See your robot's exact pose at 20Hz
- **Visual Configuration Editor** - Click ⚙️ to configure, no YAML needed
- **URDF-based Rendering** - Accurate 3D models using Three.js
- **Interactive Controls** - Rotate, zoom, pan with mouse/touch
- **Auto-discovery** - Automatically finds ESPHome entities
- **Multiple Presets** - Default, Compact, Hidden, Panoramic

## 📦 Installation

### Prerequisites

- Home Assistant 2023.11.0 or later
- HACS installed
- Reachy Mini robot with ESPHome entities configured

### Step 1: Install via HACS

1. Open Home Assistant → **HACS** → **Frontend**
2. Click **Explore & Download Repositories**
3. Search for `Reachy Mini 3D Card`
4. Click **Download** → select latest version
5. Wait for installation to complete

### Step 2: Add to Resources

1. Go to **Settings** → **Dashboard** → **Resources**
2. Click **Add Resource**
3. Search and select `Reachy Mini 3D Card`
4. Click **Add Resource**
5. Refresh your browser (Ctrl+Shift+R)

### Step 3: Add to Dashboard

1. Edit your dashboard (click **...** → **Edit dashboard**)
2. Click **Add Card** (+ button)
3. Search for `Reachy Mini 3D Card`
4. Click to add it
5. Configure using visual editor (click ⚙️)
6. Click **Save**

## ⚙️ Configuration

### Visual Editor (Recommended)

Click the **⚙️** icon in the card's top-right corner:

- **Entity Prefix**: Your ESPHome entity prefix (e.g., `reachy_mini`)
- **Height**: Card height in pixels (200-800px)
- **Show Controls**: Enable mouse/touch controls
- **Auto Rotate**: Automatically rotate the view
- **X-Ray Mode**: Show wireframe overlay
- **Wireframe**: Display as wireframe only

### Quick Presets

Click preset buttons in the visual editor:

| Preset | Height | Best For |
|--------|--------|----------|
| 🏠 Default | 400px | Standard dashboard |
| 📱 Compact | 250px | Mobile/sidebar |
| 👁️ Hidden | 300px | Background monitoring |
| 🌐 Panoramic | 600px | Large displays |

### YAML Configuration

If you prefer YAML:

```yaml
type: custom:reachy-mini-3d-card
entity_prefix: reachy_mini  # Required
height: 400                  # Optional: 200-800
show_controls: true         # Optional: default true
auto_rotate: false          # Optional: default false
xray_mode: false            # Optional: default false
wireframe: false            # Optional: default false
```

## 🎮 Usage

### View Controls

- **Rotate**: Left-click and drag
- **Zoom**: Mouse wheel or pinch gesture
- **Pan**: Right-click and drag (or two-finger drag)

### Required ESPHome Entities

The card automatically looks for these entities:

```
sensor.{prefix}_head_joints    # JSON array of joint angles
sensor.{prefix}_head_pose      # JSON array of pose data
number.{prefix}_antenna_left   # Left antenna angle
number.{prefix}_antenna_right  # Right antenna angle
```

Example with prefix `reachy_mini`:
- `sensor.reachy_mini_head_joints`
- `sensor.reachy_mini_head_pose`
- `number.reachy_mini_antenna_left`
- `number.reachy_mini_antenna_right`

## 🔧 Troubleshooting

### Card shows "Model loading failed"

1. Check browser console (F12) for specific errors
2. Verify all files are installed in `/hacsfiles/reachy-mini-3d-card/`
3. Ensure ESPHome entities are available in HA
4. Try clearing browser cache and hard refresh (Ctrl+Shift+R)

### Robot not moving

1. Verify entity prefix is correct
2. Check that ESPHome entities are updating in Developer Tools → States
3. Ensure Reachy Mini daemon is running
4. Check 20Hz data stream is active

### Performance issues

- Reduce card height
- Disable X-Ray mode
- Close other browser tabs
- Use wired Ethernet connection

## 📂 Project Structure

```
reachy-mini-3d-card/
├── reachy-mini-3d-card.js    # Compiled card code
├── assets/
│   ├── reachy-mini.urdf      # Robot kinematic definition
│   └── meshes/               # 45 STL 3D model files
├── hacs.json                 # HACS metadata
├── README.md                 # This file
├── CHANGELOG.md              # Version history
└── LICENSE                   # Apache 2.0
```

## 🛠️ Development

```bash
# Clone repository
git clone https://github.com/djhui5710/reachy-mini-3d-card.git
cd reachy-mini-3d-card

# Install dependencies
npm install

# Build
npm run build

# Watch mode
npm run watch
```

## 📝 License

Apache License 2.0 - see [LICENSE](LICENSE) for details

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/djhui5710/reachy-mini-3d-card/issues)
- **Discussions**: [GitHub Discussions](https://github.com/djhui5710/reachy-mini-3d-card/discussions)

## 🔗 Related Projects

- **Parent Project**: [reachy_mini_ha_voice](https://github.com/djhui5710/reachy_mini_ha_voice)
- **Robot Manufacturer**: [Pollen Robotics](https://www.pollen-robotics.com/)
- **Desktop App**: [reachy-mini-desktop-app](https://github.com/djhui5710/reachy_mini_ha_voice/tree/main/reachy-mini-desktop-app)

---

<div align="center">

**Made with ❤️ for the Reachy Mini community**

</div>
