/**
 * Visualizer Plugin Interface
 *
 * Defines the contract for audio visualization plugins.
 * Each plugin provides its own rendering logic via Canvas 2D.
 */

/**
 * Audio data sample: amplitude values in range [-1, 1].
 */
export type AudioData = Float32Array | number[];

/**
 * Canvas rendering context (2D only for now).
 */
export type RenderContext = CanvasRenderingContext2D;

/**
 * Dimensions of the canvas.
 */
export interface Dimensions {
  width: number;
  height: number;
}

/**
 * Render context passed to plugin.render().
 */
export interface RenderParams {
  ctx: RenderContext;
  audioData: AudioData;
  dimensions: Dimensions;
}

/**
 * VisualizerPlugin interface.
 *
 * - `name`: Human-readable identifier.
 * - `init()`: Called once when the plugin is activated. Use for setup.
 * - `render()`: Called every frame via requestAnimationFrame.
 * - `destroy()`: Called when the plugin is deactivated. Clean up resources.
 */
export interface VisualizerPlugin {
  name: string;
  init?(ctx: RenderContext): void;
  render(params: RenderParams): void;
  destroy?(): void;
}
