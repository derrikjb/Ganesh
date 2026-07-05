import type { VisualizerPlugin, RenderParams } from '../types';
import * as THREE from 'three';

const colors = {
  bgPrimary: '#0a0a0a',
  accent: '#3b82f6',
  accentMuted: 'rgba(59, 130, 246, 0.3)',
};

interface HoloFaceState {
  renderer: THREE.WebGLRenderer | null;
  scene: THREE.Scene | null;
  camera: THREE.PerspectiveCamera | null;
  mesh: THREE.Mesh | null;
  originalPositions: Float32Array | null;
  particles: THREE.Points | null;
}

const state: HoloFaceState = {
  renderer: null,
  scene: null,
  camera: null,
  mesh: null,
  originalPositions: null,
  particles: null,
};

export const HoloFaceVisualizer: VisualizerPlugin = {
  name: 'Holo Face',

  init(ctx: CanvasRenderingContext2D) {
    const canvas = ctx.canvas;

    state.scene = new THREE.Scene();
    state.camera = new THREE.PerspectiveCamera(
      50,
      canvas.width / canvas.height,
      0.1,
      100
    );
    state.camera.position.z = 3;

    state.renderer = new THREE.WebGLRenderer({
      canvas,
      alpha: true,
      antialias: true,
    });
    state.renderer.setClearColor(0x0a0a0a, 1);

    const geometry = new THREE.IcosahedronGeometry(1, 2);
    state.originalPositions = new Float32Array(geometry.attributes.position.array);

    const material = new THREE.MeshBasicMaterial({
      color: new THREE.Color(colors.accent),
      wireframe: true,
      transparent: true,
      opacity: 0.7,
    });

    state.mesh = new THREE.Mesh(geometry, material);
    state.scene.add(state.mesh);

    const particleGeometry = new THREE.BufferGeometry();
    const particlePositions = new Float32Array(30 * 3);
    for (let i = 0; i < 30; i++) {
      particlePositions[i * 3] = (Math.random() - 0.5) * 2;
      particlePositions[i * 3 + 1] = (Math.random() - 0.5) * 2;
      particlePositions[i * 3 + 2] = (Math.random() - 0.5) * 2;
    }
    particleGeometry.setAttribute('position', new THREE.BufferAttribute(particlePositions, 3));

    const particleMaterial = new THREE.PointsMaterial({
      color: new THREE.Color(colors.accent),
      size: 0.03,
      transparent: true,
      opacity: 0.5,
    });

    state.particles = new THREE.Points(particleGeometry, particleMaterial);
    state.scene.add(state.particles);
  },

  render({ ctx, audioData }: RenderParams) {
    if (!state.renderer || !state.scene || !state.camera || !state.mesh) return;

    const canvas = ctx.canvas;
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();

    state.renderer.setSize(rect.width * dpr, rect.height * dpr);
    state.camera.aspect = rect.width / rect.height;
    state.camera.updateProjectionMatrix();

    const data = Array.from(audioData);
    const energy = data.length > 0
      ? data.reduce((sum, v) => sum + Math.abs(v), 0) / data.length
      : 0;

    if (state.mesh && state.originalPositions) {
      const positions = state.mesh.geometry.attributes.position.array as Float32Array;
      for (let i = 0; i < positions.length; i += 3) {
        const origY = state.originalPositions[i + 1];
        const origX = state.originalPositions[i];
        const origZ = state.originalPositions[i + 2];

        if (origY < -0.2) {
          const jawFactor = Math.abs(origY) * energy * 0.5;
          positions[i] = origX + origX * jawFactor;
          positions[i + 1] = origY - jawFactor * 0.3;
          positions[i + 2] = origZ + origZ * jawFactor;
        } else {
          positions[i] = origX;
          positions[i + 1] = origY;
          positions[i + 2] = origZ;
        }
      }
      state.mesh.geometry.attributes.position.needsUpdate = true;

      const material = state.mesh.material as THREE.MeshBasicMaterial;
      const hue = 0.6 + energy * 0.1;
      material.color.setHSL(hue % 1, 0.8, 0.5 + energy * 0.2);
      material.opacity = 0.5 + energy * 0.4;
    }

    if (state.particles) {
      const particlePositions = state.particles.geometry.attributes.position.array as Float32Array;
      for (let i = 0; i < particlePositions.length; i += 3) {
        particlePositions[i] += (Math.random() - 0.5) * energy * 0.05;
        particlePositions[i + 1] += (Math.random() - 0.5) * energy * 0.05;
        particlePositions[i + 2] += (Math.random() - 0.5) * energy * 0.05;
      }
      state.particles.geometry.attributes.position.needsUpdate = true;
      (state.particles.material as THREE.PointsMaterial).opacity = 0.3 + energy * 0.5;
    }

    if (state.mesh) {
      state.mesh.rotation.y += 0.005 + energy * 0.01;
      state.mesh.rotation.x = Math.sin(Date.now() * 0.001) * 0.1;
    }

    state.renderer.render(state.scene, state.camera);
  },

  destroy() {
    if (state.renderer) {
      state.renderer.dispose();
      state.renderer = null;
    }
    if (state.mesh) {
      state.mesh.geometry.dispose();
      (state.mesh.material as THREE.Material).dispose();
      state.mesh = null;
    }
    if (state.particles) {
      state.particles.geometry.dispose();
      (state.particles.material as THREE.Material).dispose();
      state.particles = null;
    }
    state.scene = null;
    state.camera = null;
    state.originalPositions = null;
  },
};
