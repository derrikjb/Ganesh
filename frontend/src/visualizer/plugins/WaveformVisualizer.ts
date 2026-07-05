import type { VisualizerPlugin, RenderParams } from '../types';

const colors = {
  bgPrimary: '#0a0a0a',
  accent: '#3b82f6',
  accentMuted: 'rgba(59, 130, 246, 0.3)',
};

export const WaveformVisualizer: VisualizerPlugin = {
  name: 'Waveform',

  init(ctx: CanvasRenderingContext2D) {
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
  },

  render({ ctx, audioData, dimensions }: RenderParams) {
    const { width, height } = dimensions;
    const centerY = height / 2;

    ctx.clearRect(0, 0, width, height);

    ctx.fillStyle = colors.bgPrimary;
    ctx.fillRect(0, 0, width, height);

    const data = Array.from(audioData);
    if (data.length === 0) return;

    const step = Math.max(1, Math.floor(data.length / width));

    ctx.beginPath();
    ctx.strokeStyle = colors.accent;
    ctx.lineWidth = 2;

    for (let x = 0; x < width; x++) {
      const dataIndex = Math.min(x * step, data.length - 1);
      const amplitude = data[dataIndex];
      const y = centerY + amplitude * (height / 2) * 0.8;

      if (x === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    }

    ctx.stroke();

    ctx.beginPath();
    ctx.strokeStyle = colors.accentMuted;
    ctx.lineWidth = 6;

    for (let x = 0; x < width; x++) {
      const dataIndex = Math.min(x * step, data.length - 1);
      const amplitude = data[dataIndex];
      const y = centerY + amplitude * (height / 2) * 0.8;

      if (x === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    }

    ctx.stroke();
  },
};
