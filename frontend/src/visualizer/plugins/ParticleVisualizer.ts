import type { VisualizerPlugin, RenderParams } from '../types';

const colors = {
  bgPrimary: '#0a0a0a',
  accent: '#3b82f6',
  accentMuted: 'rgba(59, 130, 246, 0.3)',
  accentGlow: 'rgba(59, 130, 246, 0.6)',
};

const PARTICLE_COUNT = 120;

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  alpha: number;
  life: number;
  maxLife: number;
}

const particles: Particle[] = [];

function createParticle(cx: number, cy: number, energy: number): Particle {
  const angle = Math.random() * Math.PI * 2;
  const speed = (0.5 + Math.random() * 2) * (1 + energy * 3);
  return {
    x: cx,
    y: cy,
    vx: Math.cos(angle) * speed,
    vy: Math.sin(angle) * speed,
    radius: 1 + Math.random() * 3 * (1 + energy),
    alpha: 0.4 + Math.random() * 0.6,
    life: 0,
    maxLife: 30 + Math.random() * 60,
  };
}

export const ParticleVisualizer: VisualizerPlugin = {
  name: 'Particles',

  init() {
    particles.length = 0;
  },

  render({ ctx, audioData, dimensions }: RenderParams) {
    const { width, height } = dimensions;
    const cx = width / 2;
    const cy = height / 2;

    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = colors.bgPrimary;
    ctx.fillRect(0, 0, width, height);

    const data = Array.from(audioData);
    const energy = data.length > 0
      ? data.reduce((sum, v) => sum + Math.abs(v), 0) / data.length
      : 0;

    const spawnCount = Math.floor(energy * 5);
    for (let i = 0; i < spawnCount && particles.length < PARTICLE_COUNT; i++) {
      particles.push(createParticle(cx, cy, energy));
    }

    for (let i = particles.length - 1; i >= 0; i--) {
      const p = particles[i];
      p.x += p.vx;
      p.y += p.vy;
      p.vy += 0.02;
      p.life++;

      const lifeRatio = 1 - p.life / p.maxLife;
      if (lifeRatio <= 0) {
        particles.splice(i, 1);
        continue;
      }

      const currentAlpha = p.alpha * lifeRatio;
      const currentRadius = p.radius * lifeRatio;

      ctx.beginPath();
      ctx.arc(p.x, p.y, currentRadius, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(59, 130, 246, ${currentAlpha})`;
      ctx.fill();

      ctx.beginPath();
      ctx.arc(p.x, p.y, currentRadius * 2, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(59, 130, 246, ${currentAlpha * 0.2})`;
      ctx.fill();
    }

    if (energy > 0.05) {
      const glowRadius = 20 + energy * 40;
      const gradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, glowRadius);
      gradient.addColorStop(0, `rgba(59, 130, 246, ${energy * 0.4})`);
      gradient.addColorStop(1, 'rgba(59, 130, 246, 0)');
      ctx.fillStyle = gradient;
      ctx.fillRect(cx - glowRadius, cy - glowRadius, glowRadius * 2, glowRadius * 2);
    }
  },

  destroy() {
    particles.length = 0;
  },
};

export function getParticleCount(): number {
  return particles.length;
}
