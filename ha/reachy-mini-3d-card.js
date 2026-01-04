/**
 * Reachy Mini 3D Status Card for Home Assistant
 *
 * This custom card displays a real-time 3D model of Reachy Mini
 * that syncs with ESPHome entity states from the reachy_mini_ha_voice project.
 *
 * Installation:
 * 1. Copy this file to your Home Assistant config/www/ folder
 * 2. Add to resources in configuration.yaml or via UI:
 *    url: /local/reachy-mini-3d-card.js
 *    type: module
 * 3. Add the card to your dashboard
 *
 * Card Configuration:
 * type: custom:reachy-mini-3d-card
 * entity_prefix: reachy_mini  # Optional, defaults to 'reachy_mini'
 * height: 400                  # Optional, card height in pixels
 * show_controls: true          # Optional, show camera controls
 * auto_rotate: false           # Optional, auto-rotate the model
 */

const CARD_VERSION = '1.5.3';

// Three.js and URDFLoader using esm.sh CDN
const loadThreeJS = (() => {
  let loadPromise = null;

  return () => {
    if (loadPromise) return loadPromise;

    // Check if already loaded
    if (window.THREE && window.THREE.OrbitControls && window.THREE.STLLoader) {
      return Promise.resolve(window.THREE);
    }

    loadPromise = (async () => {
      try {
        // Use esm.sh which automatically resolves bare module specifiers
        const threeModule = await import('https://esm.sh/three@0.160.0');
        const { OrbitControls } = await import('https://esm.sh/three@0.160.0/examples/jsm/controls/OrbitControls.js');
        const { STLLoader } = await import('https://esm.sh/three@0.160.0/examples/jsm/loaders/STLLoader.js');

        // Try to load URDFLoader with proper Three.js external reference
        let URDFLoader = null;
        try {
          const urdfModule = await import('https://esm.sh/urdf-loader@0.12.2?external=three@0.160.0');
          URDFLoader = urdfModule.default || urdfModule.URDFLoader;
          console.log('URDFLoader loaded successfully');
        } catch (e) {
          console.warn('URDFLoader not available, using fallback loader:', e);
        }

        // Create a wrapper object
        const THREE = Object.assign({}, threeModule, {
          OrbitControls,
          STLLoader,
          URDFLoader
        });

        // Also expose globally for other components
        window.THREE = THREE;

        return THREE;
      } catch (error) {
        console.error('Failed to load Three.js modules:', error);
        throw error;
      }
    })();

    return loadPromise;
  };
})();

