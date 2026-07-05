import '@testing-library/jest-dom';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/react';
import { VisualizerCanvas } from '../visualizer/VisualizerCanvas';
import type { VisualizerPlugin } from '../visualizer/types';

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

describe('VisualizerCanvas', () => {
  const mockPlugin: VisualizerPlugin = {
    name: 'TestPlugin',
    init: vi.fn(),
    render: vi.fn(),
    destroy: vi.fn(),
  };

  const mockAudioData = new Float32Array([0.1, 0.2, 0.3]);

  beforeEach(() => {
    vi.clearAllMocks();
    rafCallbacks = [];
  });

  afterEach(() => {
    cleanup();
  });

  it('renders canvas element', () => {
    const { restore } = mockCanvasContext();
    const { fireAll, restore: restoreRaf } = mockRequestAnimationFrame();
    try {
      render(
        <VisualizerCanvas plugin={mockPlugin} audioData={mockAudioData} />
      );

      const canvas = document.querySelector('canvas');
      expect(canvas).toBeInTheDocument();

      fireAll();
      expect(mockPlugin.render).toHaveBeenCalled();
    } finally {
      restore();
      restoreRaf();
    }
  });

  it('calls plugin init on mount', () => {
    const { restore } = mockCanvasContext();
    const { restore: restoreRaf } = mockRequestAnimationFrame();
    try {
      render(
        <VisualizerCanvas plugin={mockPlugin} audioData={mockAudioData} />
      );

      expect(mockPlugin.init).toHaveBeenCalled();
    } finally {
      restore();
      restoreRaf();
    }
  });

  it('calls plugin destroy on unmount', () => {
    const { restore } = mockCanvasContext();
    const { restore: restoreRaf } = mockRequestAnimationFrame();
    try {
      const { unmount } = render(
        <VisualizerCanvas plugin={mockPlugin} audioData={mockAudioData} />
      );

      unmount();

      expect(mockPlugin.destroy).toHaveBeenCalled();
    } finally {
      restore();
      restoreRaf();
    }
  });

  it('applies custom className', () => {
    const { restore } = mockCanvasContext();
    const { restore: restoreRaf } = mockRequestAnimationFrame();
    try {
      render(
        <VisualizerCanvas
          plugin={mockPlugin}
          audioData={mockAudioData}
          className="custom-class"
        />
      );

      const canvas = document.querySelector('canvas');
      expect(canvas).toHaveClass('custom-class');
    } finally {
      restore();
      restoreRaf();
    }
  });

  it('works with plugin without init/destroy', () => {
    const { restore } = mockCanvasContext();
    const { restore: restoreRaf } = mockRequestAnimationFrame();
    try {
      const minimalPlugin: VisualizerPlugin = {
        name: 'Minimal',
        render: vi.fn(),
      };

      expect(() =>
        render(
          <VisualizerCanvas plugin={minimalPlugin} audioData={mockAudioData} />
        )
      ).not.toThrow();
    } finally {
      restore();
      restoreRaf();
    }
  });
});
