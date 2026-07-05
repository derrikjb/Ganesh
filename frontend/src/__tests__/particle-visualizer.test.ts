import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ParticleVisualizer, getParticleCount } from '../visualizer/plugins/ParticleVisualizer';
import type { RenderParams } from '../visualizer/types';

function createMockCtx() {
  return {
    clearRect: vi.fn(),
    fillRect: vi.fn(),
    beginPath: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    createRadialGradient: vi.fn(() => ({
      addColorStop: vi.fn(),
    })),
    fillStyle: '',
    canvas: { width: 400, height: 200 },
  };
}

describe('ParticleVisualizer', () => {
  const mockAudioData = new Float32Array(512);
  for (let i = 0; i < 512; i++) {
    mockAudioData[i] = Math.sin(i * 0.1) * 0.5;
  }

  const dimensions = { width: 400, height: 200 };

  beforeEach(() => {
    ParticleVisualizer.init?.({} as any);
  });

  it('particles move with audio data', () => {
    const ctx = createMockCtx();
    const params: RenderParams = {
      ctx: ctx as any,
      audioData: mockAudioData,
      dimensions,
    };

    ParticleVisualizer.render(params);

    expect(ctx.clearRect).toHaveBeenCalled();
    expect(ctx.beginPath).toHaveBeenCalled();
    expect(ctx.arc).toHaveBeenCalled();
  });

  it('spawns particles proportional to energy', () => {
    const ctx = createMockCtx();
    const highEnergy = new Float32Array(512).fill(0.8);
    const lowEnergy = new Float32Array(512).fill(0.01);

    ParticleVisualizer.render({
      ctx: ctx as any,
      audioData: highEnergy,
      dimensions,
    });
    const highCount = getParticleCount();

    ParticleVisualizer.init?.({} as any);

    ParticleVisualizer.render({
      ctx: ctx as any,
      audioData: lowEnergy,
      dimensions,
    });
    const lowCount = getParticleCount();

    expect(highCount).toBeGreaterThanOrEqual(lowCount);
  });

  it('handles empty audio data gracefully', () => {
    const ctx = createMockCtx();
    const params: RenderParams = {
      ctx: ctx as any,
      audioData: new Float32Array(0),
      dimensions,
    };

    expect(() => ParticleVisualizer.render(params)).not.toThrow();
  });

  it('has correct plugin name', () => {
    expect(ParticleVisualizer.name).toBe('Particles');
  });

  it('clears particles on destroy', () => {
    ParticleVisualizer.render({
      ctx: createMockCtx() as any,
      audioData: mockAudioData,
      dimensions,
    });

    expect(getParticleCount()).toBeGreaterThan(0);

    ParticleVisualizer.destroy?.();

    expect(getParticleCount()).toBe(0);
  });
});
