/**
 * Recommendation engine. Port of backend/app/engine.py.
 *
 * The three modes correspond to the confirmation options the Directorate of
 * Technical Education actually offers a candidate holding an allotment:
 *
 *   Accept and Upward   The procedure confirms the previously allotted choice if no
 *                       better choice arrives, so the current seat is a floor.
 *   Decline and Upward  A failed upgrade moves the candidate to the next round
 *                       WITHOUT the declined seat. The downside is real.
 *
 * Safe and Optimal therefore rely on Accept and Upward; Risk relies on declining.
 */

import { estimate } from './probability.js'
import { scoreCollege } from './scoring.js'
import { ROUNDS_WITH_OFFICIAL_DATA } from './dataStore.js'
import { pyFixed, pyPercent0, pyRound } from './pyCompat.js'

const SAFE_MIN = 0.8
const OPTIMAL_MIN = 0.45
const RISK_MIN = 0.12

const SAFE_UPLIFT = 3.0
const OPTIMAL_UPLIFT = 5.0
const RISK_UPLIFT = 8.0

const UPLIFT_NEEDED = { safe: SAFE_UPLIFT, optimal: OPTIMAL_UPLIFT, risk: RISK_UPLIFT }

export const MODE_DEFINITIONS = {
  safe: {
    label: 'Safe',
    probability_band: '80% and above',
    objective:
      'Highest college quality among seats you are very likely to actually get.',
    tnea_mechanism: 'Accept and Upward',
    downside:
      'Minimal. Under Accept and Upward the official procedure confirms your ' +
      'existing allotment if no better choice arrives, so your current seat is a floor.',
  },
  optimal: {
    label: 'Optimal',
    probability_band: '45% to 80%',
    objective:
      'Best expected value, balancing how much better the college is against how ' +
      'likely you are to get it.',
    tnea_mechanism: 'Accept and Upward',
    downside:
      'Low. Still pursued through Accept and Upward, so a failed upgrade leaves you ' +
      'with your current seat.',
  },
  risk: {
    label: 'Risk',
    probability_band: '12% to 45%',
    objective:
      'Highest quality colleges that are a genuine stretch for your rank. Large gain ' +
      'if it lands.',
    tnea_mechanism: 'Decline and Upward, or declining to a later round',
    downside:
      'Real. If you decline your seat and the upgrade does not arrive, the official ' +
      'procedure moves you to the next round without the declined seat, and you may ' +
      'end up with a weaker college or none.',
  },
}

const DISCLAIMER =
  'Probabilities are estimates derived from officially published TNEA 2026 closing ' +
  'ranks and round-wise vacancy figures. They are not guarantees. Actual allotment ' +
  'also depends on your own choice ordering and on how other candidates behave in ' +
  'the same round. Always confirm against tneaonline.org.'

const UNSCORED_EXPLANATION =
  'These colleges are reachable for your rank and their NIRF rank band is verified, ' +
  'but NIRF publishes no placement or laboratory figures for them (it publishes ' +
  'per-institute data only down to rank 200). They are listed so you can see them, ' +
  'without a quality score that would look comparable to a fully measured college.'

function candidateRows(store, studentRank, community, targetRound, branchFilter) {
  const scored = []
  const unscored = []

  for (const college of store.recommendableColleges()) {
    const code = college.college_code
    const quality = scoreCollege(college)
    const scorable = quality.scorable === true

    for (const branch of college.branches || []) {
      if (branchFilter && !branchFilter.has(branch)) continue
      const admission = estimate(store, code, branch, community, studentRank, targetRound)
      if (!admission) continue
      const row = {
        college_code: code,
        college_name: college.display_name,
        official_college_name: college.official_name,
        city: college.city ?? null,
        institution_type: college.institution_type,
        data_confidence: college.data_confidence,
        nirf: college.nirf ?? null,
        fee_band: college.fee_band,
        branch_code: branch,
        branch_name: store.branchName(branch),
        quality,
        admission,
      }
      ;(scorable ? scored : unscored).push(row)
    }
  }

  return [scored, unscored]
}

