/**
 * Data access for the browser-only build.
 *
 * This module keeps the same function signatures the components already used when
 * the app talked to the FastAPI backend, so the UI is unchanged. The difference is
 * that everything now runs locally against the static bundle in public/data, which
 * is what lets the app be hosted on GitHub Pages with no server at all.
 *
 * The Python backend in backend/ is still maintained and still exposes the same
 * endpoints for programmatic use; scripts/verify_parity.sh asserts that both
 * implementations return identical results.
 */

import { COMMUNITIES, ROUNDS_WITH_OFFICIAL_DATA, SUPPORTED_ROUNDS, getStore } from './engine/dataStore.js'
import { MODE_DEFINITIONS, recommend } from './engine/engine.js'
import { WEIGHTS } from './engine/scoring.js'
import { scoreCollege } from './engine/scoring.js'

export async function getMeta() {
  const store = await getStore()
  const meta = store.meta
  return {
    admission_year: meta.admission_year,
    communities: COMMUNITIES,
    supported_rounds: SUPPORTED_ROUNDS,
    rounds_with_official_data: ROUNDS_WITH_OFFICIAL_DATA,
    college_count: meta.college_count,
    recommendable_count: meta.recommendable_count,
    data_confidence_counts: meta.data_confidence_counts,
    data_confidence_legend: meta.data_confidence_legend,
    sources: meta.sources,
    scoring_weights: WEIGHTS,
  }
}

export async function getModes() {
  return {
    modes: MODE_DEFINITIONS,
    note:
      'The three modes map onto the confirmation options published in the official ' +
      'TNEA counselling procedure, so the downside of each is the downside the ' +
      'procedure actually defines.',
  }
}

export async function getBranches() {
  const store = await getStore()
  return { branches: store.branches }
}

export async function getColleges({ recommendableOnly = true, search = null, limit = 500 } = {}) {
  const store = await getStore()
  const needle = search ? search.trim().toLowerCase() : null

  const source = recommendableOnly ? store.recommendableColleges() : store.index
  const items = []

  for (const entry of source) {
    if (needle && !entry.official_name.toLowerCase().includes(needle)) continue

    const full = store.college(entry.college_code)
    const quality = full ? scoreCollege(full) : null

    items.push({
      college_code: entry.college_code,
      display_name: entry.display_name,
      official_name: entry.official_name,
      city: full?.city ?? null,
      institution_type: entry.institution_type,
      data_confidence: entry.data_confidence,
      recommendable: entry.recommendable ?? true,
      branches: entry.branches || [],
      nirf: full?.nirf ?? null,
      fee_band: full?.fee_band ?? null,
      quality_score: quality?.quality_score ?? null,
      evidence_completeness: quality?.evidence_completeness ?? null,
    })
  }

  items.sort((a, b) => {
    const aNull = a.quality_score === null
    const bNull = b.quality_score === null
    if (aNull !== bNull) return aNull ? 1 : -1
    return (b.quality_score || 0) - (a.quality_score || 0)
  })

  return { count: items.length, colleges: items.slice(0, limit) }
}

export async function postRecommend(payload) {
  const store = await getStore()
  return recommend(store, payload)
}
