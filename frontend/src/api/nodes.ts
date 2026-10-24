import { requestApi } from './client'
import type { components } from './schema'

export interface ProviderLease {
  job_id: string
  model_id: string
  status: string
  expires_at: string
}

export interface ProviderJob {
  job_id: string
  model_id: string
  status: string
  completed_at: string | null
}

export interface ProviderNode {
  id: string
  gpu_name: string | null
  vram_gb: number | null
  status: 'pending' | 'online' | 'offline' | 'disabled' | string
  last_heartbeat: string | null
  active_leases: number
  worker_signer_address: string | null
  supported_models: string[]
  active_lease: ProviderLease | null
  recent_jobs: ProviderJob[]
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

export type ProviderEarnings = components['schemas']['EarningsResponse']

export interface ProviderDashboardData {
  nodes: ProviderNode[]
  earnings: ProviderEarnings
}

export function listProviderNodes(signal?: AbortSignal): Promise<ProviderNode[]> {
  return requestApi<ProviderNode[]>('/nodes', { method: 'GET', signal })
}

export function registerProviderNode(input: RegisterNodeInput, signal?: AbortSignal): Promise<RegisterNodeResponse> {
  return requestApi<RegisterNodeResponse>('/nodes', { method: 'POST', body: JSON.stringify(input), signal })
}

export async function getProviderDashboard(signal?: AbortSignal): Promise<ProviderDashboardData> {
  const [nodes, earnings] = await Promise.all([
    listProviderNodes(signal),
    requestApi<ProviderEarnings>('/earnings', { method: 'GET', signal }),
  ])
  return { nodes, earnings }
}
