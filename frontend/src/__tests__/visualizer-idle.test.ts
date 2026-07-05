import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { WaveformVisualizer } from '../visualizer/plugins/WaveformVisualizer';
import type { RenderParams } from '../visualizer/types';

function createMockCtx() {
  const drawnPaths: { x: number; y: number }[] = [];

  const ctx = {
    clearRect: vi.fn(),
    fillRect: vi.fn(),
    beginPath: vi.fn(),
    stroke: vi.fn(),
    moveTo: vi.fn((x: number, y: number) => {
      drawnPaths.push({ x, y });
    }),
    lineTo: vi.fn((x: number, y: number) => {
      drawnPaths.push({ x, y });
    }),
    lineCap: '',
    lineJoin: '',
    strokeStyle: '',
    lineWidth: 0,
    canvas: { width: 400, height: 200 },
  };

  return { ctx, drawnPaths };
}

describe('WaveformVisualizer Idle Animation', () => {
  const dimensions = { width: 400, height: 200 };
  const emptyAudio = new Float32Array(0);

  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders idle state with no audio data', () => {
    const { ctx } = createMockCtx();
    const params: RenderParams = {
      ctx: ctx as any,
      audioData: emptyAudio,
      dimensions,
      state: 'IDLE',
      timeMs: 0,
    };

    expect(() => WaveformVisualizer.render(params)).not.toThrow();
    expect(ctx.clearRect).toHaveBeenCalled();
    expect(ctx.fillRect).toHaveBeenCalled();
  });

  it('idle animation produces pixel variance > 0 across time', () => {
    const { ctx, drawnPaths } = createMockCtx();

    const renderAt = (timeMs: number) => {
      drawnPaths.length = 0;
      ctx.clearRect.mockClear();
      ctx.fillRect.mockClear();
      ctx.beginPath.mockClear();
      ctx.stroke.mockClear();
      ctx.moveTo.mockClear();
      ctx.lineTo.mockClear();

      const params: RenderParams = {
        ctx: ctx as any,
        audioData: emptyAudio,
        dimensions,
        state: 'IDLE',
        timeMs,
      };
      WaveformVisualizer.render(params);
      return [...drawnPaths];
    };

    const frame0 = renderAt(0);
    const frame1 = renderAt(250);
    const frame2 = renderAt(500);

    expect(frame0.length).toBeGreaterThan(0);
    expect(frame1.length).toBeGreaterThan(0);
    expect(frame2.length).toBeGreaterThan(0);

    const yValues0 = frame0.map((p) => p.y);
    const yValues1 = frame1.map((p) => p.y);

    const variance = yValues0.reduce((sum, y, i) => {
      const diff = y - (yValues1[i] ?? y);
      return sum + diff * diff;
    }, 0);

    expect(variance).toBeGreaterThan(0);
  });

  it('idle animation uses low amplitude (subtle)', () => {
    const { ctx, drawnPaths } = createMockCtx();
    const centerY = dimensions.height / 2;

    const params: RenderParams = {
      ctx: ctx as any,
      audioData: emptyAudio,
      dimensions,
      state: 'IDLE',
      timeMs: 1000,
    };
    WaveformVisualizer.render(params);

    const yValues = drawnPaths.map((p) => p.y);
    const maxDeviation = Math.max(...yValues.map((y) => Math.abs(y - centerY)));

    expect(maxDeviation).toBeLessThan(centerY * 0.3);
  });

  it('thinking state renders with faster pulse than idle', () => {
    const renderAt = (timeMs: number, state: 'IDLE' | 'THINKING') => {
      const paths: { x: number; y: number }[] = [];
      const mockCtx = {
        clearRect: vi.fn(),
        fillRect: vi.fn(),
        beginPath: vi.fn(),
        stroke: vi.fn(),
        moveTo: vi.fn((x: number, y: number) => paths.push({ x, y })),
        lineTo: vi.fn((x: number, y: number) => paths.push({ x, y })),
        lineCap: '',
        lineJoin: '',
        strokeStyle: '',
        lineWidth: 0,
        canvas: { width: 400, height: 200 },
      };

      const params: RenderParams = {
        ctx: mockCtx as any,
        audioData: emptyAudio,
        dimensions,
        state,
        timeMs,
      };
      WaveformVisualizer.render(params);
      return paths;
    };

    const idle0 = renderAt(0, 'IDLE');
    const idle1 = renderAt(500, 'IDLE');
    const thinking0 = renderAt(0, 'THINKING');
    const thinking1 = renderAt(500, 'THINKING');

    const idleVariance = idle0.reduce((sum, p, i) => {
      const other = idle1[i] ?? p;
      return sum + Math.pow(p.y - other.y, 2);
    }, 0);

    const thinkingVariance = thinking0.reduce((sum, p, i) => {
      const other = thinking1[i] ?? p;
      return sum + Math.pow(p.y - other.y, 2);
    }, 0);

    expect(thinkingVariance).toBeGreaterThan(idleVariance);
  });

  it('has correct plugin name', () => {
    expect(WaveformVisualizer.name).toBe('Waveform');
  });
});
