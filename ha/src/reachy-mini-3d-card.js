// Reachy Mini 3D Card for Home Assistant
// 带有可视化配置编辑器的完整版本
// 支持 HACS 安装

(async () => {
  const MODULE_URL = new URL(import.meta.url);
  const BASE_URL = MODULE_URL.origin + MODULE_URL.pathname.replace(/\/[^/]*$/, '/');

  // 从 CDN 或本地加载 Three.js
  await loadScript('https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js');
  await loadScript('https://cdn.jsdelivr.net/npm/three@0.160.0/examples/js/controls/OrbitControls.js');
  await loadScript('https://cdn.jsdelivr.net/npm/three@0.160.0/examples/js/loaders/STLLoader.js');

  // LitElement 和 Home Assistant 帮助函数
  const { LitElement, html, css } = await loadLit();

  class ReachyMini3DCard extends LitElement {
    static get properties() {
      return {
        hass: Object,
        config: Object,
        _editing: { type: Boolean, state: true }
      };
    }

    static get styles() {
      return css`
        :host {
          display: block;
          width: 100%;
          position: relative;
        }
        ha-card {
          overflow: hidden;
          border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: var(--ha-card-box-shadow, none);
        }
        .card-container {
          width: 100%;
          position: relative;
        }
        #canvas-container {
          width: 100%;
          height: 400px;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          position: relative;
        }
        .status-overlay {
          position: absolute;
          top: 10px;
          left: 10px;
          background: rgba(0,0,0,0.6);
          color: white;
          padding: 8px 12px;
          border-radius: 8px;
          font-family: var(--font-family, Roboto);
          font-size: 12px;
          pointer-events: none;
        }
        .controls {
          position: absolute;
          bottom: 10px;
          right: 10px;
          display: flex;
          gap: 8px;
        }
        .control-btn {
          background: rgba(255,255,255,0.9);
          border: none;
          border-radius: 8px;
          padding: 8px 12px;
          cursor: pointer;
          font-size: 20px;
          transition: all 0.2s;
          box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        }
        .control-btn:hover {
          background: white;
          transform: translateY(-2px);
          box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }
        .control-btn:active {
          transform: translateY(0);
        }
        .edit-mode {
          position: absolute;
          top: 10px;
          right: 10px;
          z-index: 100;
        }
        .edit-btn {
          background: var(--primary-color, #03a9f4);
          color: white;
          border: none;
          border-radius: 50%;
          width: 40px;
          height: 40px;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 20px;
          box-shadow: 0 2px 8px rgba(0,0,0,0.3);
          transition: all 0.2s;
        }
        .edit-btn:hover {
          background: var(--primary-color, #0288d1);
          transform: scale(1.1);
        }
        .config-panel {
          position: absolute;
          top: 0;
          right: 0;
          width: 320px;
          height: 100%;
          background: white;
          box-shadow: -4px 0 16px rgba(0,0,0,0.1);
          border-radius: 12px 0 0 12px;
          padding: 20px;
          overflow-y: auto;
          z-index: 1000;
          transform: translateX(100%);
          transition: transform 0.3s ease;
        }
        .config-panel.open {
          transform: translateX(0);
        }
        .config-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 20px;
          padding-bottom: 10px;
          border-bottom: 2px solid #f0f0f0;
        }
        .config-header h3 {
          margin: 0;
          color: #333;
          font-size: 18px;
        }
        .close-btn {
          background: none;
          border: none;
          font-size: 24px;
          cursor: pointer;
          color: #666;
          padding: 0;
          width: 30px;
          height: 30px;
        }
        .close-btn:hover {
          color: #333;
        }
        .config-item {
          margin-bottom: 16px;
        }
        .config-item label {
          display: block;
          margin-bottom: 6px;
          font-size: 13px;
          color: #555;
          font-weight: 500;
        }
        .config-item input[type="text"],
        .config-item input[type="number"],
        .config-item select {
          width: 100%;
          padding: 8px 12px;
          border: 1px solid #ddd;
          border-radius: 6px;
          font-size: 14px;
          box-sizing: border-box;
          transition: border-color 0.2s;
        }
        .config-item input:focus,
        .config-item select:focus {
          outline: none;
          border-color: var(--primary-color, #03a9f4);
          box-shadow: 0 0 0 3px rgba(3, 169, 244, 0.1);
        }
        .config-item ha-switch {
          display: block;
        }
        .entity-selector {
          position: relative;
        }
        .entity-selector input {
          padding-right: 30px;
        }
        .entity-icon {
          position: absolute;
          right: 8px;
          top: 50%;
          transform: translateY(-50%);
          color: #999;
        }
        .preset-buttons {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 8px;
          margin-bottom: 16px;
        }
        .preset-btn {
          background: #f5f5f5;
          border: 1px solid #ddd;
          border-radius: 6px;
          padding: 8px 12px;
          cursor: pointer;
          font-size: 12px;
          transition: all 0.2s;
        }
        .preset-btn:hover {
          background: var(--primary-color, #03a9f4);
          color: white;
          border-color: var(--primary-color, #03a9f4);
        }
        .loading-overlay {
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(255,255,255,0.9);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 16px;
          color: #666;
          z-index: 50;
        }
      `;
    }

    static getStubConfig() {
      return {
        entity_prefix: 'reachy_mini',
        height: 400,
        show_controls: true,
        auto_rotate: false,
        xray_mode: false,
        wireframe: false
      };
    }

    setConfig(config) {
      if (!config.entity_prefix) {
        throw new Error('You need to define an entity prefix');
      }
      this.config = {
        ...ReachyMini3DCard.getStubConfig(),
        ...config
      };
    }

    getCardSize() {
      return Math.ceil(this.config.height / 50);
    }

    connectedCallback() {
      super.connectedCallback();
      this.initThreeJS();
    }

    disconnectedCallback() {
      super.disconnectedCallback();
      this.cleanup();
    }

    async initThreeJS() {
      const container = this.shadowRoot.getElementById('canvas-container');
      if (!container) return;

      // 场景
      this.scene = new THREE.Scene();
      this.scene.background = new THREE.Color(0xf0f0f0);

      // 相机
      const width = container.clientWidth;
      const height = this.config.height || 400;
      this.camera = new THREE.PerspectiveCamera(50, width / height, 0.01, 1000);
      this.camera.position.set(0.3, 0.3, 0.5);

      // 渲染器
      this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      this.renderer.setSize(width, height);
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      this.renderer.shadowMap.enabled = true;
      this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      container.appendChild(this.renderer.domElement);

      // 控制器
      this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
      this.controls.enableDamping = true;
      this.controls.dampingFactor = 0.05;
      this.controls.minDistance = 0.2;
      this.controls.maxDistance = 1;

      // 灯光
      const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
      this.scene.add(ambientLight);

      const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
      directionalLight.position.set(1, 1, 1);
      directionalLight.castShadow = true;
      this.scene.add(directionalLight);

      // 地面网格
      const gridHelper = new THREE.GridHelper(0.4, 20, 0x888888, 0xcccccc);
      this.scene.add(gridHelper);

      // 加载机器人模型
      await this.loadRobotModel();

      // 开始动画循环
      this.animate();

      // 监听窗口大小变化
      window.addEventListener('resize', this.onWindowResize.bind(this));

      // 启动状态更新
      this.startStateUpdate();
    }

    async loadRobotModel() {
      try {
        // 动态导入 urdf-loader
        const URDFLoader = (await import('/hacsfiles/reachy-mini-3d-card/lib/urdf-loader.js')).default;

        // HACS 安装后的路径结构：
        // /hacsfiles/reachy-mini-3d-card/reachy-mini-3d-card.js (当前文件)
        // /hacsfiles/reachy-mini-3d-card/assets/reachy-mini.urdf
        // /hacsfiles/reachy-mini-3d-card/assets/meshes/xxx.stl

        // 构造 URDF 文件路径
        const urdfPath = '/hacsfiles/reachy-mini-3d-card/assets/reachy-mini.urdf';

        // 创建 URDFLoader
        const loader = new URDFLoader();

        // 设置工作目录路径 (用于解析相对路径)
        loader.workingPath = '/hacsfiles/reachy-mini-3d-card/assets/';

        // 设置资源路径前缀
        loader.pathPrefix = (path) => {
          // URDF 中的路径是 "meshes/xxx.stl"
          // 转换为完整路径
          return '/hacsfiles/reachy-mini-3d-card/assets/' + path;
        };

        // 加载 URDF
        this.robot = await loader.load(urdfPath);

        // 将机器人添加到场景
        this.scene.add(this.robot);

        // 设置机器人初始位置
        this.robot.position.set(0, 0, 0);

        // 存储关节引用以便后续更新
        this.joints = this.robot.joints;

        console.log('Robot model loaded successfully:', this.robot);
        console.log('Available joints:', Object.keys(this.robot.joints));

      } catch (error) {
        console.error('Failed to load URDF model:', error);

        // 降级方案：显示错误信息
        const errorDiv = document.createElement('div');
        errorDiv.style.cssText = `
          position: absolute;
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          text-align: center;
          color: #f44336;
          padding: 20px;
          background: white;
          border-radius: 8px;
          box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        `;
        errorDiv.innerHTML = `
          <div style="font-size: 48px;">⚠️</div>
          <div style="font-size: 16px; margin-top: 10px;">
            <strong>模型加载失败</strong><br>
            <small style="color: #666;">${error.message}</small><br>
            <small style="color: #999; font-size: 11px;">请确保文件已正确安装到 HACS</small>
          </div>
        `;
        this.shadowRoot.getElementById('canvas-container').appendChild(errorDiv);
      }
    }

    startStateUpdate() {
      // 每 50ms 更新一次 (20Hz)
      this.updateInterval = setInterval(() => {
        if (this.hass && this.robot) {
          this.updateRobotState();
        }
      }, 50);
    }

    updateRobotState() {
      if (!this.robot || !this.robot.joints) return;

      const prefix = this.config.entity_prefix;

      // 从 Home Assistant 实体获取状态
      const getState = (entityType, entityName) => {
        const entityId = `${entityType}.${prefix}_${entityName}`;
        const state = this.hass.states[entityId];
        return state ? parseFloat(state.state) : 0;
      };

      // 获取关节数据 (从 JSON sensor)
      const headJointsState = this.hass.states[`sensor.${prefix}_head_joints`];
      const headPoseState = this.hass.states[`sensor.${prefix}_head_pose`];

      if (headJointsState && headJointsState.state !== 'unknown') {
        try {
          const headJoints = JSON.parse(headJointsState.state);

          // Stewart platform 关节 (参考 desktop app 的映射)
          this.robot.setJointValue('yaw_body', headJoints[0] || 0);
          this.robot.setJointValue('stewart_1', headJoints[1] || 0);
          this.robot.setJointValue('stewart_2', headJoints[2] || 0);
          this.robot.setJointValue('stewart_3', headJoints[3] || 0);
          this.robot.setJointValue('stewart_4', headJoints[4] || 0);
          this.robot.setJointValue('stewart_5', headJoints[5] || 0);
          this.robot.setJointValue('stewart_6', headJoints[6] || 0);

        } catch (e) {
          console.warn('Failed to parse head_joints:', e);
        }
      }

      // 获取天线角度
      const antennaLeft = getState('number', 'antenna_left');
      const antennaRight = getState('number', 'antenna_right');

      // 天线映射 (注意：角度可能需要反转，参考 desktop app)
      this.robot.setJointValue('left_antenna', -antennaLeft);
      this.robot.setJointValue('right_antenna', -antennaRight);
    }

    animate() {
      if (!this.renderer) return;

      requestAnimationFrame(this.animate.bind(this));

      if (this.controls) {
        this.controls.update();
      }

      if (this.config.auto_rotate && this.robot) {
        this.robot.rotation.y += 0.005;
      }

      if (this.renderer && this.scene && this.camera) {
        this.renderer.render(this.scene, this.camera);
      }
    }

    onWindowResize() {
      if (!this.camera || !this.renderer) return;

      const container = this.shadowRoot.getElementById('canvas-container');
      if (!container) return;

      const width = container.clientWidth;
      const height = this.config.height || 400;

      this.camera.aspect = width / height;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(width, height);
    }

    cleanup() {
      if (this.updateInterval) {
        clearInterval(this.updateInterval);
      }
      window.removeEventListener('resize', this.onWindowResize.bind(this));
      if (this.renderer) {
        this.renderer.dispose();
      }
    }

    showError(message) {
      const container = this.shadowRoot.getElementById('canvas-container');
      if (container) {
        container.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#f44336;font-size:14px;">${message}</div>`;
      }
    }

    // 配置相关方法
    toggleEditMode() {
      this._editing = !this._editing;
    }

    updateConfig(newConfig) {
      this.config = { ...this.config, ...newConfig };
      this.dispatchEvent(new CustomEvent('config-changed', {
        detail: { config: this.config },
        bubbles: true
      }));
    }

    render() {
      return html`
        <ha-card>
          <div class="card-container">
            ${this._editing ? html`
              <div class="config-panel open">
                <div class="config-header">
                  <h3>⚙️ Card Configuration</h3>
                  <button class="close-btn" @click="${() => this.toggleEditMode()}">×</button>
                </div>

                <div class="preset-buttons">
                  <button class="preset-btn" @click="${() => this.applyPreset('default')}">🏠 Default</button>
                  <button class="preset-btn" @click="${() => this.applyPreset('compact')}">📱 Compact</button>
                  <button class="preset-btn" @click="${() => this.applyPreset('detailed')}">📊 Detailed</button>
                  <button class="preset-btn" @click="${() => this.applyPreset('minimal')}">✨ Minimal</button>
                </div>

                <div class="config-item">
                  <label>Entity Prefix</label>
                  <div class="entity-selector">
                    <input type="text"
                           .value="${this.config.entity_prefix}"
                           @change="${(e) => this.updateConfig({ entity_prefix: e.target.value })}">
                    <span class="entity-icon">🔗</span>
                  </div>
                </div>

                <div class="config-item">
                  <label>Height (${this.config.height}px)</label>
                  <input type="range"
                         min="200"
                         max="800"
                         step="50"
                         .value="${this.config.height}"
                         @input="${(e) => this.updateConfig({ height: parseInt(e.target.value) })}">
                </div>

                <div class="config-item">
                  <label>Options</label>
                  <label style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
                    <input type="checkbox"
                           ?checked="${this.config.show_controls}"
                           @change="${(e) => this.updateConfig({ show_controls: e.target.checked })}">
                    Show Controls
                  </label>
                  <label style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
                    <input type="checkbox"
                           ?checked="${this.config.auto_rotate}"
                           @change="${(e) => this.updateConfig({ auto_rotate: e.target.checked })}">
                    Auto Rotate
                  </label>
                  <label style="display:flex;align-items:center;gap:8px;">
                    <input type="checkbox"
                           ?checked="${this.config.xray_mode}"
                           @change="${(e) => this.updateConfig({ xray_mode: e.target.checked })}">
                    X-Ray Mode
                  </label>
                </div>
              </div>
            ` : ''}

            <div id="canvas-container" style="height:${this.config.height}px"></div>

            ${this.config.show_controls ? html`
              <div class="controls">
                <button class="control-btn" @click="${() => this.resetCamera()}" title="Reset View">🎯</button>
                <button class="control-btn" @click="${() => this.toggleAutoRotate()}" title="Toggle Rotation">🔄</button>
              </div>
            ` : ''}

            <div class="edit-mode">
              <button class="edit-btn" @click="${() => this.toggleEditMode()}" title="Edit Configuration">⚙️</button>
            </div>
          </div>
        </ha-card>
      `;
    }

    resetCamera() {
      if (this.camera && this.controls) {
        this.camera.position.set(0.3, 0.3, 0.5);
        this.controls.reset();
      }
    }

    toggleAutoRotate() {
      this.updateConfig({ auto_rotate: !this.config.auto_rotate });
    }

    applyPreset(preset) {
      const presets = {
        default: { height: 400, show_controls: true, auto_rotate: false },
        compact: { height: 300, show_controls: false, auto_rotate: true },
        detailed: { height: 600, show_controls: true, auto_rotate: false, xray_mode: true },
        minimal: { height: 250, show_controls: false, auto_rotate: false }
      };
      this.updateConfig(presets[preset] || presets.default);
    }
  }

  // 注册自定义卡片
  customElements.define('reachy-mini-3d-card', ReachyMini3DCard);

  // 配置编辑器
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: 'reachy-mini-3d-card',
    name: 'Reachy Mini 3D Card',
    description: 'Real-time 3D visualization of Reachy Mini robot with visual configuration editor',
    preview: true,
    documentationURL: 'https://github.com/djhui5710/reachy_mini_ha_voice'
  });

  // 辅助函数
  async function loadScript(url) {
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = url;
      script.onload = resolve;
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }

  async function loadLit() {
    if (window.LitElement) {
      return { LitElement: window.LitElement, html: window.html, css: window.css };
    }
    await loadScript('https://cdn.jsdelivr.net/npm/lit@3.1.0/index.js');
    await loadScript('https://cdn.jsdelivr.net/npm/lit@3.1.0/decorators.js');
    await loadScript('https://cdn.jsdelivr.net/npm/lit@3.1.0/polyfill-support.js');

    // Lit 需要 polyfill
    await loadScript('https://cdn.jsdelivr.net/npm/@lit/reactive-element@1.6.0/reactive-element.js');
    await loadScript('https://cdn.jsdelivr.net/npm/lit@3.1.0/lit-element.js');

    return {
      LitElement: window.LitElement || window.LitElementElement,
      html: window.html || ((strings, ...values) => ({ strings, values })),
      css: window.css || ((strings, ...values) => strings.join(''))
    };
  }
})();
