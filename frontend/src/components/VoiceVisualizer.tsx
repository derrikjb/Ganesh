import { useState, useMemo } from 'react';
import { VisualizerCanvas } from '../visualizer/VisualizerCanvas';
import { list as listPlugins, register } from '../visualizer/registry';
import { WaveformVisualizer } from '../visualizer/plugins/WaveformVisualizer';
import { FreqBarsVisualizer } from '../visualizer/plugins/FreqBarsVisualizer';
import { ParticleVisualizer } from '../visualizer/plugins/ParticleVisualizer';
import { HoloFaceVisualizer } from '../visualizer/plugins/HoloFaceVisualizer';
import type { VisualizerPlugin, AudioData } from '../visualizer/types';

register(WaveformVisualizer);
register(FreqBarsVisualizer);
register(ParticleVisualizer);
register(HoloFaceVisualizer);

function generateMockAudioData(length: number = 512): AudioData {
  const data = new Float32Array(length);
  for (let i = 0; i < length; i++) {
    data[i] = Math.sin(i * 0.05) * 0.5 + (Math.random() - 0.5) * 0.3;
  }
  return data;
}

export function VoiceVisualizer() {
  const plugins = useMemo(() => listPlugins(), []);
  const [activeIndex, setActiveIndex] = useState(0);
  const [audioData] = useState<AudioData>(() => generateMockAudioData());

  const activePlugin: VisualizerPlugin | undefined = plugins[activeIndex];

  if (!activePlugin) {
    return (
      <div className="flex items-center justify-center h-48 bg-bg-secondary rounded-lg border border-border">
        <p className="text-text-muted text-sm">No visualizer plugins registered</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-text-primary">
          Visualizer: <span className="text-accent">{activePlugin.name}</span>
        </span>
        {plugins.length > 1 && (
          <div className="flex gap-2">
            {plugins.map((plugin, index) => (
              <button
                key={plugin.name}
                onClick={() => setActiveIndex(index)}
                className={`px-3 py-1 text-xs rounded-full transition-colors ${
                  index === activeIndex
                    ? 'bg-accent text-text-inverse'
                    : 'bg-bg-tertiary text-text-secondary hover:bg-bg-elevated'
                }`}
              >
                {plugin.name}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="h-48 bg-bg-secondary rounded-lg border border-border overflow-hidden">
        <VisualizerCanvas
          plugin={activePlugin}
          audioData={audioData}
        />
      </div>
    </div>
  );
}
