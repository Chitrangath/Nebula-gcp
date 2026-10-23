import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'

const frontend = resolve(import.meta.dirname, '..')
const openapi = resolve(frontend, '../backend/openapi.json')
const committed = resolve(frontend, 'src/api/schema.d.ts')
const temporaryDirectory = mkdtempSync(join(tmpdir(), 'nebula-openapi-'))
const generated = join(temporaryDirectory, 'schema.d.ts')

try {
  execFileSync(resolve(frontend, 'node_modules/.bin/openapi-typescript'), [openapi, '--output', generated], {
    cwd: frontend,
    stdio: 'inherit',
  })
  if (readFileSync(generated, 'utf8') !== readFileSync(committed, 'utf8')) {
    throw new Error('Generated browser API types are stale; run npm run generate:api')
  }
  console.log('Browser API types match the committed OpenAPI document')
} finally {
  rmSync(temporaryDirectory, { recursive: true, force: true })
}