function currentAllotmentView(store, collegeCode, branchCode) {
  if (!collegeCode) return null

  const indexed = store.collegeFromIndex(collegeCode)
  if (!indexed) {
    return {
      known: false,
      college_code: Number(collegeCode),
      message:
        `College code ${collegeCode} is not in the official TNEA 2026 general ` +
        'academic list.',
    }
  }

  const full = store.college(collegeCode)
  const quality = full ? scoreCollege(full) : null
  const scorable = quality && quality.scorable

  return {
    known: true,
    college_code: Number(collegeCode),
    college_name: indexed.display_name,
    official_college_name: indexed.official_name,
    branch_code: branchCode ?? null,
    branch_name: branchCode ? store.branchName(branchCode) : null,
    institution_type: indexed.institution_type,
    data_confidence: indexed.data_confidence,
    quality: quality,
    quality_unavailable_reason: scorable
      ? null
      : full
        ? quality.unscorable_reason
        : 'This college has no NIRF presence, so no verified placement, laboratory ' +
          'or ranking data exists for it. Its quality cannot be scored, and this tool ' +
          'will not invent a number for it.',
  }
}

function expectedValue(mode, targetQuality, probability, currentQuality) {
  if (mode === 'safe' || mode === 'optimal') {
    // Accept and Upward: a failed upgrade leaves the existing seat intact.
    if (currentQuality === null || currentQuality === undefined) {
      return {
        expected_quality: null,
        explanation:
          'Expected value needs the quality of your current seat, which cannot be ' +
          'scored for that college.',
      }
    }
    const ev = probability * targetQuality + (1 - probability) * currentQuality
    return {
      expected_quality: pyRound(ev, 2),
      fallback_quality: pyRound(currentQuality, 2),
      explanation:
        'Under Accept and Upward a failed upgrade keeps your current seat, so the ' +
        'downside is your current college, not nothing.',
    }
  }
  return {
    expected_quality: null,
    explanation:
      'Not quantified. This path involves declining your seat, and the official ' +
      'procedure then moves you to the next round without it. The outcome of that ' +
      "round depends on other candidates' choices and cannot be estimated " +
      'honestly from published data.',
  }
}

function pick(mode, rows, limit) {
  let pool
  if (mode === 'safe') {
    pool = rows.filter((r) => r.admission.probability >= SAFE_MIN)
    pool.sort(
      (a, b) =>
        b.quality.quality_score - a.quality.quality_score ||
        b.admission.probability - a.admission.probability
    )
  } else if (mode === 'optimal') {
    pool = rows.filter(
      (r) => r.admission.probability >= OPTIMAL_MIN && r.admission.probability < SAFE_MIN
    )
    pool.sort(
      (a, b) =>
        b.quality.quality_score * b.admission.probability -
        a.quality.quality_score * a.admission.probability
    )
  } else {
    pool = rows.filter(
      (r) => r.admission.probability >= RISK_MIN && r.admission.probability < OPTIMAL_MIN
    )
    pool.sort(
      (a, b) =>
        b.quality.quality_score - a.quality.quality_score ||
        b.admission.probability - a.admission.probability
    )
  }
  return pool.slice(0, limit)
}

