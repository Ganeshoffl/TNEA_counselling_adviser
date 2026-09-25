// Drives the built app in a headless browser and captures screenshots, so the UI
// can be reviewed without a local machine. Expects the API (which also serves the
// built frontend) to be running on the port given by API_PORT.
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const PORT = process.env.API_PORT || '8000'
const BASE = `http://127.0.0.1:${PORT}`
const OUT = process.env.SHOT_DIR || '/projects/sandbox/screenshots'
const RANK = process.env.SHOT_RANK || '12000'
const COMMUNITY = process.env.SHOT_COMMUNITY || 'MBC'
const ROUND = process.env.SHOT_ROUND || '2'
const CUTOFF = process.env.SHOT_CUTOFF || '190'

mkdirSync(OUT, { recursive: true })

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
const problems = []

page.on('pageerror', (err) => problems.push(`pageerror: ${err.message}`))
page.on('console', (msg) => {
  if (msg.type() === 'error') problems.push(`console: ${msg.text()}`)
})

async function shot(name) {
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true })
  console.log(`  captured ${name}.png`)
}

console.log('loading app')
await page.goto(BASE, { waitUntil: 'networkidle' })
await page.waitForSelector('.masthead h1')
await shot('01-landing')

// Fill the form the way a student would.
await page.fill('#cutoff', CUTOFF)
await page.fill('#rank', RANK)
await page.selectOption('#community', COMMUNITY)
await page.selectOption('#round', ROUND)

// Pick the current allotment through the search-and-select flow.
await page.fill('#college-search', 'Sri Sai Ram Engineering')
await page.waitForSelector('button.link')
await page.click('button.link')
await page.waitForSelector('#branch')
await page.selectOption('#branch', 'EC')

await page.click('button.primary')
await page.waitForSelector('.verdict', { timeout: 60000 })
await page.waitForTimeout(400)
await shot('02-results-safe')

// Expand the provenance panels on the first option.
const disclosures = page.locator('.option .disclosure > summary')
const count = await disclosures.count()
if (count >= 2) {
  await disclosures.nth(0).click()
  await disclosures.nth(1).click()
  await page.waitForTimeout(300)
  await shot('03-provenance-expanded')
}

// Visit the other two modes.
for (const [index, label] of [[1, 'optimal'], [2, 'risk']]) {
  await page.locator('.tab').nth(index).click()
  await page.waitForTimeout(350)
  await shot(`0${index + 3}-results-${label}`)
}

// Confirm the headline verdict text actually rendered.
await page.locator('.tab').nth(0).click()
await page.waitForTimeout(250)
const headline = await page.locator('.verdict .headline').first().textContent()
console.log(`  safe verdict headline: ${headline?.trim()}`)

if (!headline || !headline.trim()) problems.push('verdict headline did not render')

// Confirm the confidence-grade badges render, including grade S where present.
const gradeBadges = await page.locator('.option .badge', { hasText: 'Grade' }).allTextContents()
const grades = new Set(gradeBadges.map((t) => t.trim().split(' ')[1]))
console.log(`  confidence grades visible in results: ${[...grades].sort().join(', ') || 'none'}`)
if (grades.size === 0) problems.push('no confidence-grade badge rendered on any option')

const selfHosted = await page.locator('.selfhosted-flag').count()
console.log(`  college-hosted figure markers on this tab: ${selfHosted}`)

await browser.close()

if (problems.length) {
  console.log('\nBROWSER PROBLEMS:')
  for (const p of problems) console.log(`  - ${p}`)
  process.exit(1)
}
console.log('\nno browser errors')
