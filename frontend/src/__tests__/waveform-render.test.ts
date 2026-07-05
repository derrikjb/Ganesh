import { describe, it, expect, vi } from 'vitest';
import { WaveformVisualizer } from '../visualizer/plugins/WaveformVisualizer';

function createMockContext() {
  return {
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
  };
}

describe('WaveformVisualizer', () => {
  it('has correct name', () => {
    expect(WaveformVisualizer.name).toBe('Waveform');
  });

  it('renders to canvas with mock context', () => {
    const ctx = createMockContext();
    const audioData = new Float32Array([0.1, 0.2, 0.3, 0.4, 0.5]);
    const dimensions = { width: 100, height: 50 };

    WaveformVisualizer.render({ ctx: ctx as any, audioData, dimensions });

    expect(ctx.clearRect).toHaveBeenCalled();
    expect(ctx.fillRect).toHaveBeenCalled();
    expect(ctx.beginPath).toHaveBeenCalled();
    expect(ctx.stroke).toHaveBeenCalled();
  });

  it('handles empty audio data', () => {
    const ctx = createMockContext();
    const audioData = new Float32Array(0);
    const dimensions = { width: 100, height: 50 };

    WaveformVisualizer.render({ ctx: ctx as any, audioData, dimensions });

    expect(ctx.clearRect).toHaveBeenCalled();
    expect(ctx.fillRect).toHaveBeenCalled();
    expect(ctx.moveTo).not.toHaveBeenCalled();
  });

  it('initializes canvas context properties', () => {
    const ctx = createMockContext();

    WaveformVisualizer.init?.(ctx as any);

    expect(ctx.lineCap).toBe('round');
    expect(ctx.lineJoin).toBe('round');
  });

  it('renders with array audio data', () => {
    const ctx = createMockContext();
    const audioData = [0.1, -0.2, 0.3, -0.4, 0.5];
    const dimensions = { width: 100, height: 50 };

    WaveformVisualizer.render({ ctx: ctx as any, audioData, dimensions });

    expect(ctx.clearRect).toHaveBeenCalled();
    expect(ctx.stroke).toHaveBeenCalled();
  });
});
