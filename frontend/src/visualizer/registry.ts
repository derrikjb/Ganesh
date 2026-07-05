import type { VisualizerPlugin } from './types';

const registry = new Map<string, VisualizerPlugin>();

export function register(plugin: VisualizerPlugin): void {
  registry.set(plugin.name, plugin);
}

export function get(name: string): VisualizerPlugin | undefined {
  return registry.get(name);
}

export function list(): VisualizerPlugin[] {
  return Array.from(registry.values());
}

export function remove(name: string): boolean {
  return registry.delete(name);
}

export function clear(): void {
  registry.clear();
}
