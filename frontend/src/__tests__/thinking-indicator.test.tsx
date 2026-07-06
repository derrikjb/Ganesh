import '@testing-library/jest-dom';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, act } from '@testing-library/react';
import { useEffect } from 'react';
import { ThinkingIndicator } from '../components/ThinkingIndicator';
import { AccessibilityProvider, useAccessibility } from '../contexts/AccessibilityContext';
import { VisualizerStateProvider, useVisualizerState } from '../contexts/VisualizerStateContext';
import { VisualizerCanvas } from '../visualizer/VisualizerCanvas';
import { WaveformVisualizer } from '../visualizer/plugins/WaveformVisualizer';
import type { VisualizerPlugin, RenderParams } from '../visualizer/types';

function TestWrapper({ showThinkingIndicator = true, children }: { showThinkingIndicator?: boolean; children: React.ReactNode }) {
  return (
    <AccessibilityProvider>
      <VisualizerStateProvider>
        <Initializer showThinkingIndicator={showThinkingIndicator} />
        {children}
      </VisualizerStateProvider>
    </AccessibilityProvider>
  );
}

function Initializer({ showThinkingIndicator }: { showThinkingIndicator: boolean }) {
  const { setShowThinkingIndicator } = useAccessibility();
  useEffect(() => {
    setShowThinkingIndicator(showThinkingIndicator);
  }, [showThinkingIndicator, setShowThinkingIndicator]);
  return null;
}

let rafCallbacks: ((time: number) => void)[] = [];

function mockCanvasContext() {
  const ctx = {
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
    scale: vi.fn(),
  };

  const originalGetContext = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = vi.fn(() => ctx) as any;

  return {
    ctx,
    restore: () => {
      HTMLCanvasElement.prototype.getContext = originalGetContext;
    },
  };
}

function mockRequestAnimationFrame() {
  const originalRaf = window.requestAnimationFrame;
  const originalCaf = window.cancelAnimationFrame;

  rafCallbacks = [];

  window.requestAnimationFrame = vi.fn((cb: FrameRequestCallback) => {
    rafCallbacks.push(cb);
    return rafCallbacks.length;
  });

  window.cancelAnimationFrame = vi.fn((id: number) => {
    rafCallbacks = rafCallbacks.filter((_, i) => i !== id - 1);
  });

  return {
    fireAll: (timestamp = 0) => {
      const callbacks = [...rafCallbacks];
      rafCallbacks = [];
      callbacks.forEach((cb) => cb(timestamp));
    },
    restore: () => {
      window.requestAnimationFrame = originalRaf;
      window.cancelAnimationFrame = originalCaf;
    },
  };
}

describe('ThinkingIndicator', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it('renders when visible and showThinkingIndicator is true', () => {
    const { getByTestId } = render(
      <TestWrapper showThinkingIndicator={true}>
        <ThinkingIndicator visible={true} />
      </TestWrapper>
    );

    expect(getByTestId('thinking-indicator')).toBeInTheDocument();
    expect(getByTestId('thinking-indicator')).toHaveTextContent('Ganesh is thinking');
  });

  it('does not render when visible is false', () => {
    const { queryByTestId } = render(
      <TestWrapper showThinkingIndicator={true}>
        <ThinkingIndicator visible={false} />
      </TestWrapper>
    );

    expect(queryByTestId('thinking-indicator')).not.toBeInTheDocument();
  });

  it('does not render when showThinkingIndicator is false', () => {
    const { queryByTestId } = render(
      <TestWrapper showThinkingIndicator={false}>
        <ThinkingIndicator visible={true} />
      </TestWrapper>
    );

    expect(queryByTestId('thinking-indicator')).not.toBeInTheDocument();
  });

  it('has role="status" and aria-live="polite" for accessibility', () => {
    const { getByTestId } = render(
      <TestWrapper showThinkingIndicator={true}>
        <ThinkingIndicator visible={true} />
      </TestWrapper>
    );

    const indicator = getByTestId('thinking-indicator');
    expect(indicator).toHaveAttribute('role', 'status');
    expect(indicator).toHaveAttribute('aria-live', 'polite');
  });
});

describe('Thinking Visual State (distinct from IDLE)', () => {
  const dimensions = { width: 400, height: 200 };
  const emptyAudio = new Float32Array(0);

  it('THINKING state produces higher variance than IDLE in WaveformVisualizer', () => {
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

  it('THINKING state has higher opacity than IDLE', () => {
    const createMockCtx = () => {
      const ctx = {
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
        canvas: { width: 400, height: 200 },
      };
      return ctx;
    };

    const idleCtx = createMockCtx();
    const thinkingCtx = createMockCtx();

    WaveformVisualizer.render({
      ctx: idleCtx as any,
      audioData: emptyAudio,
      dimensions,
      state: 'IDLE',
      timeMs: 1000,
    });

    WaveformVisualizer.render({
      ctx: thinkingCtx as any,
      audioData: emptyAudio,
      dimensions,
      state: 'THINKING',
      timeMs: 1000,
    });

    const idleStroke = idleCtx.strokeStyle as string;
    const thinkingStroke = thinkingCtx.strokeStyle as string;

    const idleOpacity = parseFloat(idleStroke.match(/[\d.]+\)$/)?.[0] ?? '0');
    const thinkingOpacity = parseFloat(thinkingStroke.match(/[\d.]+\)$/)?.[0] ?? '0');

    expect(thinkingOpacity).toBeGreaterThanOrEqual(idleOpacity);
  });
});

describe('State Transition on LLM Start', () => {
  const mockPlugin: VisualizerPlugin = {
    name: 'TestPlugin',
    init: vi.fn(),
    render: vi.fn(),
    destroy: vi.fn(),
  };

  const emptyAudio = new Float32Array(0);

  beforeEach(() => {
    vi.clearAllMocks();
    rafCallbacks = [];
  });

  afterEach(() => {
    cleanup();
  });

  it('transitions to THINKING when forced state prop is THINKING', () => {
    const { restore } = mockCanvasContext();
    const { fireAll, restore: restoreRaf } = mockRequestAnimationFrame();
    try {
      render(
        <VisualizerCanvas
          plugin={mockPlugin}
          audioData={emptyAudio}
          state="THINKING"
        />,
      );

      act(() => {
        fireAll(100);
      });

      const canvas = document.querySelector('canvas');
      expect(canvas).toHaveAttribute('data-state', 'THINKING');
    } finally {
      restore();
      restoreRaf();
    }
  });

  it('THINKING state is passed to plugin.render', () => {
    const { restore } = mockCanvasContext();
    const { fireAll, restore: restoreRaf } = mockRequestAnimationFrame();
    try {
      render(
        <VisualizerCanvas
          plugin={mockPlugin}
          audioData={emptyAudio}
          state="THINKING"
        />,
      );

      act(() => {
        fireAll(1000);
      });

      expect(mockPlugin.render).toHaveBeenCalledWith(
        expect.objectContaining({
          state: 'THINKING',
          timeMs: expect.any(Number),
        }),
      );
    } finally {
      restore();
      restoreRaf();
    }
  });

  it('VisualizerStateContext provides state to consumers', () => {
    function StateReader() {
      const { state } = useVisualizerState();
      return <span data-testid="state-value">{state}</span>;
    }

    const { getByTestId } = render(
      <AccessibilityProvider>
        <VisualizerStateProvider>
          <StateReader />
        </VisualizerStateProvider>
      </AccessibilityProvider>,
    );

    expect(getByTestId('state-value').textContent).toBe('IDLE');
  });
});

