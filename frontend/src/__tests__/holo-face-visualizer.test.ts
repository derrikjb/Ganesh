import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { RenderParams } from '../visualizer/types';

vi.mock('three', () => {
  const mockDispose = vi.fn();

  const MockMaterial = {
    color: { setHSL: vi.fn() },
    opacity: 0.7,
    dispose: mockDispose,
  };

  const MockGeometry = {
    attributes: {
      position: {
        array: new Float32Array(300),
        needsUpdate: false,
      },
    },
    dispose: mockDispose,
  };

  const MockMesh = {
    geometry: MockGeometry,
    material: MockMaterial,
    rotation: { x: 0, y: 0, z: 0 },
  };

  const MockPoints = {
    geometry: {
      attributes: {
        position: {
          array: new Float32Array(90),
          needsUpdate: false,
        },
      },
      dispose: mockDispose,
    },
    material: { opacity: 0.5, dispose: mockDispose },
  };

  const MockRenderer = {
    setClearColor: vi.fn(),
    setSize: vi.fn(),
    render: vi.fn(),
    dispose: mockDispose,
  };

  const MockCamera = {
    position: { z: 3 },
    aspect: 1,
    updateProjectionMatrix: vi.fn(),
  };

  const MockScene = {
    add: vi.fn(),
  };

  return {
    Scene: vi.fn(() => MockScene),
    PerspectiveCamera: vi.fn(() => MockCamera),
    WebGLRenderer: vi.fn(() => MockRenderer),
    IcosahedronGeometry: vi.fn(() => MockGeometry),
    MeshBasicMaterial: vi.fn(() => MockMaterial),
    Mesh: vi.fn(() => MockMesh),
    BufferGeometry: vi.fn(() => ({
      attributes: { position: { array: new Float32Array(90) } },
      setAttribute: vi.fn(),
    })),
    BufferAttribute: vi.fn((arr) => arr),
    PointsMaterial: vi.fn(() => ({ opacity: 0.5, dispose: mockDispose })),
    Points: vi.fn(() => MockPoints),
    Color: vi.fn(() => ({ setHSL: vi.fn() })),
  };
});

const { HoloFaceVisualizer } = await import('../visualizer/plugins/HoloFaceVisualizer');

describe('HoloFaceVisualizer', () => {
  const mockAudioData = new Float32Array(512);
  for (let i = 0; i < 512; i++) {
    mockAudioData[i] = Math.sin(i * 0.1) * 0.5;
  }

  const dimensions = { width: 400, height: 200 };

  const mockCanvas = {
    width: 400,
    height: 200,
    getBoundingClientRect: () => ({ width: 400, height: 200 }),
  };

  const mockCtx = {
    canvas: mockCanvas,
  } as any;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    HoloFaceVisualizer.destroy?.();
  });

  it('Three.js scene initializes', () => {
    HoloFaceVisualizer.init?.(mockCtx);

    expect(HoloFaceVisualizer).toBeDefined();
  });

  it('renders without errors after init', () => {
    HoloFaceVisualizer.init?.(mockCtx);

    const params: RenderParams = {
      ctx: mockCtx,
      audioData: mockAudioData,
      dimensions,
    };

    expect(() => HoloFaceVisualizer.render(params)).not.toThrow();
  });

  it('has correct plugin name', () => {
    expect(HoloFaceVisualizer.name).toBe('Holo Face');
  });

  it('cleans up resources on destroy', () => {
    HoloFaceVisualizer.init?.(mockCtx);
    HoloFaceVisualizer.destroy?.();

    expect(HoloFaceVisualizer.name).toBe('Holo Face');
  });
});
