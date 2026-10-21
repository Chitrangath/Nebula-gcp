export const API_BASE_URL = '/api/v1'

export const ARBITRUM_SEPOLIA_CHAIN_ID = 421614

export const ARBITRUM_SEPOLIA_EXPLORER = 'https://sepolia.arbiscan.io'

export const CONTRACT_ADDRESS = import.meta.env.VITE_CONTRACT_ADDRESS || ''

export const SUPPORTED_MODELS = [
  { id: 'yolov5', name: 'YOLOv5', description: 'Object detection', price: 0.05, inputType: 'image', maxSizeMb: 25 },
  { id: 'bert-base', name: 'BERT-Base', description: 'Text classification', price: 0.03, inputType: 'text', maxSizeMb: 10 },
  { id: 'resnet50', name: 'ResNet50', description: 'Image classification', price: 0.05, inputType: 'image', maxSizeMb: 25 },
  { id: 'whisper-tiny', name: 'Whisper Tiny', description: 'Speech to text', price: 0.10, inputType: 'audio', maxSizeMb: 50 },
] as const

export const JOB_STATUSES = {
  PENDING_BLOCKCHAIN: 'pending_blockchain',
  QUEUED: 'queued',
  ASSIGNED: 'assigned',
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed',
} as const
