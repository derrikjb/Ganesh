import { describe, it, expect, beforeEach } from 'vitest';
import { register, get, list, remove, clear } from '../visualizer/registry';
import type { VisualizerPlugin } from '../visualizer/types';

describe('Visualizer Registry', () => {
  const mockPlugin: VisualizerPlugin = {
    name: 'TestPlugin',
    render: () => {},
  };

  const mockPlugin2: VisualizerPlugin = {
    name: 'AnotherPlugin',
    render: () => {},
  };

  beforeEach(() => {
    clear();
  });

  it('registers a plugin', () => {
    register(mockPlugin);
    expect(get('TestPlugin')).toBe(mockPlugin);
  });

  it('retrieves a registered plugin by name', () => {
    register(mockPlugin);
    const result = get('TestPlugin');
    expect(result).toBeDefined();
    expect(result?.name).toBe('TestPlugin');
  });

  it('returns undefined for unregistered plugin', () => {
    expect(get('NonExistent')).toBeUndefined();
  });

  it('lists all registered plugins', () => {
    register(mockPlugin);
    register(mockPlugin2);
    const plugins = list();
    expect(plugins).toHaveLength(2);
    expect(plugins.map((p) => p.name)).toContain('TestPlugin');
    expect(plugins.map((p) => p.name)).toContain('AnotherPlugin');
  });

  it('removes a plugin', () => {
    register(mockPlugin);
    expect(remove('TestPlugin')).toBe(true);
    expect(get('TestPlugin')).toBeUndefined();
  });

  it('returns false when removing non-existent plugin', () => {
    expect(remove('NonExistent')).toBe(false);
  });

  it('clears all plugins', () => {
    register(mockPlugin);
    register(mockPlugin2);
    clear();
    expect(list()).toHaveLength(0);
  });
});
