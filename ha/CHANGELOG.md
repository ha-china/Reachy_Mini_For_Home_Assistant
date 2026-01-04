# Changelog - Reachy Mini 3D Card

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- Multiple robot URDF support
- Custom color themes
- Recording/playback of poses
- Export 3D model as GLTF
- VR mode support

## [1.0.0] - 2025-01-04

### Added
- ✨ Initial release of Reachy Mini 3D Card
- 🎨 Visual configuration editor (click ⚙️)
- 📊 Real-time 3D visualization of robot pose
- 🎮 Interactive camera controls (rotate, zoom, pan)
- 📱 Live status overlay with joint angles
- 🔄 Auto-rotation mode
- 🎭 X-Ray transparency mode
- 📐 Wireframe display mode
- 🎯 Four configuration presets (Default, Compact, Detailed, Minimal)
- 🏷️ Full HACS integration support
- 📦 Automated build and release pipeline
- 📖 Comprehensive documentation and examples
- 🔌 ESPHome entity auto-discovery
- ⚙️ No YAML editing required - everything through UI

### Technical Details
- Three.js 0.160.0 for 3D rendering
- Lit 3.1.0 for web components
- Real-time 20Hz update rate
- Support for multiple robots on single dashboard
- Automatic asset loading from `/local/reachy-mini-assets/`

### Required Entities
- `number.{prefix}_body_yaw`
- `number.{prefix}_head_pitch`
- `number.{prefix}_head_roll`
- `number.{prefix}_head_yaw`
- `number.{prefix}_antenna_left`
- `number.{prefix}_antenna_right`

### Documentation
- README.md with full feature list
- QUICKSTART.md for 5-minute setup guide
- example-dashboard.yaml with sample configurations
- hacs.json for HACS repository integration

---

## Version Format

Each version entry should include:
- **Version number** (e.g., [1.0.0])
- **Release date** (YYYY-MM-DD)
- **Sections**:
  - `Added` - New features
  - `Changed` - Changes to existing functionality
  - `Deprecated` - Soon-to-be removed features
  - `Removed` - Removed features
  - `Fixed` - Bug fixes
  - `Security` - Security vulnerability fixes

---

## Links

- [Current Repository](https://github.com/djhui5710/reachy_mini_ha_voice)
- [HACS Repository](https://hacs.xyz/)
- [Issue Tracker](https://github.com/djhui5710/reachy_mini_ha_voice/issues)
