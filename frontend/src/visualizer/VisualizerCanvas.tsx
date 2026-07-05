import { useEffect, useRef, useCallback } from 'react';
import type { VisualizerPlugin, AudioData } from './types';

interface VisualizerCanvasProps {
  plugin: VisualizerPlugin;
  audioData: AudioData;
  className?: string;
}

export function VisualizerCanvas({ plugin, audioData, className }: VisualizerCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pluginRef = useRef<VisualizerPlugin>(plugin);
  const animFrameRef = useRef<number>(0);

  const render = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();

    if (canvas.width !== rect.width * dpr || canvas.height !== rect.height * dpr) {
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.scale(dpr, dpr);
    }

    pluginRef.current.render({
      ctx,
      audioData,
      dimensions: { width: rect.width, height: rect.height },
    });

    animFrameRef.current = requestAnimationFrame(render);
  }, [audioData]);

  useEffect(() => {
    pluginRef.current = plugin;

    const canvas = canvasRef.current;
    if (canvas) {
      const ctx = canvas.getContext('2d');
      if (ctx) {
        plugin.init?.(ctx);
      }
    }

    animFrameRef.current = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(animFrameRef.current);
      plugin.destroy?.();
    };
  }, [plugin, render]);

  return (
    <canvas
      ref={canvasRef}
      className={className}
      style={{ width: '100%', height: '100%' }}
    />
  );
}
