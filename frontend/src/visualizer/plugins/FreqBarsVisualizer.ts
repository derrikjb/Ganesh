import type { VisualizerPlugin, RenderParams } from '../types';

const colors = {
  bgPrimary: '#0a0a0a',
  accent: '#3b82f6',
  accentMuted: 'rgba(59, 130, 246, 0.3)',
  accentGlow: 'rgba(59, 130, 246, 0.6)',
};

const BAR_COUNT = 64;
const BAR_GAP = 2;

export const FreqBarsVisualizer: VisualizerPlugin = {
  name: 'Freq Bars',

  render({ ctx, audioData, dimensions }: RenderParams) {
    const { width, height } = dimensions;

    ctx.clearRect(0, 0, width, height);

    ctx.fillStyle = colors.bgPrimary;
    ctx.fillRect(0, 0, width, height);

    const data = Array.from(audioData);
    if (data.length === 0) return;

    const barWidth = (width - BAR_GAP * (BAR_COUNT - 1)) / BAR_COUNT;
    const maxBarHeight = height * 0.85;

    for (let i = 0; i < BAR_COUNT; i++) {
      const dataIndex = Math.floor((i / BAR_COUNT) * data.length);
      const value = Math.abs(data[dataIndex] || 0);
      const barHeight = Math.max(2, value * maxBarHeight);

      const x = i * (barWidth + BAR_GAP);
      const y = height - barHeight;

      const gradient = ctx.createLinearGradient(x, height, x, y);
      gradient.addColorStop(0, colors.accent);
      gradient.addColorStop(1, colors.accentGlow);

      ctx.fillStyle = gradient;
      ctx.fillRect(x, y, barWidth, barHeight);

      ctx.fillStyle = colors.accentMuted;
      ctx.fillRect(x, y - 4, barWidth, 2);
    }
  },
};
