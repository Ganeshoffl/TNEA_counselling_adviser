# TNEA Counselling Advisor

A web app for a student in the middle of **TNEA** (Tamil Nadu Engineering Admissions)
counselling. Enter your cutoff mark, rank, community and current round, plus the seat you
have been allotted, and it tells you whether to **stay** or **move up** — under three
heads: **Safe**, **Optimal** and **Risk**.

Every figure it uses is published by a government source, and every figure it shows links
back to the document it came from. Nothing is estimated from reputation, coaching-centre
lists or hearsay.

---

## It runs in the browser, with no server

The app is a **static site**. The recommendation engine and the whole dataset ship to the
browser (**746 KB, ~96 KB gzipped**), so there is no backend to host, no cold start and no
running cost. Pushing to `main` publishes it to GitHub Pages.

The FastAPI backend is still maintained and still serves the same documented API for
programmatic use — it is simply no longer required to use the app.

## Quick start

```bash
# Static site only — no Python needed to run it
cd frontend && npm install && npm run dev      # http://127.0.0.1:5173
```

```bash
# Full setup, including the API and the data pipeline
uv venv .venv --python 3.11
uv pip install --python .venv/bin/python -r backend/requirements.txt
cd frontend && npm install && npm run build && cd ..

bash scripts/dev_api.sh          # http://127.0.0.1:8000  (API + built UI)
```

Verify everything end to end:

```bash
bash scripts/verify.sh           # 19 checks, including engine-vs-official-file and Python/JS parity
bash scripts/verify_parity.sh    # just the Python vs JavaScript engine comparison
bash scripts/capture_static.sh   # proves the UI works with NO backend, writes screenshots/static/
bash scripts/demo.sh             # boots the API, prints a live recommendation, shuts down
```

---

## Where the data comes from

