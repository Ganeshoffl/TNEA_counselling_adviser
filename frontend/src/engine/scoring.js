/**
 * College quality scoring. Port of backend/app/scoring.py.
 *
 * Keep the two in step: scripts/verify_parity.sh asserts they produce identical
 * scores, component breakdowns and provenance for every college.
 *
 * The two decisions that matter most are preserved here:
 *   1. A quality score REQUIRES published placement data. Renormalising the
 *      remaining weights when placement is missing produced actively misleading
 *      output, so a college without it gets no score at all.
 *   2. Components are normalised against fixed ABSOLUTE anchors, not against the
 *      best and worst college in the dataset, so scores stay interpretable and do
 *      not shift as the dataset grows.
 */

import { pyFixed, pyRound, pyThousands, clamp } from './pyCompat.js'

export const WEIGHTS = {
  placement_median_salary: 0.35,
  placement_rate: 0.15,
  lab_spend_per_student: 0.15,
  infrastructure_spend_per_student: 0.1,
  nirf_standing: 0.15,
  fee_band: 0.1,
}

const REQUIRED_COMPONENTS = ['placement_median_salary']

const ANCHORS = {
  placement_median_salary: [300000, 1000000],
  placement_rate: [0.4, 0.95],
  lab_spend_per_student: [10000, 250000],
  infrastructure_spend_per_student: [20000, 600000],
  nirf_standing: [300.0, 1.0],
  fee_band: [3.0, 1.0],
}

const LOG_SCALED = new Set(['lab_spend_per_student', 'infrastructure_spend_per_student'])

export const COMPONENT_LABELS = {
  placement_median_salary: 'Median salary of placed graduates',
  placement_rate: 'Share of graduating students placed',
  lab_spend_per_student:
    'Annual spend on new laboratory equipment and software, per student',
  infrastructure_spend_per_student:
    'Annual capital spend on labs, library, classrooms and workshops, per student',
  nirf_standing: 'NIRF national standing in Engineering',
  fee_band: 'Fee tier (lower tuition scores higher)',
}

const BAND_MIDPOINTS = { '101-150': 125.5, '151-200': 175.5, '201-300': 250.5 }

const UNSCORABLE_REASON =
  'No placement figure could be obtained for this college, and placement carries ' +
  'half of the quality weight. Rather than renormalise the remaining factors and ' +
  'produce a number that would look comparable to a fully measured college, no ' +
  'quality score is given. NIRF publishes per-institute data only down to rank 200, ' +
  "and no copy of this college's own submission was found on its website either."

const SCORING_NOTE =
  'Placement carries 50% of the total weight (median salary 35%, placement rate ' +
  '15%). Each factor is normalised against fixed absolute anchors, not against the ' +
  'best and worst college in this dataset, so scores stay interpretable and do not ' +
  'shift as the dataset grows. Weights and anchors are a modelling choice and are ' +
  'published by the API.'

export function anchorNormalise(component, value) {
  let [zeroAt, oneAt] = ANCHORS[component]
  let v = value
  if (LOG_SCALED.has(component)) {
    v = Math.log(Math.max(v, 1.0))
    zeroAt = Math.log(zeroAt)
    oneAt = Math.log(oneAt)
  }
  if (oneAt === zeroAt) return 0.5
  return clamp((v - zeroAt) / (oneAt - zeroAt), 0.0, 1.0)
}

export function nirfPosition(college) {
  const nirf = college.nirf
  if (!nirf) return null
  if (nirf.rank) return Number(nirf.rank)
  return BAND_MIDPOINTS[nirf.rank_band] ?? null
}

export function labPerStudent(college) {
  const infra = college.infrastructure
  if (!infra) return null
  return infra.lab_spend_per_student_inr ?? null
}

export function infraPerStudent(college) {
  const infra = college.infrastructure
  if (!infra) return null
  const total = infra.ug4_total_students
  if (!total) return null
  const parts = [
    infra.lab_equipment_expenditure_inr,
    infra.library_expenditure_inr,
    infra.other_capital_expenditure_inr,
    infra.engineering_workshops_expenditure_inr,
  ].filter((p) => p !== null && p !== undefined)
  if (!parts.length) return null
  return parts.reduce((a, b) => a + b, 0) / total
}

