import { useEffect, useRef, useCallback, useState } from 'react';
import type { VisualizerPlugin, AudioData, VisualizerState } from './types';

interface VisualizerCanvasProps {
  plugin: VisualizerPlugin;
  audioData: AudioData;
  className?: string;
  /** Force a specific state from parent (overrides auto-detection) */
  state?: VisualizerState;
}

const IDLE_TIMEOUT_MS = 300;
const AUDIO_ACTIVITY_THRESHOLD = 0.02;

export function VisualizerCanvas({ plugin, audioData, className, state: forcedState }: VisualizerCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pluginRef = useRef<VisualizerPlugin>(plugin);
  const animFrameRef = useRef<number>(0);
  const stateStartTimeRef = useRef<number>(0);

  const [currentState, setCurrentState] = useState<VisualizerState>('IDLE');
  const idleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isWebGL = plugin.name === 'Holo Face';

  const effectiveState = forcedState ?? currentState;

  const hasAudioActivity = useCallback((data: AudioData): boolean => {
    const arr = Array.from(data);
    if (arr.length === 0) return false;
    const energy = arr.reduce((sum, v) => sum + Math.abs(v), 0) / arr.length;
    return energy > AUDIO_ACTIVITY_THRESHOLD;
  }, []);

  const transitionTo = useCallback((newState: VisualizerState, timestamp: number) => {
    if (newState !== effectiveState) {
      stateStartTimeRef.current = timestamp;
      setCurrentState(newState);
    }
  }, [effectiveState]);

  const render = useCallback((timestamp: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext(isWebGL ? 'webgl2' : '2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();

    if (canvas.width !== rect.width * dpr || canvas.height !== rect.height * dpr) {
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      if (!isWebGL) {
        (ctx as CanvasRenderingContext2D).scale(dpr, dpr);
      }
    }

    if (hasAudioActivity(audioData)) {
      if (idleTimerRef.current) {
        clearTimeout(idleTimerRef.current);
        idleTimerRef.current = null;
      }
      transitionTo('SPEAKING', timestamp);
    } else if (effectiveState === 'SPEAKING' && !idleTimerRef.current) {
      idleTimerRef.current = setTimeout(() => {
        transitionTo('IDLE', performance.now());
        idleTimerRef.current = null;
      }, IDLE_TIMEOUT_MS);
    }

    const elapsed = timestamp - stateStartTimeRef.current;

    pluginRef.current.render({
      ctx: ctx as any,
      audioData,
      dimensions: { width: rect.width, height: rect.height },
      state: effectiveState,
      timeMs: elapsed,
    });

    animFrameRef.current = requestAnimationFrame(render);
  }, [audioData, isWebGL, effectiveState, hasAudioActivity, transitionTo]);

  useEffect(() => {
    pluginRef.current = plugin;

    const canvas = canvasRef.current;
    if (canvas) {
      const ctx = canvas.getContext(isWebGL ? 'webgl2' : '2d');
      if (ctx) {
        plugin.init?.(ctx as any);
      }
    }

    stateStartTimeRef.current = performance.now();
    animFrameRef.current = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(animFrameRef.current);
      if (idleTimerRef.current) {
        clearTimeout(idleTimerRef.current);
      }
      plugin.destroy?.();
    };
  }, [plugin, render, isWebGL]);

  return (
    <canvas
      ref={canvasRef}
      className={className}
      style={{ width: '100%', height: '100%' }}
      data-testid="visualizer-canvas"
      data-state={effectiveState}
    />
  );
}
