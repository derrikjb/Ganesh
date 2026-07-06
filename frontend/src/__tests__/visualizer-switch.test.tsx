import '@testing-library/jest-dom';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, screen, fireEvent } from '@testing-library/react';
import { VoiceVisualizer } from '../components/VoiceVisualizer';
import { list as listPlugins } from '../visualizer/registry';
import { VisualizerStateProvider } from '../contexts/VisualizerStateContext';
import { AccessibilityProvider } from '../contexts/AccessibilityContext';

let rafCallbacks: ((time: number) => void)[] = [];

function mockCanvasContext() {
  const ctx = {
    clearRect: vi.fn(),
    fillRect: vi.fn(),
    beginPath: vi.fn(),
    stroke: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    lineCap: '',
    lineJoin: '',
    strokeStyle: '',
    lineWidth: 0,
    scale: vi.fn(),
    createLinearGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
    arc: vi.fn(),
    fill: vi.fn(),
    createRadialGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
    canvas: { width: 400, height: 200 },
  };

  const originalGetContext = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = vi.fn(() => ctx) as any;

  return {
    ctx,
    restore: () => {
      HTMLCanvasElement.prototype.getContext = originalGetContext;
    },
  };
}

function mockRequestAnimationFrame() {
  const originalRaf = window.requestAnimationFrame;
  const originalCaf = window.cancelAnimationFrame;

  rafCallbacks = [];

  window.requestAnimationFrame = vi.fn((cb: FrameRequestCallback) => {
    rafCallbacks.push(cb);
    return rafCallbacks.length;
  });

  window.cancelAnimationFrame = vi.fn((id: number) => {
    rafCallbacks = rafCallbacks.filter((_, i) => i !== id - 1);
  });

  return {
    fireAll: () => {
      const callbacks = [...rafCallbacks];
      rafCallbacks = [];
      callbacks.forEach((cb) => cb(0));
    },
    restore: () => {
      window.requestAnimationFrame = originalRaf;
      window.cancelAnimationFrame = originalCaf;
    },
  };
}

vi.mock('three', () => ({
  Scene: vi.fn(() => ({ add: vi.fn() })),
  PerspectiveCamera: vi.fn(() => ({ position: { z: 3 }, aspect: 1, updateProjectionMatrix: vi.fn() })),
  WebGLRenderer: vi.fn(() => ({ setClearColor: vi.fn(), setSize: vi.fn(), render: vi.fn(), dispose: vi.fn() })),
  IcosahedronGeometry: vi.fn(() => ({ attributes: { position: { array: new Float32Array(300) } } })),
  MeshBasicMaterial: vi.fn(() => ({ color: { setHSL: vi.fn() }, opacity: 0.7, dispose: vi.fn() })),
  Mesh: vi.fn(() => ({ geometry: { attributes: { position: { array: new Float32Array(300), needsUpdate: false } }, material: { color: { setHSL: vi.fn() }, opacity: 0.7 }, rotation: { x: 0, y: 0, z: 0 } } })),
  BufferGeometry: vi.fn(() => ({ attributes: { position: { array: new Float32Array(90) } }, setAttribute: vi.fn() })),
  BufferAttribute: vi.fn((arr) => arr),
  PointsMaterial: vi.fn(() => ({ opacity: 0.5, dispose: vi.fn() })),
  Points: vi.fn(() => ({ geometry: { attributes: { position: { array: new Float32Array(90) } } }, material: { opacity: 0.5, dispose: vi.fn() } })),
  Color: vi.fn(() => ({ setHSL: vi.fn() })),
}));

describe('VoiceVisualizer', () => {
  beforeEach(() => {
    rafCallbacks = [];
  });

  afterEach(() => {
    cleanup();
  });

  it('switching between plugins works', () => {
    const { restore } = mockCanvasContext();
    const { restore: restoreRaf } = mockRequestAnimationFrame();

    try {
      render(
        <AccessibilityProvider>
          <VisualizerStateProvider>
            <VoiceVisualizer />
          </VisualizerStateProvider>
        </AccessibilityProvider>
      );

      const plugins = listPlugins();
      expect(plugins.length).toBeGreaterThanOrEqual(4);

      const initialName = screen.getByText(/Visualizer:/);
      expect(initialName).toBeInTheDocument();

      const buttons = screen.getAllByRole('button');
      const pluginButtons = buttons.filter((b) =>
        plugins.some((p) => b.textContent === p.name)
      );

      expect(pluginButtons.length).toBeGreaterThanOrEqual(4);

      fireEvent.click(pluginButtons[1]);

      const updatedName = screen.getByText(/Visualizer:/);
      expect(updatedName.textContent).toContain(plugins[1].name);
    } finally {
      restore();
      restoreRaf();
    }
  });
});