function componentValues(college) {
  const out = {}
  const placement = college.placement

  if (placement) {
    const shared = {
      source: placement.source ?? null,
      source_url: placement.source_url ?? null,
      as_of: placement.graduating_year ?? null,
      hosted_by: placement.hosted_by ?? null,
      caveat: placement.provenance_caveat ?? null,
      host_note: placement.host_note ?? null,
    }
    const salary = placement.median_salary_inr
    if (salary) {
      out.placement_median_salary = {
        raw: salary,
        display: `Rs ${pyThousands(salary)} per annum`,
        normalised: anchorNormalise('placement_median_salary', Number(salary)),
        ...shared,
      }
    }
    const rate = placement.placement_rate
    if (rate !== null && rate !== undefined) {
      out.placement_rate = {
        raw: rate,
        display:
          `${pyFixed(rate * 100, 1)}% ` +
          `(${placement.students_placed} of ${placement.students_graduating})`,
        normalised: anchorNormalise('placement_rate', Number(rate)),
        ...shared,
      }
    }
  }

  const infrastructure = college.infrastructure || {}
  const infraShared = {
    source: infrastructure.source ?? null,
    source_url: infrastructure.source_url ?? null,
    hosted_by: infrastructure.hosted_by ?? null,
    caveat: infrastructure.provenance_caveat ?? null,
  }

  const lab = labPerStudent(college)
  if (lab) {
    out.lab_spend_per_student = {
      raw: lab,
      display: `Rs ${pyThousands(pyRound(lab, 0))} per student per year`,
      normalised: anchorNormalise('lab_spend_per_student', Number(lab)),
      ...infraShared,
    }
  }
  const infra = infraPerStudent(college)
  if (infra) {
    out.infrastructure_spend_per_student = {
      raw: infra,
      display: `Rs ${pyThousands(pyRound(infra, 0))} per student per year`,
      normalised: anchorNormalise('infrastructure_spend_per_student', Number(infra)),
      ...infraShared,
    }
  }

  const nirf = college.nirf
  const position = nirfPosition(college)
  if (nirf && position) {
    let display
    let basis
    if (nirf.rank) {
      display = `NIRF ${nirf.year} rank ${nirf.rank} (score ${nirf.score})`
      basis = 'published rank'
    } else {
      display = `NIRF ${nirf.year} rank band ${nirf.rank_band}`
      basis =
        'midpoint of the published band, because NIRF publishes no rank or score ' +
        'for institutes inside a band'
    }
    out.nirf_standing = {
      raw: position,
      display,
      normalised: anchorNormalise('nirf_standing', Number(position)),
      source: nirf.publisher ?? null,
      source_url: nirf.source_url ?? null,
      basis,
    }
  }

  const fee = college.fee_band
  out.fee_band = {
    raw: fee.relative_tier,
    display: fee.band,
    normalised: anchorNormalise('fee_band', Number(fee.relative_tier)),
    source: 'Derived from the institution type in the official TNEA college name',
    caveat: fee.caveat,
  }

  return out
}

const TOTAL_WEIGHT = Object.values(WEIGHTS).reduce((a, b) => a + b, 0)

export function scoreCollege(college) {
  const components = componentValues(college)

  const missingRequired = REQUIRED_COMPONENTS.filter((c) => !(c in components)).sort()

  const breakdown = []
  let usedWeight = 0
  let weighted = 0

  for (const [key, weight] of Object.entries(WEIGHTS)) {
    const comp = components[key]
    if (!comp || comp.normalised === null || comp.normalised === undefined) {
      breakdown.push({
        component: key,
        label: COMPONENT_LABELS[key],
        weight,
        available: false,
        reason: 'Not published by the official source for this college',
      })
      continue
    }
    usedWeight += weight
    weighted += weight * comp.normalised
    const entry = {
      component: key,
      label: COMPONENT_LABELS[key],
      weight,
      available: true,
      value: comp.display,
      normalised: pyRound(comp.normalised, 4),
      source: comp.source ?? null,
      source_url: comp.source_url ?? null,
    }
    for (const extra of ['as_of', 'basis', 'caveat', 'hosted_by', 'host_note']) {
      if (comp[extra]) entry[extra] = comp[extra]
    }
    breakdown.push(entry)
  }

  if (missingRequired.length || usedWeight <= 0) {
    return {
      quality_score: null,
      scorable: false,
      unscorable_reason: UNSCORABLE_REASON,
      missing_required_components: missingRequired,
      evidence_completeness: pyRound(usedWeight / TOTAL_WEIGHT, 3),
      data_confidence: college.data_confidence ?? null,
      components: breakdown,
    }
  }

  return {
    quality_score: pyRound((100.0 * weighted) / usedWeight, 2),
    scorable: true,
    evidence_completeness: pyRound(usedWeight / TOTAL_WEIGHT, 3),
    data_confidence: college.data_confidence ?? null,
    components: breakdown,
    scoring_note: SCORING_NOTE,
  }
}
