import { invoke } from '@tauri-apps/api/core'
import { listen, type UnlistenFn } from '@tauri-apps/api/event'

export type UpdateChannel = 'stable' | 'beta'

export interface UpdateInfo {
  available: boolean
  version: string | null
  current_version: string
  body: string | null
  date: string | null
  download_url: string | null
}

export interface DownloadProgress {
  downloaded: number
  total: number | null
}

export interface UpdateConfig {
  channel: UpdateChannel
  auto_check: boolean
}

export async function checkUpdate(): Promise<UpdateInfo> {
  return await invoke<UpdateInfo>('check_update')
}

export async function downloadUpdate(): Promise<boolean> {
  return await invoke<boolean>('download_update')
}

export async function installUpdate(): Promise<boolean> {
  return await invoke<boolean>('install_update')
}

export async function cancelUpdate(): Promise<boolean> {
  return await invoke<boolean>('cancel_update')
}

export async function getUpdateConfig(): Promise<UpdateConfig> {
  return await invoke<UpdateConfig>('get_update_config')
}

export async function setUpdateConfig(config: UpdateConfig): Promise<UpdateConfig> {
  return await invoke<UpdateConfig>('set_update_config', { config })
}

export function onUpdateAvailable(
  handler: (version: string) => void,
): Promise<UnlistenFn> {
  return listen<string>('update://available', (event) => {
    handler(event.payload)
  })
}

export function onDownloadProgress(
  handler: (progress: DownloadProgress) => void,
): Promise<UnlistenFn> {
  return listen<DownloadProgress>('update://progress', (event) => {
    handler(event.payload)
  })
}

export function onDownloadComplete(
  handler: (size: number) => void,
): Promise<UnlistenFn> {
  return listen<number>('update://download-complete', (event) => {
    handler(event.payload)
  })
}

export function onDownloadCancelled(handler: () => void): Promise<UnlistenFn> {
  return listen('update://cancelled', () => {
    handler()
  })
}
