/**
 * Admission probability. Port of backend/app/probability.py.
 *
 * Combines two officially published facts:
 *   1. the closing rank actually allotted for that college + branch + community in
 *      the reference round, from the per-candidate allotment lists;
 *   2. the seats still vacant going into the round, from the round-wise vacancy
 *      files. Zero vacancy is a hard stop, not a small number.
 */

import { pyRound, clamp } from './pyCompat.js'
import { ROUNDS_WITH_OFFICIAL_DATA } from './dataStore.js'

/**
 * Controls how sharply probability falls as the candidate's rank passes the
 * closing rank. At rel === 0 (rank exactly equal to the closing rank) probability
 * is 0.5, which is the honest reading of sitting precisely on the boundary.
 */
const RANK_SPREAD = 0.12

const METHOD =
  'Logistic in the relative gap between your rank and the official closing rank, ' +
  'multiplied by a discount when very few seats remain. Estimate only.'

function availabilityFactor(seats) {
  if (seats <= 0) return 0.0
  if (seats === 1) return 0.7
  if (seats === 2) return 0.8
  if (seats <= 5) return 0.9
  return 1.0
}

function logistic(rel) {
  const exponent = rel / RANK_SPREAD
  if (exponent > 700) return 0.0
  if (exponent < -700) return 1.0
  return 1.0 / (1.0 + Math.exp(exponent))
}

export function estimate(store, collegeCode, branchCode, community, studentRank, targetRound) {
  const [cutoff, cutoffRound] = store.referenceCutoff(
    collegeCode,
    branchCode,
    community,
    targetRound
  )
  const seats = store.seatsAvailable(collegeCode, branchCode, community, targetRound)

  if (!cutoff) return null

  const closingRank = cutoff.closing_rank
  const openingRank = cutoff.opening_rank

  const rel = (studentRank - closingRank) / Math.max(closingRank, 1)
  const pRank = logistic(rel)

  const notes = []
  let probability
  let availabilityState
  let factor

  if (seats === null) {
    probability = pRank
    availabilityState = 'unknown'
    factor = 1.0
    notes.push(
      'TNEA published no vacancy figure for this community in this branch, so only ' +
        'the closing-rank evidence is reflected.'
    )
  } else {
    factor = availabilityFactor(seats)
    probability = pRank * factor
    if (seats <= 0) {
      availabilityState = 'none'
      notes.push(
        'No seats of this community remained vacant going into this round, so this ' +
          'seat cannot be allotted regardless of rank.'
      )
    } else if (seats <= 5) {
      availabilityState = 'scarce'
      notes.push(
        `Only ${seats} seat(s) of this community were vacant going into this round.`
      )
    } else {
      availabilityState = 'available'
    }
  }

  if (studentRank <= openingRank) {
    notes.push(
      `Your rank is ahead of the best rank allotted here in round ${cutoffRound} ` +
        `(rank ${openingRank}).`
    )
  } else if (studentRank <= closingRank) {
    notes.push(
      `Your rank falls inside the range actually allotted here in round ${cutoffRound} ` +
        `(ranks ${openingRank} to ${closingRank}).`
    )
  } else {
    const gap = studentRank - closingRank
    notes.push(
      `Your rank is ${gap.toLocaleString('en-US')} behind the last rank allotted here ` +
        `in round ${cutoffRound} (rank ${closingRank}).`
    )
  }

  if (!ROUNDS_WITH_OFFICIAL_DATA.includes(targetRound)) {
    notes.push(
      `Round ${targetRound} has not been published by TNEA, so round ${cutoffRound} ` +
        'evidence is used as the closest available benchmark.'
    )
  } else if (cutoffRound !== targetRound) {
    notes.push(
      `No allotments were recorded here in round ${targetRound}; round ${cutoffRound} ` +
        'evidence is used instead.'
    )
  }

  return {
    probability: pyRound(clamp(probability, 0.0, 1.0), 4),
    closing_rank: closingRank,
    opening_rank: openingRank,
    closing_mark: cutoff.closing_mark ?? null,
    evidence_round: cutoffRound,
    seats_allotted_in_evidence_round: cutoff.seats_allotted ?? null,
    seats_vacant_entering_round: seats,
    availability: availabilityState,
    availability_factor: factor,
    rank_component: pyRound(pRank, 4),
    notes,
    method: METHOD,
  }
}
