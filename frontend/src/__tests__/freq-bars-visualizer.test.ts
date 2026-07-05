import { describe, it, expect, vi } from 'vitest';
import { FreqBarsVisualizer } from '../visualizer/plugins/FreqBarsVisualizer';
import type { RenderParams } from '../visualizer/types';

function createMockCtx() {
  return {
    clearRect: vi.fn(),
    fillRect: vi.fn(),
    createLinearGradient: vi.fn(() => ({
      addColorStop: vi.fn(),
    })),
    fillStyle: '',
    canvas: { width: 400, height: 200 },
  };
}

describe('FreqBarsVisualizer', () => {
  const mockAudioData = new Float32Array(512);
  for (let i = 0; i < 512; i++) {
    mockAudioData[i] = Math.sin(i * 0.1) * 0.5;
  }

  const dimensions = { width: 400, height: 200 };

  it('renders bars to canvas', () => {
    const ctx = createMockCtx();
    const params: RenderParams = {
      ctx: ctx as any,
      audioData: mockAudioData,
      dimensions,
    };

    FreqBarsVisualizer.render(params);

    expect(ctx.clearRect).toHaveBeenCalled();
    expect(ctx.fillRect).toHaveBeenCalled();
    expect(ctx.createLinearGradient).toHaveBeenCalled();
  });

  it('handles empty audio data gracefully', () => {
    const ctx = createMockCtx();
    const params: RenderParams = {
      ctx: ctx as any,
      audioData: new Float32Array(0),
      dimensions,
    };

    expect(() => FreqBarsVisualizer.render(params)).not.toThrow();
  });

  it('has correct plugin name', () => {
    expect(FreqBarsVisualizer.name).toBe('Freq Bars');
  });
});
