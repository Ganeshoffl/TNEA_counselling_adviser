/**
 * Loads the static data bundle and exposes the lookups the engine needs.
 *
 * Mirrors backend/app/data_store.py, with one deliberate difference: nothing is
 * DERIVED here. Seats-available-before-each-round (including the reconstructed
 * pre-round-1 figure) is computed once in scripts/build_static_bundle.py and
 * shipped ready to use, so that derivation has a single implementation.
 */

export const COMMUNITIES = ['OC', 'BC', 'BCM', 'MBC', 'SC', 'SCA', 'ST']
export const ROUNDS_WITH_OFFICIAL_DATA = [1, 2, 3]
export const SUPPORTED_ROUNDS = [1, 2, 3, 4]

// Vite injects import.meta.env; plain Node (used by the parity harness) does not,
// so this is read defensively rather than assumed.
const BASE =
  (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.BASE_URL) || '/'

function dataUrl(name) {
  return `${BASE}data/${name}`.replace(/([^:])\/\/+/g, '$1/')
}

async function loadJson(name) {
  const response = await fetch(dataUrl(name))
  if (!response.ok) {
    throw new Error(`Could not load ${name} (HTTP ${response.status})`)
  }
  return response.json()
}

let storePromise = null

export function lookupKey(collegeCode, branchCode, community) {
  return `${collegeCode}|${branchCode}|${community}`
}

class DataStore {
  constructor({ meta, colleges, index, cutoffs, seats, branches }) {
    this.meta = meta
    this.colleges = colleges
    this.branches = branches
    this.cutoffs = cutoffs
    this.seats = seats

    this.byCode = new Map(colleges.map((c) => [c.college_code, c]))
    this.indexByCode = new Map(index.map((c) => [c.college_code, c]))
    this.index = index
  }

  college(code) {
    return this.byCode.get(Number(code)) || null
  }

  collegeFromIndex(code) {
    return this.indexByCode.get(Number(code)) || null
  }

  branchName(code) {
    return this.branches[code] || code
  }

  recommendableColleges() {
    return this.colleges
  }

  /**
   * Closing-rank record that best represents what it takes to be allotted this
   * seat in `targetRound`. Preference order matches the Python implementation:
   *   1. the same round, when TNEA published it;
   *   2. otherwise the latest earlier round, since closing ranks drift weaker;
   *   3. otherwise the earliest later round.
   */
  referenceCutoff(collegeCode, branchCode, community, targetRound) {
    const byRound = this.cutoffs[lookupKey(collegeCode, branchCode, community)]
    if (!byRound) return [null, null]

    const target = String(targetRound)
    if (byRound[target]) return [byRound[target], targetRound]

    const rounds = Object.keys(byRound).map(Number)
    const earlier = rounds.filter((r) => r < targetRound)
    if (earlier.length) {
      const r = Math.max(...earlier)
      return [byRound[String(r)], r]
    }
    const r = Math.min(...rounds)
    return [byRound[String(r)], r]
  }

  /** Seats available going INTO the given round, or null when not published. */
  seatsAvailable(collegeCode, branchCode, community, targetRound) {
    const byRound = this.seats[lookupKey(collegeCode, branchCode, community)]
    if (!byRound) return null
    const seats = byRound[String(targetRound)]
    return seats === undefined ? null : seats
  }
}

export function getStore() {
  if (!storePromise) {
    storePromise = Promise.all([
      loadJson('meta.json'),
      loadJson('colleges.json'),
      loadJson('college-index.json'),
      loadJson('cutoffs.json'),
      loadJson('seats.json'),
      loadJson('branches.json'),
    ]).then(
      ([meta, colleges, index, cutoffs, seats, branches]) =>
        new DataStore({ meta, colleges, index, cutoffs, seats, branches })
    )
  }
  return storePromise
}

/** Test seam: lets the parity harness inject a bundle read from disk. */
export function createStore(bundle) {
  return new DataStore(bundle)
}
