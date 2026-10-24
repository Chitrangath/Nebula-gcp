import type { components } from './schema'
import { requestApi } from './client'

export type NetworkSnapshot = components['schemas']['NetworkSnapshotResponse']
export type NetworkNode = components['schemas']['NetworkNodeResponse']

export function getNetworkSnapshot(signal?: AbortSignal): Promise<NetworkSnapshot> {
  return requestApi<NetworkSnapshot>('/network', { method: 'GET', signal })
}