class ReachyMini3DCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._hass = null;
    this._config = null;
    this._scene = null;
    this._camera = null;
    this._renderer = null;
    this._controls = null;
    this._robot = null;
    this._animationId = null;
    this._initialized = false;
    this._THREE = null;
  }

  static get properties() {
    return {
      hass: {},
      config: {},
    };
  }

  set hass(hass) {
    this._hass = hass;
    if (this._initialized) {
      this._updateRobotState();
    }
  }

  setConfig(config) {
    this._config = {
      entity_prefix: 'reachy_mini',
      height: 400,
      show_controls: true,
      auto_rotate: false,
      assets_path: '/local/reachy-mini-assets/',
      ...config,
    };

    this._render();
    this._initThreeJS();
  }

  getCardSize() {
    return Math.ceil(this._config.height / 50);
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
        }
        .card {
          background: var(--ha-card-background, var(--card-background-color, #1a1a2e));
          border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: var(--ha-card-box-shadow, none);
          overflow: hidden;
          position: relative;
        }
        .canvas-container {
          width: 100%;
          height: ${this._config.height}px;
          position: relative;
        }
        .canvas-container canvas {
          width: 100% !important;
          height: 100% !important;
        }
        .status-overlay {
          position: absolute;
          top: 12px;
          left: 12px;
          background: rgba(0, 0, 0, 0.7);
          backdrop-filter: blur(10px);
          border-radius: 8px;
          padding: 10px 14px;
          color: #fff;
          font-size: 12px;
          z-index: 10;
        }
        .status-header {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 8px;
          font-weight: 600;
          font-size: 14px;
        }
        .status-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: #22c55e;
        }
        .status-dot.offline { background: #ef4444; }
        .status-dot.busy { background: #f59e0b; animation: pulse 1.5s infinite; }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
        .status-row {
          display: flex;
          justify-content: space-between;
          margin-bottom: 4px;
          font-size: 11px;
        }
        .status-label { color: #888; }
        .status-value {
          color: #FF9500;
          font-family: monospace;
          font-weight: 600;
        }
        .controls {
          position: absolute;
          top: 12px;
          right: 12px;
          display: flex;
          flex-direction: column;
          gap: 6px;
          z-index: 10;
        }
        .control-btn {
          width: 32px;
          height: 32px;
          border-radius: 8px;
          border: 1px solid rgba(255, 255, 255, 0.2);
          background: rgba(0, 0, 0, 0.5);
          color: #888;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 14px;
          transition: all 0.2s;
        }
        .control-btn:hover {
          background: rgba(255, 149, 0, 0.3);
          color: #FF9500;
        }
        .control-btn.active {
          background: rgba(255, 149, 0, 0.4);
          color: #FF9500;
        }
        .loading {
          position: absolute;
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          color: #666;
          font-size: 14px;
          text-align: center;
        }
        .loading-spinner {
          width: 32px;
          height: 32px;
          border: 3px solid rgba(255, 149, 0, 0.2);
          border-top-color: #FF9500;
          border-radius: 50%;
          animation: spin 1s linear infinite;
          margin: 0 auto 12px;
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      </style>
      <ha-card>
        <div class="card">
          <div class="canvas-container" id="canvas-container">
            <div class="loading" id="loading">
              <div class="loading-spinner"></div>
              <div>Loading Reachy Mini...</div>
            </div>
          </div>
          <div class="status-overlay" id="status-overlay">
            <div class="status-header">
              <div class="status-dot" id="status-dot"></div>
              <span id="status-title">Reachy Mini</span>
            </div>
          </div>
          ${this._config.show_controls ? `
          <div class="controls">
            <button class="control-btn" id="btn-reset" title="Reset View">↺</button>
            <button class="control-btn" id="btn-auto" title="Auto Rotate">⟳</button>
          </div>
          ` : ''}
        </div>
      </ha-card>
    `;
  }

  async _initThreeJS() {
    try {
      // Wait for container to be ready
      await new Promise(resolve => setTimeout(resolve, 100));

      // Load Three.js
      this._THREE = await loadThreeJS();

      this._setupScene();
      await this._loadRobot();
      this._setupControls();
      this._animate();
      this._initialized = true;

      if (this._hass) {
        this._updateRobotState();
      }
    } catch (error) {
      console.error('Failed to initialize Three.js:', error);
      const loading = this.shadowRoot.getElementById('loading');
      if (loading) {
        loading.innerHTML = `<div style="color: #ef4444;">Failed to load 3D viewer: ${error.message}</div>`;
      }
    }
  }

  _setupScene() {
    const THREE = this._THREE;
    const container = this.shadowRoot.getElementById('canvas-container');
    const width = container.clientWidth || 400;
    const height = this._config.height;

    // Scene
    this._scene = new THREE.Scene();
    this._scene.background = new THREE.Color(0x1a1a2e);

    // Camera
    this._camera = new THREE.PerspectiveCamera(50, width / height, 0.01, 10);
    this._camera.position.set(0, 0.25, 0.52);

    // Renderer
    this._renderer = new THREE.WebGLRenderer({ antialias: true });
    this._renderer.setSize(width, height);
    this._renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this._renderer.toneMapping = THREE.ACESFilmicToneMapping;
    container.appendChild(this._renderer.domElement);

    // Orbit Controls
    this._controls = new THREE.OrbitControls(this._camera, this._renderer.domElement);
    this._controls.target.set(0, 0.2, 0);
    this._controls.enableDamping = true;
    this._controls.dampingFactor = 0.05;
    this._controls.minDistance = 0.2;
    this._controls.maxDistance = 0.8;
    this._controls.autoRotate = this._config.auto_rotate;
    this._controls.update();

    // Lights
    const ambient = new THREE.AmbientLight(0xffffff, 0.4);
    this._scene.add(ambient);

    const keyLight = new THREE.DirectionalLight(0xffffff, 0.8);
    keyLight.position.set(5, 5, 5);
    this._scene.add(keyLight);

    const fillLight = new THREE.DirectionalLight(0xffffff, 0.3);
    fillLight.position.set(-5, 3, -5);
    this._scene.add(fillLight);

    // Grid
    const gridHelper = new THREE.GridHelper(1, 20, 0x444444, 0x333333);
    this._scene.add(gridHelper);

    // Handle resize
    const resizeObserver = new ResizeObserver(() => {
      const w = container.clientWidth;
      const h = this._config.height;
      if (w > 0 && this._camera && this._renderer) {
        this._camera.aspect = w / h;
        this._camera.updateProjectionMatrix();
        this._renderer.setSize(w, h);
      }
    });
    resizeObserver.observe(container);
  }

  async _loadRobot() {
    const THREE = this._THREE;
    const assetsPath = this._config.assets_path;
    const urdfPath = assetsPath + 'reachy-mini.urdf';

    // Check if URDFLoader is available and properly loaded
    if (THREE.URDFLoader && typeof THREE.URDFLoader === 'function') {
      try {
        console.log('Loading robot with URDFLoader...');
        await this._loadRobotWithURDF();
        return;
      } catch (error) {
        console.error('URDFLoader failed, falling back to STL loader:', error);
        // Continue to fallback
      }
    } else {
      console.warn('URDFLoader not available, using fallback STL loader');
    }

    // Fallback to STL loading
    console.log('Loading robot with STL fallback...');
    await this._loadRobotFallback();
  }

  async _loadRobotWithURDF() {
    const THREE = this._THREE;
    const assetsPath = this._config.assets_path;
    const urdfPath = assetsPath + 'reachy-mini.urdf';

    // Fetch and parse URDF file
    const response = await fetch(urdfPath);
    if (!response.ok) {
      throw new Error(`Failed to fetch URDF: ${response.status}`);
    }
    const urdfText = await response.text();

    const loader = new THREE.URDFLoader();

    // Configure the loader to load STL meshes from local assets
    loader.packages = { '': assetsPath };

    // Configure mesh loading callback
    loader.loadMeshCb = (path, manager, onComplete) => {
      const stlLoader = new THREE.STLLoader(manager);
      const fullPath = assetsPath + path; // Use full path including 'meshes/' subdirectory
      console.log('Loading mesh:', fullPath);

      // Use fetch to load the STL file as ArrayBuffer, then parse with STLLoader
      fetch(fullPath)
        .then(response => {
          if (!response.ok) {
            throw new Error(`Failed to fetch ${fullPath}: ${response.status}`);
          }
          return response.arrayBuffer();
        })
        .then(buffer => {
          const geometry = stlLoader.parse(buffer);
          const material = new THREE.MeshStandardMaterial({
            color: 0xcccccc,
            metalness: 0.1,
            roughness: 0.7,
          });
          const mesh = new THREE.Mesh(geometry, material);
          onComplete(mesh);
        })
        .catch(err => {
          console.warn(`Failed to load mesh: ${fullPath}`, err);
          onComplete(null);
        });
    };

    // Parse the URDF
    const robot = loader.parse(urdfText);
    if (!robot) {
      throw new Error('Failed to parse URDF');
    }

    this._robot = robot;

    // Apply materials based on URDF colors
    this._robot.traverse((child) => {
      if (child.isMesh) {
        const material = new THREE.MeshStandardMaterial({
          color: child.material?.color || 0xcccccc,
          metalness: 0.1,
          roughness: 0.7,
        });
        child.material = material;
      }
    });

    // Position and rotate the robot correctly
    // URDF coordinates: Z-up, Three.js: Y-up
    // Rotate -90° around X-axis to make the robot stand upright
    this._robot.rotation.set(-Math.PI / 2, 0, 0);
    this._scene.add(this._robot);

    // Initialize all joints to zero
    if (this._robot.joints) {
      Object.keys(this._robot.joints).forEach(jointName => {
        if (this._robot.joints[jointName]) {
          this._robot.setJointValue(jointName, 0);
        }
      });
    }

    // Hide loading
    const loading = this.shadowRoot.getElementById('loading');
    if (loading) loading.style.display = 'none';

    console.info('Reachy Mini 3D model loaded successfully with URDFLoader');
  }

  // Fallback method using simple STL loading (original implementation)
  async _loadRobotFallback() {
    const THREE = this._THREE;
    const assetsPath = this._config.assets_path;
    const urdfPath = assetsPath + 'reachy-mini.urdf';

    try {
      const response = await fetch(urdfPath);
      if (!response.ok) {
        throw new Error(`Failed to load URDF: ${response.status}`);
      }
      const urdfText = await response.text();
      const parser = new DOMParser();
      const urdfDoc = parser.parseFromString(urdfText, 'text/xml');

      this._robot = new THREE.Group();

      const links = urdfDoc.querySelectorAll('link');
      const stlLoader = new THREE.STLLoader();
      const loadPromises = [];

      links.forEach(link => {
        const linkName = link.getAttribute('name');
        const visuals = link.querySelectorAll('visual');

        visuals.forEach(visual => {
          const meshElement = visual.querySelector('mesh');
          if (meshElement) {
            const filename = meshElement.getAttribute('filename');
            const meshPath = assetsPath + filename;

            const origin = visual.querySelector('origin');
            let position = [0, 0, 0];
            let rotation = [0, 0, 0];

            if (origin) {
              const xyz = origin.getAttribute('xyz');
              const rpy = origin.getAttribute('rpy');
              if (xyz) position = xyz.split(' ').map(Number);
              if (rpy) rotation = rpy.split(' ').map(Number);
            }

            const material = visual.querySelector('material');
            let color = 0xcccccc;
            if (material) {
              const colorElement = material.querySelector('color');
              if (colorElement) {
                const rgba = colorElement.getAttribute('rgba').split(' ').map(Number);
                color = new THREE.Color(rgba[0], rgba[1], rgba[2]);
              }
            }

            const loadPromise = new Promise((resolve) => {
              console.log('Loading mesh (fallback):', meshPath);

              // Use fetch to load the STL file as ArrayBuffer, then parse with STLLoader
              fetch(meshPath)
                .then(response => {
                  if (!response.ok) {
                    throw new Error(`Failed to fetch ${meshPath}: ${response.status}`);
                  }
                  return response.arrayBuffer();
                })
                .then(buffer => {
                  const geometry = stlLoader.parse(buffer);
                  const mat = new THREE.MeshStandardMaterial({
                    color: color,
                    metalness: 0.1,
                    roughness: 0.7,
                  });
                  const mesh = new THREE.Mesh(geometry, mat);
                  mesh.position.set(position[0], position[1], position[2]);
                  mesh.rotation.set(rotation[0], rotation[1], rotation[2]);
                  mesh.name = linkName;
                  this._robot.add(mesh);
                  resolve();
                })
                .catch(err => {
                  console.warn(`Failed to load mesh: ${meshPath}`, err);
                  resolve();
                });
            });

            loadPromises.push(loadPromise);
          }
        });
      });

      await Promise.all(loadPromises);

      this._robot.position.set(0, 0, 0);
      this._robot.rotation.set(0, -Math.PI / 2, 0);
      this._scene.add(this._robot);

      // Hide loading
      const loading = this.shadowRoot.getElementById('loading');
      if (loading) loading.style.display = 'none';

      console.info('Reachy Mini 3D model loaded with fallback STL loader');

    } catch (error) {
      console.error('Error loading robot:', error);
      const loading = this.shadowRoot.getElementById('loading');
      if (loading) {
        loading.innerHTML = `<div style="color: #ef4444;">Error: ${error.message}</div>`;
      }
    }
  }

  _setupControls() {
    const btnReset = this.shadowRoot.getElementById('btn-reset');
    const btnAuto = this.shadowRoot.getElementById('btn-auto');

    if (btnReset) {
      btnReset.addEventListener('click', () => {
        this._camera.position.set(0, 0.25, 0.52);
        this._controls.target.set(0, 0.2, 0);
        this._controls.update();
      });
    }

    if (btnAuto) {
      btnAuto.addEventListener('click', () => {
        this._controls.autoRotate = !this._controls.autoRotate;
        btnAuto.classList.toggle('active', this._controls.autoRotate);
      });
    }
  }

  _animate() {
    this._animationId = requestAnimationFrame(() => this._animate());
    if (this._controls) this._controls.update();
    if (this._renderer && this._scene && this._camera) {
      this._renderer.render(this._scene, this._camera);
    }
  }

  _getEntityState(suffix) {
    if (!this._hass) return null;
    const entityId = `number.${this._config.entity_prefix}_${suffix}`;
    return this._hass.states[entityId];
  }

  _getSwitchState(suffix) {
    if (!this._hass) return null;
    const entityId = `switch.${this._config.entity_prefix}_${suffix}`;
    return this._hass.states[entityId];
  }

  _getSensorState(suffix) {
    if (!this._hass) return null;
    const entityId = `sensor.${this._config.entity_prefix}_${suffix}`;
    return this._hass.states[entityId];
  }

  _getBinarySensorState(suffix) {
    if (!this._hass) return null;
    const entityId = `binary_sensor.${this._config.entity_prefix}_${suffix}`;
    return this._hass.states[entityId];
  }

  _getTextSensorState(suffix) {
    if (!this._hass) return null;
    const entityId = `sensor.${this._config.entity_prefix}_${suffix}`;
    return this._hass.states[entityId];
  }

  _updateRobotState() {
    // Get states from Home Assistant
    const bodyYaw = this._getEntityState('body_yaw');
    const headPitch = this._getEntityState('head_pitch');
    const headRoll = this._getEntityState('head_roll');
    const headYaw = this._getEntityState('head_yaw');
    const antennaLeft = this._getEntityState('antenna_left');
    const antennaRight = this._getEntityState('antenna_right');
    const motorsEnabled = this._getSwitchState('motors_enabled');
    const daemonState = this._getSensorState('daemon_state');
    const backendReady = this._getBinarySensorState('backend_ready');

    // Get head joints as JSON array (Phase 13: single sensor)
    const headJointsEntity = this._getTextSensorState('head_joints');
    let headJoints = null;
    if (headJointsEntity && headJointsEntity.state) {
      try {
        headJoints = JSON.parse(headJointsEntity.state);
      } catch (e) {
        console.warn('Failed to parse head_joints JSON:', e);
      }
    }

    // Get passive joints as JSON array (Phase 14: single sensor)
    const passiveJointsEntity = this._getTextSensorState('passive_joints');
    let passiveJoints = null;
    if (passiveJointsEntity && passiveJointsEntity.state) {
      try {
        passiveJoints = JSON.parse(passiveJointsEntity.state);
      } catch (e) {
        console.warn('Failed to parse passive_joints JSON:', e);
      }
    }

    // Debug: Log available joints
    if (this._robot && this._robot.joints) {
      console.log('Available joints in robot model:', Object.keys(this._robot.joints));
    }

    // Update 3D model using joint system if available (URDFLoader)
    if (this._robot && this._robot.joints) {
      // Update all joints from head_joints array
      if (headJoints && Array.isArray(headJoints) && headJoints.length >= 7) {
        // headJoints = [yaw_body, stewart_1, ..., stewart_6]
        // All values are already in radians
        console.log('Updating robot joints:', headJoints);
        const jointNames = ['yaw_body', 'stewart_1', 'stewart_2', 'stewart_3', 'stewart_4', 'stewart_5', 'stewart_6'];

        for (let i = 0; i < 7; i++) {
          const jointName = jointNames[i];
          if (this._robot.joints[jointName]) {
            this._robot.setJointValue(jointName, headJoints[i]);
            console.log(`Set ${jointName} = ${headJoints[i]}`);
          } else {
            console.warn(`Joint ${jointName} not found in robot model`);
          }
        }

        // Update passive joints (Phase 14)
        if (passiveJoints && Array.isArray(passiveJoints) && passiveJoints.length >= 21) {
          console.log('Updating passive joints:', passiveJoints);
          const passiveJointNames = [
            'passive_1_x', 'passive_1_y', 'passive_1_z',
            'passive_2_x', 'passive_2_y', 'passive_2_z',
            'passive_3_x', 'passive_3_y', 'passive_3_z',
            'passive_4_x', 'passive_4_y', 'passive_4_z',
            'passive_5_x', 'passive_5_y', 'passive_5_z',
            'passive_6_x', 'passive_6_y', 'passive_6_z',
            'passive_7_x', 'passive_7_y', 'passive_7_z',
          ];

          for (let i = 0; i < 21; i++) {
            const jointName = passiveJointNames[i];
            if (this._robot.joints[jointName]) {
              this._robot.setJointValue(jointName, passiveJoints[i]);
              console.log(`Set ${jointName} = ${passiveJoints[i]}`);
            } else {
              console.warn(`Joint ${jointName} not found in robot model`);
            }
          }
        }
      } else {
        console.warn('head_joints data not available or invalid:', headJoints);
        // Fallback: use individual body_yaw entity
        if (bodyYaw && this._robot.joints['yaw_body']) {
          const yawRad = parseFloat(bodyYaw.state) * Math.PI / 180;
          this._robot.setJointValue('yaw_body', yawRad);
        }
      }

      // Update antennas - mapping matches desktop-app implementation
      if (antennaLeft && this._robot.joints['left_antenna']) {
        this._robot.setJointValue('left_antenna', -parseFloat(antennaLeft.state) * Math.PI / 180);
      }
      if (antennaRight && this._robot.joints['right_antenna']) {
        this._robot.setJointValue('right_antenna', -parseFloat(antennaRight.state) * Math.PI / 180);
      }

    } else if (this._robot) {
      // Fallback: simple rotation for non-URDF loaded robot
      if (bodyYaw) {
        const yawRad = parseFloat(bodyYaw.state) * Math.PI / 180;
        this._robot.rotation.y = -Math.PI / 2 + yawRad;
      }
    }

    // Update UI - only show status
    const statusDot = this.shadowRoot.getElementById('status-dot');
    const statusTitle = this.shadowRoot.getElementById('status-title');

    // Update status indicator
    if (statusDot && statusTitle) {
      if (backendReady && backendReady.state === 'on') {
        statusDot.className = 'status-dot';
        statusTitle.textContent = daemonState ? `Reachy - ${daemonState.state}` : 'Reachy Mini';
      } else {
        statusDot.className = 'status-dot offline';
        statusTitle.textContent = 'Offline';
      }
    }
  }

  disconnectedCallback() {
    if (this._animationId) {
      cancelAnimationFrame(this._animationId);
    }
    if (this._renderer) {
      this._renderer.dispose();
    }
  }
}

// Register the card
customElements.define('reachy-mini-3d-card', ReachyMini3DCard);

// Register with Home Assistant
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'reachy-mini-3d-card',
  name: 'Reachy Mini 3D Card',
  description: 'A 3D visualization card for Reachy Mini robot status',
  preview: true,
});

console.info(`%c REACHY-MINI-3D-CARD %c v${CARD_VERSION} `,
  'color: white; background: #FF9500; font-weight: bold;',
  'color: #FF9500; background: white; font-weight: bold;'
);
