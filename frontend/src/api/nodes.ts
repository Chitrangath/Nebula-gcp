import { requestApi } from './client'

export interface ProviderNode {
  id: string
  gpu_name: string | null
  vram_gb: number | null
  status: 'pending' | 'online' | 'offline' | 'disabled' | string
  last_heartbeat: string | null
  active_leases: number
  worker_signer_address: string | null
}

export interface RegisterNodeInput {
  gpu_name?: string
  vram_gb?: number
  location?: string
  worker_signer_address?: string
}

export interface RegisterNodeResponse {
  node_id: string
  api_key: string
  status: string
}

export function listProviderNodes(signal?: AbortSignal): Promise<ProviderNode[]> {
  return requestApi<ProviderNode[]>('/nodes', { method: 'GET', signal })
}

export function registerProviderNode(input: RegisterNodeInput, signal?: AbortSignal): Promise<RegisterNodeResponse> {
  return requestApi<RegisterNodeResponse>('/nodes', { method: 'POST', body: JSON.stringify(input), signal })
}
