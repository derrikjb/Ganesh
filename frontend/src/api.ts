import { invoke } from '@tauri-apps/api/core'

export async function getSidecarPort(): Promise<number> {
  return await invoke<number>('get_sidecar_port')
}

export async function sidecarFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const port = await getSidecarPort()
  if (port === undefined || port === null) {
    throw new Error('sidecar port not available')
  }
  const url = `http://127.0.0.1:${port}${path}`
  return await fetch(url, init)
}

export async function checkSidecarHealth(): Promise<boolean> {
  try {
    const res = await sidecarFetch('/health')
    return res.ok
  } catch {
    return false
  }
}
