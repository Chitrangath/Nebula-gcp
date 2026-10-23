import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const frontend = resolve(import.meta.dirname, '..')
const artifact = JSON.parse(readFileSync(resolve(frontend, 'src/contracts/nebula.json'), 'utf8'))
const backendAbi = JSON.parse(readFileSync(resolve(frontend, '../backend/app/nebula_abi.json'), 'utf8'))
const backendMetadata = JSON.parse(
  readFileSync(resolve(frontend, '../backend/app/nebula_artifact.json'), 'utf8'),
)

const expected = { abi: backendAbi, metadata: backendMetadata }
if (JSON.stringify(artifact) !== JSON.stringify(expected)) {
  throw new Error('Frontend contract artifact is stale or contains unexpected fields')
}
console.log('Frontend contract artifact matches the canonical backend artifacts')
