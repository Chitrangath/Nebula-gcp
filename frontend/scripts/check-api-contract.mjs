import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { mkdtempSync, readFileSync, readdirSync, rmSync, statSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'

const frontend = resolve(import.meta.dirname, '..')
const openapi = resolve(frontend, '../backend/openapi.json')
const manifest = JSON.parse(readFileSync(resolve(frontend, '../backend/openapi.manifest.json'), 'utf8'))
const committed = resolve(frontend, 'src/api/schema.d.ts')

const sourceFiles = (directory) =>
  readdirSync(directory)
    .flatMap((name) => {
      const path = join(directory, name)
      return statSync(path).isDirectory() ? sourceFiles(path) : path.endsWith('.py') ? [path] : []
    })
    .sort()

const sourceDigest = createHash('sha256')
for (const path of sourceFiles(resolve(frontend, '../backend/app'))) {
  sourceDigest.update(path.slice(resolve(frontend, '../backend').length + 1).replaceAll('\\', '/'))
  sourceDigest.update('\0')
  sourceDigest.update(readFileSync(path))
  sourceDigest.update('\0')
}
if (sourceDigest.digest('hex') !== manifest.source_sha256) {
  throw new Error('FastAPI source changed after OpenAPI generation; run npm run generate:api')
}
if (createHash('sha256').update(readFileSync(openapi)).digest('hex') !== manifest.openapi_sha256) {
  throw new Error('Committed OpenAPI document does not match its generation manifest')
}

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
