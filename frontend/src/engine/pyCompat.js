/**
 * Helpers that reproduce Python's numeric formatting and rounding exactly.
 *
 * The recommendation engine exists twice: once in Python (backend/app, which also
 * serves the documented API) and once here, so the app can run with no backend on
 * static hosting. scripts/verify_parity.sh asserts the two produce byte-identical
 * output, which only holds if rounding matches.
 *
 * Getting this right took two attempts, both caught by the parity check:
 *
 *  1. A 1e-9 tolerance was used to detect rounding ties. That wrongly classified
 *     75.55 as a tie. It is not one: the nearest double to 75.55 is
 *     75.5499999999999971..., so Python's "%.1f" correctly gives "75.5".
 *
 *  2. Ties were then detected as `value * 10**digits % 1 === 0.5`. That is also
 *     wrong, because the multiplication itself rounds: 75.55 * 10 lands on exactly
 *     755.5, destroying the evidence that the original value was below .55.
 *
 * The fix is to never multiply. Python formats the exact binary value, and so does
 * JavaScript's toFixed, so `value.toFixed(digits)` already agrees with Python
 * everywhere EXCEPT at a genuine tie — a value whose exact binary expansion really
 * does end in 5 at the rounding position, such as 23.25 or 0.125. Python rounds
 * those half-to-even while toFixed rounds half-up, so genuine ties are detected by
 * inspecting the exact decimal expansion (toFixed with extra digits is exact for
 * doubles) and handled separately.
 */

const EXTRA_DIGITS = 25

/** Exact decimal expansion of |value|, as [integerPart, decimalPart]. */
function exactParts(value, digits) {
  const text = Math.abs(value).toFixed(Math.min(100, digits + EXTRA_DIGITS))
  const dot = text.indexOf('.')
  if (dot === -1) return [text, '']
  return [text.slice(0, dot), text.slice(dot + 1)]
}

/**
 * True only when the exact binary value ends in 5 at the rounding position, with
 * nothing but zeros after it. This is what Python treats as a tie.
 */
function isExactTie(value, digits) {
  if (!Number.isFinite(value) || Math.abs(value) >= 1e21) return false
  const [, decimals] = exactParts(value, digits)
  const rest = decimals.slice(digits)
  return /^50*$/.test(rest)
}

function formatScaled(scaled, digits) {
  let text = scaled.toString().padStart(digits + 1, '0')
  if (digits === 0) return text
  return `${text.slice(0, text.length - digits)}.${text.slice(text.length - digits)}`
}

/** Python's f"{value:.Nf}" */
export function pyFixed(value, digits) {
  if (!Number.isFinite(value)) return String(value)

  if (isExactTie(value, digits)) {
    const [integerPart, decimals] = exactParts(value, digits)
    // |floor(value * 10**digits)|, built from the exact digits so nothing is lost.
    let scaled = BigInt(integerPart + decimals.slice(0, digits))
    if (scaled % 2n !== 0n) scaled += 1n // ties to even
    const formatted = formatScaled(scaled, digits)
    return value < 0 ? `-${formatted}` : formatted
  }

  // Both runtimes round the exact double identically here.
  return value.toFixed(digits)
}

/** Python's round(): ties to even, otherwise nearest. */
export function pyRound(value, digits = 0) {
  if (!Number.isFinite(value)) return value
  return Number(pyFixed(value, digits))
}

/** Python's f"{value:,}" for integers, e.g. 800000 -> "800,000" */
export function pyThousands(value) {
  return Math.trunc(value).toLocaleString('en-US')
}

/** Python's f"{value:.0%}", e.g. 0.331 -> "33%" */
export function pyPercent0(value) {
  return `${pyFixed(value * 100, 0)}%`
}

/** Clamp into [lo, hi]. */
export function clamp(value, lo, hi) {
  return Math.max(lo, Math.min(hi, value))
}