| Dataset | Source | What it gives |
|---|---|---|
| Round-wise allotment lists, rounds 1–3 | [static.tneaonline.org](https://static.tneaonline.org/docs/TNEA-2026-ROUND-1-GENERAL-ACADEMIC-PROVISIONAL-ALLOTMENT-LIST.pdf) — Directorate of Technical Education (DoTE), Tamil Nadu | Per-candidate rank, college, branch and allotted community → exact **opening and closing ranks** per college + branch + community + round |
| Vacancy position after rounds 1–3 | [static.tneaonline.org](https://static.tneaonline.org/docs/TNEA-2026-GENERAL-ACADEMIC-VACANCY-POSITION-AFTER-ROUND-1.pdf) — DoTE | **Seats still vacant** per community, and the official college/branch code directory |
| Counselling procedure | [static.tneaonline.org](https://static.tneaonline.org/docs/8_TNEA_2024_Counselling_procedure.pdf) — DoTE | The six official seat-confirmation options the three modes are built on |
| NIRF 2025 Engineering rankings | [nirfindia.org](https://www.nirfindia.org/Rankings/2025/EngineeringRanking.html) — Ministry of Education | Rank, score, sub-scores (TLR, RPC, GO, OI, Perception), and rank bands |
| NIRF 2025 per-institute disclosures | `nirfindia.org/nirfpdfcdn/2025/pdf/Engineering/{id}.pdf` — Ministry of Education | **Median salary**, students placed and graduating, **laboratory equipment spend**, library and capital spend, student strength |
| Institution-hosted NIRF disclosures | Each college's own website (e.g. `sece.ac.in`, `panimalar.ac.in`, `rmd.ac.in`) | The same NIRF submission document for colleges the Ministry does not publish, used under a **separate, weaker confidence grade** (see below) |

Admission year **2026** for counselling data (the most recent complete cycle) and **2025**
for NIRF (the most recent published edition).

### Scale of what was ingested

- **422** official TNEA colleges and **116** branch codes
- **19,170** opening/closing-rank records (college × branch × community × round)
- **10,404** vacancy rows across three rounds
- **0** unparsed data rows in either dataset

---

## Placement and lab quality are real figures, not proxies

The original plan was to use accreditation tier as a *proxy* for lab and infrastructure
quality, because no trustworthy numeric source was expected to exist. It turned out that
NIRF's per-institute disclosures — the forms each college submits to the Ministry of
Education — contain audited figures directly:

- `Median salary of placed graduates`
- `No. of students placed` and `No. of students graduating in minimum stipulated time`
- `New Equipment and software for Laboratories` (annual capital expenditure)
- `Library (Books, Journals and e-Resources)`
- `Other expenditure on creation of Capital Assets` (classrooms, labs, workshops)

So lab and infrastructure quality is measured as **actual rupees spent per student per
year**, not inferred from a grade.

---

## The three modes are official TNEA options, not invented labels

From the DoTE counselling procedure, a candidate holding an allotment has six confirmation
options. Two of them decide the whole stay-or-move question:

**Accept and Upward** — pay the fee at a TFC and wait for a *higher* choice. The procedure
states that if no better choice becomes available, the candidate *"is confirmed with the
previously allotted choice"*. **Your current seat is a floor.**

**Decline and Upward** — decline the seat and wait for a higher choice. If the upgrade does
not arrive the candidate *"will be moved to the next round"* **without** the declined seat.

Hence:

| Mode | Probability band | Official route | Downside |
|---|---|---|---|
| **Safe** | ≥ 80% | Accept and Upward | Minimal — a failed upgrade leaves you holding your current seat |
| **Optimal** | 45–80% | Accept and Upward | Low — same protection |
| **Risk** | 12–45% | Decline and Upward | **Real** — you can end up in the next round with no seat |

Expected value is computed with the correct fallback for each route: for Safe and Optimal
the downside is *your current college*, so `EV = p × target + (1 − p) × current`. For Risk
the fallback is genuinely unknowable from published data, so **no number is invented** — the
app says so instead.

> One real constraint the app surfaces rather than hides: upward movement only considers
> choices ranked **above** your current allotment *in your own choice list*. A college
> suggested here is reachable in upward movement only if you had already placed it higher;
> otherwise it must be pursued in a later round.

---

## How admission probability is estimated

For a college + branch + community and a target round:

1. **Closing rank** — the worst rank actually allotted there in the reference round, taken
   from the official per-candidate allotment list. Probability follows a logistic curve in
   the *relative* gap between your rank and that closing rank; sitting exactly on the
   closing rank gives 50%, which is the honest reading of being on the boundary.
2. **Seat availability** — seats vacant after round *N* are exactly what candidates compete
   for in round *N+1*. **Zero vacancy forces probability to zero**, a hard stop rather than a
   small number. Very few remaining seats apply a discount (1 seat → ×0.70).

Reference-round preference: the same round when TNEA published it (same-year, same-round
evidence is strongest), otherwise the nearest earlier round, otherwise a later one. The
round actually used is always stated in the UI.

**Seats before round 1** are not published for 2026 — the only seat-matrix PDF still online
is a 2023 file, which was discarded. That figure is instead *derived by exact arithmetic on
two official numbers*: `seats vacant after round 1 + seats allotted in round 1`. This was
cross-checked and holds: `vacant_after_R3 (53,668) = vacant_after_R2 (106,583) − R3_allotments (52,915)`,
and the implied statewide total of **181,436** seats matches Tamil Nadu's real ~1.8 lakh
engineering capacity.

---

## Quality score

Placement carries **half** the weight, as requested.

| Factor | Weight |
|---|---|
| Median salary of placed graduates | 35% |
| Share of graduating students placed | 15% |
| Lab equipment spend per student | 15% |
| Infrastructure capital spend per student | 10% |
| NIRF national standing | 15% |
| Fee tier | 10% |

Two deliberate decisions, both made to avoid misleading output:

**A score requires published placement data.** An earlier version renormalised the weights
when placement was missing, and the result was actively wrong: a government college with *no
placement data at all* scored **40.0** purely because its tuition is low, beating a college
with fully verified placement, laboratory and ranking data at **37.7**. Colleges without
placement data are now never given a score. They still appear, in a separate
*"Also reachable, but not quality-ranked"* section, so the student sees them without a fake
comparison.

**Factors are normalised against fixed absolute anchors, not cohort extremes.** Min–max
normalisation over 40 colleges collapsed whichever college came last on every metric to
nearly zero (Mepco Schlenk scored **4.88**), which misrepresents a respected institution.
Absolute anchors keep scores stable and interpretable and do not shift as the dataset grows.

Weights and anchors are a **modelling choice**, not data. They are published at `/api/meta`
so they can be argued with. The figures they are applied to are official.

### Data confidence grades

Provenance is graded, and the grade travels with every figure into the API and the UI.

| Grade | Count | Meaning |
|---|---|---|
| **A** | 18 | Placement and laboratory figures from the NIRF disclosure **published by the Ministry of Education itself**. Strongest provenance. |
| **S** | 12 | The **same kind of official NIRF submission, but served from the college's own website**, because the Ministry publishes per-institute data only down to rank 200. Verified for submission year, Engineering category and matching institute identity — but the chain of custody is weaker, so it is graded separately and never shown as Ministry-hosted. |
| **B** | 10 | NIRF publishes only a rank band and no disclosure could be obtained anywhere. **No placement or laboratory figure is claimed.** |
| **U** | 382 | No NIRF presence. Never ranked or recommended on quality; retained only so a current allotment can still be displayed. |

So **30 of the 40** TNEA colleges with NIRF standing now carry real placement and
laboratory figures, up from 18 when only Ministry-hosted documents were used.

#### What grade S is checked for

A college-hosted PDF is accepted only if **all** of these hold. Anything else is
rejected and contributes nothing:

1. **Host belongs to the institution.** The PDF's registrable domain must match the
   college's own site. Third-party aggregators, brochure mirrors, Scribd, notopedia and
   random CDNs are rejected outright regardless of content — that is precisely the
   grey-provenance zone this project avoids. (One documented exception: SNS College of
   Technology publishes via `snsiqac.org`, its own IQAC site; that host is allowed
   explicitly, for that college only, and the exception is recorded in the output.)
2. **Correct document.** The PDF must declare `Submitted Institute Data for NIRF'YYYY'`
   (or the Ministry's equivalent wording) for an accepted year.
3. **Correct category.** The embedded institute id must start with `IR-E-`, and the
   header must say `Data Capturing System: ENGINEERING`. Overall, Innovation and SDG
   submissions carry different figures and are rejected.
4. **Correct institution.** The `Institute Name` printed inside the PDF must match the
   expected college by distinctive-token overlap or whole-string similarity.

This rejected real documents: National Engineering College publishes only 2020 and 2021
copies, and several colleges' `Overall` submissions were discarded for being the wrong
category.

#### A note on 2025 versus 2026

NIRF 2025 is the latest *published ranking*, and the ranks and bands used throughout come
from it. Some colleges have additionally published their **NIRF 2026** submission (that
submission window closed in March 2026). A 2026 document is newer and equally official, so
it is accepted, but 2025 is preferred whenever both exist. The consequence is visible
rather than hidden: a 2025 submission reports the **2023-24** graduating cohort while a
2026 submission reports **2024-25**, and the cohort year is displayed next to every
placement figure in the UI. Eight grade-S colleges use 2025 data; four use 2026.

---

## Honest limitations

- **10 of the 40 NIRF-listed TNEA colleges still have no placement data.** NIRF publishes
  per-institute disclosures only down to rank 200, and for these ten no copy of their own
  submission could be found on their website either (Chennai Institute of Technology,
  E.G.S. Pillay, Karpagam, K. Ramakrishnan College of Technology, K. Ramakrishnan College
  of Engineering, M.Kumarasamy, National Engineering College, PSNA, Rathinam Technical
  Campus, Saveetha Engineering College). Nothing is filled in for them and they are never
  quality-ranked.
- **Grade S figures are college-served, not Ministry-served.** The document is the
  institution's own NIRF submission and is content-verified, but a college controls the file
  it publishes about itself. Treat grade S as good evidence, not as strong as grade A.
- **Placement cohort years are mixed** across grade S (2023-24 for 2025 submissions,
  2024-25 for 2026 ones). Every figure shows its cohort year, but strict like-for-like
  comparison across those colleges is imperfect.
- **Scores follow official submissions, not reputation.** Mepco Schlenk scores low because
  the median salary (₹3.5 L) and placement rate (48.8%) it *reported to NIRF* are low. That
  is the point of preferring audited data over popular perception, but it can be
  counter-intuitive.
- **Placement is institute-level.** NIRF does not publish per-branch salaries, so branch is
  handled through cutoffs and demand rather than by claiming branch-level placement numbers.
- **Anna University is rated as one institution.** Its NIRF data is applied only to the three
  Chennai university departments it covers (CEG, ACT, MIT), and deliberately *not* to the
  regional campuses or the School of Architecture.
- **Round 4 is a forward simulation**, since TNEA published only rounds 1–3.
- **Availability is historical, not live.** There is no TNEA API; the round files are static
  PDFs. The app models a round from published data rather than reading a live seat count.
- **Deemed universities are absent by design.** VIT, SRM, Amrita, SASTRA, Sathyabama,
  Karunya, HITS, Crescent, Dr. M.G.R. and VISTAS do not admit through TNEA, so they are not
  in the official TNEA list and are filtered out by the data itself. SSN College of
  Engineering and Sri Sai Ram Institute of Technology are also absent from the TNEA 2026
  general academic list and are therefore excluded.
- Probabilities are **estimates**, not guarantees. Actual allotment also depends on your own
  choice ordering and on how other candidates behave in the same round.

---

## Why the NIRF → TNEA mapping is hand-written

Automated fuzzy name matching was implemented, tested, and **rejected**. TNEA college names
embed the full postal address, so once generic words (`college`, `institute`, `engineering`,
`technology`) are removed the only distinctive token is often the city. That made
*"Vellore Institute of Technology"* match unrelated colleges merely located in Vellore, with
a perfect-looking confidence score.

Because a wrong match would attach one college's placement record to a different college,
the mapping in `data-sources/curated/nirf_tnea_mapping.json` is hand-verified against the
official TNEA names, with the verbatim TNEA name stored beside each code for audit, plus the
reason for every exclusion. The rejected matcher is kept at `scripts/match_nirf_tnea.py` as
documentation of why.

Disclosure ingestion is additionally **self-verifying**: the fetched PDF's own
`Institute Name: X [ID]` line must match the expected college, or the disclosure is rejected.
That check caught a genuine bug in the matcher itself — `R.M.K. Engineering College` loses
every token once punctuation is stripped and single letters dropped, so a perfect match was
being rejected until a string-similarity fallback was added.

---

## The engine exists twice, and that is checked

To run with no server, the engine had to be ported to JavaScript. The Python
implementation is kept because it backs the documented API. Two implementations of the
same logic is a real maintenance risk, so it is converted into a guarded invariant:

`scripts/verify_parity.sh` runs **both** engines over ten student profiles and asserts the
output is identical — every score, probability, option ordering, verdict and sentence.
Floats are compared to 1e-9; everything else must match exactly. It currently agrees across
**3,521 scored candidates and 172 ranked options**, and it runs in CI on every push.

That check earned its keep immediately by catching two real bugs in the port:

1. **A rounding tolerance that was simply wrong.** Ties were detected with a 1e-9
   tolerance, which classified `75.55` as a tie. It is not one — the nearest double is
   `75.5499999999999971…`, so Python's `%.1f` correctly gives `75.5`, while the port
   produced `75.6`.
2. **Multiplication destroying the evidence.** The second attempt tested
   `value * 10**digits % 1 === 0.5`, but that multiplication itself rounds: `75.55 * 10`
   lands on *exactly* `755.5`, hiding the fact that the original value was below `.55`.

The fix is to never multiply, and to detect genuine ties (`23.25`, `0.125`) from the exact
decimal expansion. See `frontend/src/engine/pyCompat.js`.

## Project structure

```
backend/
  app/
    main.py          FastAPI routes; also serves the built frontend
    engine.py        Safe / Optimal / Risk selection and the stay-vs-move verdict
    probability.py   Admission probability from closing ranks and vacancy
    scoring.py       Quality score, weights, anchors, provenance breakdown
    data_store.py    Loads the dataset, builds indices, derives pre-round-1 seats
    models.py        Request validation
    data/            Generated dataset (colleges, cutoffs, vacancy, branches)
frontend/
  public/data/       Static bundle shipped to the browser (746 KB)
  src/engine/        JavaScript port: scoring, probability, verdicts, pyCompat
  src/               React app: form, three mode tabs, provenance panels
data-sources/
  raw/               Downloaded official PDFs and HTML
  parsed/            Structured output of the parsers
  curated/           Hand-verified NIRF ↔ TNEA mapping and institute IDs
scripts/
  parse_allotments.py       Allotment lists  → opening/closing ranks
  parse_vacancy.py          Vacancy PDFs     → vacant seats + code directory
  parse_nirf.py             NIRF rankings    → ranks, scores, Ministry disclosures
  fetch_disclosures.py      Verified Ministry disclosure fetch by recovered institute id
  discover_self_hosted.py   Crawls colleges' own sites for their NIRF submission (grade S)
  parse_self_hosted.py      Parses the verified college-hosted disclosures
  build_dataset.py          Combines everything into backend/app/data
  build_static_bundle.py    Trims the dataset into frontend/public/data for the browser
  verify.sh                 End-to-end checks (19)
  verify_parity.sh          Python vs JavaScript engine comparison
  capture.sh                Screenshots via the API-served build
  capture_static.sh         Screenshots via the static build, proving no backend is needed
  demo.sh                   Boots the API, prints a live recommendation, shuts down
```

After changing anything in `backend/app/data`, regenerate the browser bundle:

```bash
python scripts/build_static_bundle.py
```

The Pages workflow regenerates it too and **fails the build if the committed copy is
stale**, so the data shipped to users cannot drift from the dataset.

Rebuild the dataset from the official sources:

```bash
.venv/bin/python scripts/parse_allotments.py
.venv/bin/python scripts/parse_vacancy.py
.venv/bin/python scripts/parse_nirf.py
.venv/bin/python scripts/fetch_disclosures.py
.venv/bin/python scripts/discover_self_hosted.py
.venv/bin/python scripts/parse_self_hosted.py
.venv/bin/python scripts/build_dataset.py
```

---

## Parsing details worth knowing

Two quirks in the official PDFs would have silently corrupted the data:

1. **Community columns are not in a fixed order.** Rounds 1 and 2 print
   `OC BC BCM MBC SC SCA ST`, but round 3 prints `OC BCM BC MBC SCA SC ST`. The order is read
   from each page's own header instead of assumed, so columns cannot be transposed.
2. **Ranks carry tie-break letter suffixes** such as `53A` and `53B` when candidates share a
   rank position. The parsers report every unmatched line rather than dropping it, which is
   how this was caught.

Both parsers finish with zero unmatched rows, and `scripts/verify.sh` asserts the engine's
reported closing rank, opening rank and allotted-seat count match the raw official file
exactly. It also asserts that every grade-S figure carries a provenance caveat and a source
link, that grade B and U colleges carry no placement figures at all, and that no
third-party aggregator host slipped into the self-hosted source list.

---

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Liveness and row counts |
| `GET /api/meta` | Admission year, communities, rounds, confidence legend, scoring weights, sources |
| `GET /api/modes` | The three modes and the official TNEA route each relies on |
| `GET /api/branches` | Branch code → official branch name |
| `GET /api/colleges` | Colleges with quality scores; `search`, `recommendable_only`, `limit` |
| `GET /api/colleges/{code}` | Full record including per-factor provenance |
| `POST /api/recommend` | The recommendation |

```bash
curl -X POST http://127.0.0.1:8000/api/recommend \
  -H 'Content-Type: application/json' \
  -d '{"cutoff_mark":190.0,"rank":12000,"community":"MBC","current_round":2,
       "current_college_code":1419,"current_branch_code":"EC"}'
```

Stateless: no login, no database, nothing about the student is stored.

---

*Not affiliated with the Directorate of Technical Education or the Ministry of Education.
Always confirm against [tneaonline.org](https://www.tneaonline.org/) before acting.*
