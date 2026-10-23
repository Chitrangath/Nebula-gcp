import type { components } from '../api/schema'
import { requestApi } from '../api/client'
import type { BackendJob, Hex, JobBackend, JobSubmissionRequest } from './submitJob'

type JobResponse = components['schemas']['JobResponse']
type ConfirmEscrowResponse = components['schemas']['ConfirmEscrowResponse']

export interface SupportedModel {
  id: string
  name: string
  input_type: string
  supported_formats: string[]
  max_input_size_mb?: number
  price_base_units: string
}

const formatMimeTypes: Record<string, string> = {
  png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg',
}

export function modelMimeTypes(model: SupportedModel): string[] {
  return [...new Set(model.supported_formats.map((format) => formatMimeTypes[format.toLowerCase()] ?? format))]
}

function parseModel(value: unknown): SupportedModel {
  if (!value || typeof value !== 'object') throw new Error('Invalid model response')
  const model = value as Partial<SupportedModel>
  if (typeof model.id !== 'string' || typeof model.name !== 'string' || typeof model.input_type !== 'string' ||
      !Array.isArray(model.supported_formats) || !model.supported_formats.every((format) => typeof format === 'string') ||
      typeof model.price_base_units !== 'string' ||
      (model.max_input_size_mb !== undefined && (!Number.isFinite(model.max_input_size_mb) || model.max_input_size_mb <= 0))) {
    throw new Error('Invalid model response')
  }
  return model as SupportedModel
}

export async function listSupportedModels(signal?: AbortSignal): Promise<SupportedModel[]> {
  const response = await requestApi<unknown[]>('/models', { method: 'GET', signal })
  return response.map(parseModel)
}

function toBackendJob(job: JobResponse): BackendJob {
  const fingerprint = job.fingerprint?.replace(/^0x/, '')
  if (!fingerprint || !/^[0-9a-fA-F]{64}$/.test(fingerprint) || !/^0x[0-9a-fA-F]{64}$/.test(job.chain_job_id)) {
    throw new Error('Job is missing chain identity')
  }
  return {
    id: job.id,
    chain_job_id: job.chain_job_id as Hex,
    fingerprint: `0x${fingerprint}`,
    price_base_units: job.price_base_units,
  }
}

export const jobBackend: JobBackend = {
  async createJob(request: JobSubmissionRequest, idempotencyKey: string, signal?: AbortSignal): Promise<BackendJob> {
    const body = new FormData()
    body.set('model_id', request.modelId)
    body.set('deadline', request.deadline)
    body.set('input_file', request.input)
    const response = await requestApi<JobResponse>('/jobs', {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey },
      body,
      signal,
    })
    return toBackendJob(response)
  },

  async confirmEscrow(jobId: string, transactionHash: Hex, signal?: AbortSignal): Promise<{ status: string }> {
    const body: components['schemas']['ConfirmEscrowRequest'] = { tx_hash: transactionHash }
    return requestApi<ConfirmEscrowResponse>(`/jobs/${encodeURIComponent(jobId)}/confirm-escrow`, {
      method: 'POST',
      body: JSON.stringify(body),
      signal,
    })
  },
}
