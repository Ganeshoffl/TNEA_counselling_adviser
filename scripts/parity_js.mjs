/**
 * Runs the JavaScript engine over a set of student profiles and prints the result
 * as JSON, so it can be compared against the Python engine.
 *
 * The engine modules normally read the bundle over HTTP via fetch(). Here the
 * bundle is read from disk and injected through createStore(), which is the only
 * reason that test seam exists.
 */

import { readFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const DATA = join(HERE, '..', 'frontend', 'public', 'data')

const { createStore } = await import('../frontend/src/engine/dataStore.js')
const { recommend } = await import('../frontend/src/engine/engine.js')

function load(name) {
  return JSON.parse(readFileSync(join(DATA, name), 'utf8'))
}

const store = createStore({
  meta: load('meta.json'),
  colleges: load('colleges.json'),
  index: load('college-index.json'),
  cutoffs: load('cutoffs.json'),
  seats: load('seats.json'),
  branches: load('branches.json'),
})

const profiles = JSON.parse(readFileSync(process.argv[2], 'utf8'))
const out = profiles.map((p) => recommend(store, p))
process.stdout.write(JSON.stringify(out))