function verdict(mode, picks, current) {
  const upliftNeeded = UPLIFT_NEEDED[mode]
  const mechanism = MODE_DEFINITIONS[mode].tnea_mechanism

  if (!picks.length) {
    return {
      action: 'stay',
      headline: 'No option in this band',
      reasoning:
        'No college and branch combination falls in this probability band for your ' +
        'rank, community and round, so there is nothing to move up to here.',
      tnea_mechanism: mechanism,
    }
  }

  const best = picks[0]
  const targetQuality = best.quality.quality_score
  const probability = best.admission.probability

  let currentQuality = null
  if (
    current &&
    current.quality &&
    current.quality.quality_score !== null &&
    current.quality.quality_score !== undefined
  ) {
    currentQuality = current.quality.quality_score
  }

  const ev = expectedValue(mode, targetQuality, probability, currentQuality)
  const target = `${best.college_name} - ${best.branch_name}`

  if (current === null) {
    return {
      action: 'pursue',
      headline: 'No current allotment given, so every option here is a gain',
      target,
      target_quality: targetQuality,
      probability,
      expected_value: ev,
      tnea_mechanism: mechanism,
      reasoning:
        'You did not provide a current allotment, so this is simply the best option ' +
        'in this band for your rank and community.',
    }
  }

  if (currentQuality === null) {
    return {
      action: 'compare_not_possible',
      headline: 'Cannot compare against your current seat',
      target,
      target_quality: targetQuality,
      probability,
      expected_value: ev,
      tnea_mechanism: mechanism,
      reasoning:
        'Your current college has no verified NIRF, placement or laboratory data, so ' +
        'a like-for-like quality comparison is not possible. The option shown is the ' +
        'strongest in this band, but whether it is an upgrade for you cannot be ' +
        'established from official data.',
    }
  }

  const uplift = targetQuality - currentQuality

  if (uplift < upliftNeeded) {
    return {
      action: 'stay',
      headline: 'Stay with your current allotment',
      target,
      target_quality: targetQuality,
      current_quality: currentQuality,
      quality_uplift: pyRound(uplift, 2),
      probability,
      expected_value: ev,
      tnea_mechanism: mechanism,
      reasoning:
        `The best option in this band scores ${pyFixed(targetQuality, 1)} against your ` +
        `current ${pyFixed(currentQuality, 1)}, a gain of only ${pyFixed(uplift, 1)} ` +
        `points. That is below the ${pyFixed(upliftNeeded, 0)}-point threshold this ` +
        'mode uses, so moving is not worth the effort or the fee.',
    }
  }

  if (mode === 'risk') {
    return {
      action: 'move_up_with_risk',
      headline: 'Worth a gamble, with a real downside',
      target,
      target_quality: targetQuality,
      current_quality: currentQuality,
      quality_uplift: pyRound(uplift, 2),
      probability,
      expected_value: ev,
      tnea_mechanism: mechanism,
      reasoning:
        `${best.college_name} scores ${pyFixed(targetQuality, 1)} against your current ` +
        `${pyFixed(currentQuality, 1)}, a gain of ${pyFixed(uplift, 1)} points, but the ` +
        `estimated chance is only ${pyPercent0(probability)}. Pursuing it means ` +
        'declining your current seat, and if the upgrade does not arrive the official ' +
        'procedure moves you to the next round without it.',
    }
  }

  return {
    action: 'move_up',
    headline: 'Move up',
    target,
    target_quality: targetQuality,
    current_quality: currentQuality,
    quality_uplift: pyRound(uplift, 2),
    probability,
    expected_value: ev,
    tnea_mechanism: mechanism,
    reasoning:
      `${best.college_name} scores ${pyFixed(targetQuality, 1)} against your current ` +
      `${pyFixed(currentQuality, 1)}, a gain of ${pyFixed(uplift, 1)} points, with an ` +
      `estimated ${pyPercent0(probability)} chance. Because Accept and Upward confirms ` +
      'your existing allotment if no better choice arrives, your current seat is ' +
      'protected while you try.',
  }
}

export function recommend(
  store,
  {
    cutoff_mark,
    rank,
    community,
    current_round,
    current_college_code = null,
    current_branch_code = null,
    branches = null,
    limit = 10,
  }
) {
  const branchFilter = branches && branches.length ? new Set(branches) : null
  const [rows, unscored] = candidateRows(
    store,
    rank,
    community,
    current_round,
    branchFilter
  )
  const current = currentAllotmentView(store, current_college_code, current_branch_code)

  const modes = {}
  for (const mode of ['safe', 'optimal', 'risk']) {
    const picks = pick(mode, rows, limit)
    modes[mode] = {
      definition: MODE_DEFINITIONS[mode],
      verdict: verdict(mode, picks, current),
      options: picks,
      option_count: picks.length,
    }
  }

  unscored.sort((a, b) => b.admission.probability - a.admission.probability)
  const reachableUnscored = unscored
    .filter((r) => r.admission.probability >= RISK_MIN)
    .slice(0, limit)

  const warnings = []
  if (!ROUNDS_WITH_OFFICIAL_DATA.includes(current_round)) {
    warnings.push(
      `TNEA has published rounds [${ROUNDS_WITH_OFFICIAL_DATA.join(', ')}] for the 2026 ` +
        `general academic stream. Round ${current_round} is a forward simulation that ` +
        'reuses the most recent published round as its benchmark.'
    )
  }
  if (current_round === 1) {
    warnings.push(
      'Seats available before round 1 are reconstructed as (seats vacant after round 1 ' +
        "+ seats allotted in round 1), because TNEA's only online pre-round seat matrix " +
        'is from 2023.'
    )
  }
  if (!rows.length) {
    warnings.push(
      'No college and branch combination had official closing-rank evidence for this ' +
        'community and round, so no recommendation could be produced.'
    )
  }

  return {
    input: {
      cutoff_mark,
      rank,
      community,
      current_round,
      current_college_code,
      current_branch_code,
      branch_filter: branchFilter ? [...branchFilter].sort() : null,
    },
    current_allotment: current,
    modes,
    unscored_available_options: {
      explanation: UNSCORED_EXPLANATION,
      options: reachableUnscored,
      option_count: reachableUnscored.length,
    },
    candidates_evaluated: rows.length + unscored.length,
    scored_candidates: rows.length,
    unscored_candidates: unscored.length,
    warnings,
    disclaimer: DISCLAIMER,
  }
}
