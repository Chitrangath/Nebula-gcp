import type { components } from '../api/schema'
import { requestApi, requestApiResponse } from '../api/client'
import type { BackendJob, Hex, JobBackend, JobSubmissionRequest } from './submitJob'
import type { Job } from './lifecycle'

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

export interface ResNetJobResult {
  model_id: 'resnet50'
  top_k: Array<{ index: number; probability_hex: string }>
}

export interface BertJobResult {
  model_id: 'bert-base'
  stars: number
  scores: Array<{ stars: number; probability_hex: string }>
}

export type JobResult = ResNetJobResult | BertJobResult

const formatMimeTypes: Record<string, string> = {
  png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', txt: 'text/plain',
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

export async function listJobs(signal?: AbortSignal): Promise<Job[]> {
  const response = await requestApi<{ jobs: Job[] }>('/jobs', { method: 'GET', signal })
  return response.jobs
}

export async function getJob(jobId: string, signal?: AbortSignal): Promise<Job> {
  return requestApi<Job>(`/jobs/${encodeURIComponent(jobId)}`, { method: 'GET', signal })
}

export async function downloadJobResult(jobId: string, signal?: AbortSignal): Promise<Blob> {
  const response = await requestApiResponse(`/jobs/${encodeURIComponent(jobId)}/result`, { method: 'GET', signal })
  return response.blob()
}

function parseJobResult(value: unknown): JobResult {
  if (!value || typeof value !== 'object' || !('model_id' in value)) throw new Error('Result has an invalid format')
  const result = value as Record<string, unknown>
  if (result.model_id === 'resnet50' && Array.isArray(result.top_k) && result.top_k.length >= 1 && result.top_k.length <= 5 && result.top_k.every((item) => {
    if (!item || typeof item !== 'object') return false
    const row = item as Record<string, unknown>
    return typeof row.index === 'number' && Number.isInteger(row.index) && row.index >= 0 &&
      typeof row.probability_hex === 'string' && isProbabilityHex(row.probability_hex)
  }) && new Set(result.top_k.map((item) => (item as Record<string, unknown>).index)).size === result.top_k.length) return {
    model_id: 'resnet50',
    top_k: result.top_k.map((item) => ({ index: item.index as number, probability_hex: item.probability_hex as string })),
  }
  if (result.model_id === 'bert-base' && typeof result.stars === 'number' && Number.isInteger(result.stars) && result.stars >= 1 && result.stars <= 5 && Array.isArray(result.scores) && result.scores.length === 5 && result.scores.every((item) => {
    if (!item || typeof item !== 'object') return false
    const row = item as Record<string, unknown>
    return typeof row.stars === 'number' && Number.isInteger(row.stars) && row.stars >= 1 && row.stars <= 5 &&
      typeof row.probability_hex === 'string' && isProbabilityHex(row.probability_hex)
  }) && new Set(result.scores.map((item) => (item as Record<string, unknown>).stars)).size === 5) return {
    model_id: 'bert-base',
    stars: result.stars,
    scores: result.scores.map((item) => ({ stars: item.stars as number, probability_hex: item.probability_hex as string })),
  }
  throw new Error('Result has an invalid format')
}

export async function getJobResult(jobId: string, signal?: AbortSignal): Promise<JobResult> {
  const response = await requestApiResponse(`/jobs/${encodeURIComponent(jobId)}/result`, { method: 'GET', signal })
  try {
    return parseJobResult(JSON.parse(await response.text()) as unknown)
  } catch (error) {
    if (error instanceof Error && error.message === 'Result has an invalid format') throw error
    throw new Error('Result has an invalid format')
  }
}

export function probabilityFromHexFloat(value: string): number | null {
  const match = /^(-?)0x([0-9a-f]+)(?:\.([0-9a-f]*))?p([+-]?\d+)$/i.exec(value)
  if (!match) return null
  const integer = Number.parseInt(match[2], 16)
  const fractionDigits = match[3] ?? ''
  let fraction = 0
  for (let index = 0; index < fractionDigits.length; index += 1) {
    fraction += Number.parseInt(fractionDigits[index], 16) / (16 ** (index + 1))
  }
  const number = (integer + fraction) * (2 ** Number.parseInt(match[4], 10))
  const signed = match[1] ? -number : number
  return Number.isFinite(signed) ? signed : null
}

function isProbabilityHex(value: string): boolean {
  const probability = probabilityFromHexFloat(value)
  return probability !== null && probability >= 0 && probability <= 1
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
