import type { VisualizerPlugin, RenderParams } from '../types';

const colors = {
  bgPrimary: '#0a0a0a',
  accent: '#3b82f6',
  accentMuted: 'rgba(59, 130, 246, 0.3)',
};

const IDLE_FREQ_HZ = 0.1;
const THINKING_FREQ_HZ = 1;
const IDLE_AMPLITUDE = 0.05;

function renderIdle(ctx: CanvasRenderingContext2D, dimensions: { width: number; height: number }, timeMs: number) {
  const { width, height } = dimensions;
  const centerY = height / 2;
  const timeSec = timeMs / 1000;
  const breath = Math.sin(timeSec * IDLE_FREQ_HZ * Math.PI * 2) * 0.5 + 0.5;
  const opacity = 0.3 + breath * 0.3;
  const scale = 0.8 + breath * 0.2;

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = colors.bgPrimary;
  ctx.fillRect(0, 0, width, height);

  ctx.beginPath();
  ctx.strokeStyle = `rgba(59, 130, 246, ${opacity})`;
  ctx.lineWidth = 2;

  for (let x = 0; x < width; x++) {
    const t = x / width;
    const y = centerY + Math.sin(t * Math.PI * 4 + timeSec * IDLE_FREQ_HZ * Math.PI * 2) * (height / 2) * IDLE_AMPLITUDE * scale;
    if (x === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  }
  ctx.stroke();
}

function renderThinking(ctx: CanvasRenderingContext2D, dimensions: { width: number; height: number }, timeMs: number) {
  const { width, height } = dimensions;
  const centerY = height / 2;
  const timeSec = timeMs / 1000;
  const pulse = Math.sin(timeSec * THINKING_FREQ_HZ * Math.PI * 2) * 0.5 + 0.5;
  const opacity = 0.4 + pulse * 0.4;
  const amplitude = IDLE_AMPLITUDE * (1.5 + pulse);

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = colors.bgPrimary;
  ctx.fillRect(0, 0, width, height);

  ctx.beginPath();
  ctx.strokeStyle = `rgba(59, 130, 246, ${opacity})`;
  ctx.lineWidth = 2;

  for (let x = 0; x < width; x++) {
    const t = x / width;
    const y = centerY + Math.sin(t * Math.PI * 6 + timeSec * THINKING_FREQ_HZ * Math.PI * 2) * (height / 2) * amplitude;
    if (x === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  }
  ctx.stroke();
}

function renderSpeaking(ctx: CanvasRenderingContext2D, audioData: number[], dimensions: { width: number; height: number }) {
  const { width, height } = dimensions;
  const centerY = height / 2;

  const step = Math.max(1, Math.floor(audioData.length / width));

  ctx.beginPath();
  ctx.strokeStyle = colors.accent;
  ctx.lineWidth = 2;

  for (let x = 0; x < width; x++) {
    const dataIndex = Math.min(x * step, audioData.length - 1);
    const amplitude = audioData[dataIndex];
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
    const dataIndex = Math.min(x * step, audioData.length - 1);
    const amplitude = audioData[dataIndex];
    const y = centerY + amplitude * (height / 2) * 0.8;

    if (x === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  }
  ctx.stroke();
}

export const WaveformVisualizer: VisualizerPlugin = {
  name: 'Waveform',

  init(ctx: CanvasRenderingContext2D) {
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
  },

  render({ ctx, audioData, dimensions, state = 'IDLE', timeMs = 0 }: RenderParams) {
    const { width, height } = dimensions;

    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = colors.bgPrimary;
    ctx.fillRect(0, 0, width, height);

    const data = Array.from(audioData);

    if (state === 'IDLE') {
      renderIdle(ctx, dimensions, timeMs);
      return;
    }

    if (state === 'THINKING') {
      renderThinking(ctx, dimensions, timeMs);
      return;
    }

    if (data.length === 0) return;

    renderSpeaking(ctx, data, dimensions);
  },
};
