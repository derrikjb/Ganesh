import '@testing-library/jest-dom';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, act } from '@testing-library/react';
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
    fireAll: (timestamp = 0) => {
      const callbacks = [...rafCallbacks];
      rafCallbacks = [];
      callbacks.forEach((cb) => cb(timestamp));
    },
    restore: () => {
      window.requestAnimationFrame = originalRaf;
      window.cancelAnimationFrame = originalCaf;
    },
  };
}

describe('VisualizerCanvas State Transitions', () => {
  const mockPlugin: VisualizerPlugin = {
    name: 'TestPlugin',
    init: vi.fn(),
    render: vi.fn(),
    destroy: vi.fn(),
  };

  const emptyAudio = new Float32Array(0);
  const activeAudio = new Float32Array(512).fill(0.5);

  beforeEach(() => {
    vi.clearAllMocks();
    rafCallbacks = [];
  });

  afterEach(() => {
    cleanup();
  });

  it('starts in IDLE state by default', () => {
    const { restore } = mockCanvasContext();
    const { restore: restoreRaf } = mockRequestAnimationFrame();
    try {
      render(<VisualizerCanvas plugin={mockPlugin} audioData={emptyAudio} />);

      const canvas = document.querySelector('canvas');
      expect(canvas).toHaveAttribute('data-state', 'IDLE');
    } finally {
      restore();
      restoreRaf();
    }
  });

  it('transitions to SPEAKING when audio has activity', () => {
    const { restore } = mockCanvasContext();
    const { fireAll, restore: restoreRaf } = mockRequestAnimationFrame();
    try {
      const { rerender } = render(
        <VisualizerCanvas plugin={mockPlugin} audioData={emptyAudio} />
      );

      fireAll(0);

      rerender(<VisualizerCanvas plugin={mockPlugin} audioData={activeAudio} />);
      act(() => {
        fireAll(100);
      });

      const canvas = document.querySelector('canvas');
      expect(canvas).toHaveAttribute('data-state', 'SPEAKING');
    } finally {
      restore();
      restoreRaf();
    }
  });

  it('transitions back to IDLE after audio stops', () => {
    vi.useFakeTimers();
    const { restore } = mockCanvasContext();
    const { fireAll, restore: restoreRaf } = mockRequestAnimationFrame();
    try {
      const { rerender } = render(
        <VisualizerCanvas plugin={mockPlugin} audioData={activeAudio} />
      );

      act(() => {
        fireAll(100);
      });

      let canvas = document.querySelector('canvas');
      expect(canvas).toHaveAttribute('data-state', 'SPEAKING');

      rerender(<VisualizerCanvas plugin={mockPlugin} audioData={emptyAudio} />);
      act(() => {
        fireAll(200);
      });

      act(() => {
        vi.advanceTimersByTime(350);
      });

      canvas = document.querySelector('canvas');
      expect(canvas).toHaveAttribute('data-state', 'IDLE');
    } finally {
      restore();
      restoreRaf();
      vi.useRealTimers();
    }
  });

  it('respects forced state prop over auto-detection', () => {
    const { restore } = mockCanvasContext();
    const { fireAll, restore: restoreRaf } = mockRequestAnimationFrame();
    try {
      render(
        <VisualizerCanvas
          plugin={mockPlugin}
          audioData={activeAudio}
          state="THINKING"
        />
      );

      act(() => {
        fireAll(100);
      });

      const canvas = document.querySelector('canvas');
      expect(canvas).toHaveAttribute('data-state', 'THINKING');
    } finally {
      restore();
      restoreRaf();
    }
  });

  it('passes state and timeMs to plugin.render', () => {
    const { restore } = mockCanvasContext();
    const { fireAll, restore: restoreRaf } = mockRequestAnimationFrame();
    try {
      render(
        <VisualizerCanvas
          plugin={mockPlugin}
          audioData={emptyAudio}
          state="IDLE"
        />
      );

      act(() => {
        fireAll(1000);
      });

      expect(mockPlugin.render).toHaveBeenCalledWith(
        expect.objectContaining({
          state: 'IDLE',
          timeMs: expect.any(Number),
        })
      );
    } finally {
      restore();
      restoreRaf();
    }
  });

  it('state transitions complete within 500ms', () => {
    vi.useFakeTimers();
    const { restore } = mockCanvasContext();
    const { fireAll, restore: restoreRaf } = mockRequestAnimationFrame();
    try {
      const { rerender } = render(
        <VisualizerCanvas plugin={mockPlugin} audioData={emptyAudio} />
      );

      act(() => { fireAll(0); });
      expect(document.querySelector('canvas')).toHaveAttribute('data-state', 'IDLE');

      rerender(<VisualizerCanvas plugin={mockPlugin} audioData={activeAudio} />);
      act(() => { fireAll(100); });
      expect(document.querySelector('canvas')).toHaveAttribute('data-state', 'SPEAKING');

      rerender(<VisualizerCanvas plugin={mockPlugin} audioData={emptyAudio} />);
      act(() => { fireAll(200); });
      act(() => { vi.advanceTimersByTime(350); });
      expect(document.querySelector('canvas')).toHaveAttribute('data-state', 'IDLE');
    } finally {
      restore();
      restoreRaf();
      vi.useRealTimers();
    }
  });

  it('THINKING visual state is distinct from IDLE — different render params passed to plugin', () => {
    const { restore } = mockCanvasContext();
    const { fireAll, restore: restoreRaf } = mockRequestAnimationFrame();
    try {
      const { unmount: unmount1 } = render(
        <VisualizerCanvas
          plugin={mockPlugin}
          audioData={emptyAudio}
          state="THINKING"
        />
      );

      act(() => { fireAll(1000); });

      const renderFn = mockPlugin.render as ReturnType<typeof vi.fn>;
      const call = renderFn.mock.calls[0][0];
      expect(call.state).toBe('THINKING');
      expect(call.timeMs).toBeGreaterThan(0);

      vi.clearAllMocks();
      unmount1();

      render(
        <VisualizerCanvas
          plugin={mockPlugin}
          audioData={emptyAudio}
          state="IDLE"
        />
      );

      act(() => { fireAll(2000); });

      const idleCall = renderFn.mock.calls[0][0];
      expect(idleCall.state).toBe('IDLE');
      expect(idleCall.timeMs).toBeGreaterThan(0);
    } finally {
      restore();
      restoreRaf();
    }
  });

  it('transitions to THINKING when LLM processing starts (state prop)', () => {
    const { restore } = mockCanvasContext();
    const { fireAll, restore: restoreRaf } = mockRequestAnimationFrame();
    try {
      const { rerender } = render(
        <VisualizerCanvas plugin={mockPlugin} audioData={emptyAudio} />
      );

      act(() => { fireAll(0); });
      expect(document.querySelector('canvas')).toHaveAttribute('data-state', 'IDLE');

      rerender(
        <VisualizerCanvas
          plugin={mockPlugin}
          audioData={emptyAudio}
          state="THINKING"
        />
      );
      act(() => { fireAll(100); });

      const canvas = document.querySelector('canvas');
      expect(canvas).toHaveAttribute('data-state', 'THINKING');
    } finally {
      restore();
      restoreRaf();
    }
  });
});
