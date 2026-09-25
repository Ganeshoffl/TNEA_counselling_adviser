import { useEffect, useState } from 'react'
import { getBranches, getColleges, getMeta, postRecommend } from './api'
import StudentForm from './components/StudentForm'
import OptionCard from './components/OptionCard'
import VerdictCard from './components/VerdictCard'
import CurrentAllotment from './components/CurrentAllotment'
import DataTransparency from './components/DataTransparency'

const MODES = ['safe', 'optimal', 'risk']

export default function App() {
  const [meta, setMeta] = useState(null)
  const [branches, setBranches] = useState({})
  const [colleges, setColleges] = useState([])
  const [bootError, setBootError] = useState(null)

  const [result, setResult] = useState(null)
  const [mode, setMode] = useState('safe')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    Promise.all([getMeta(), getBranches(), getColleges({ recommendableOnly: false, limit: 1000 })])
      .then(([metaRes, branchRes, collegeRes]) => {
        setMeta(metaRes)
        setBranches(branchRes.branches)
        setColleges(collegeRes.colleges)
      })
      .catch((err) => setBootError(err.message))
  }, [])

  async function handleSubmit(payload) {
    setLoading(true)
    setError(null)
    try {
      const response = await postRecommend(payload)
      setResult(response)
      const firstWithOptions = MODES.find((m) => response.modes[m].option_count > 0)
      setMode(firstWithOptions || 'safe')
    } catch (err) {
      setError(err.message)
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  const active = result?.modes?.[mode]

  return (
    <div className="shell">
      <header className="masthead">
        <h1>TNEA Counselling Advisor</h1>
        <p>
          Tells you whether to stay with your current TNEA allotment or try to move up, using
          only officially published data: the Directorate of Technical Education's round-wise
          allotment and vacancy files, and the Ministry of Education's NIRF disclosures.
        </p>
        <div className="pill-row">
          <span className="pill">Tamil Nadu engineering (B.E./B.Tech)</span>
          <span className="pill">General academic stream</span>
          <span className="pill">Admission year {meta?.admission_year ?? '—'}</span>
          <span className="pill">No login, nothing stored</span>
        </div>
      </header>

      {bootError && (
        <div className="callout error" style={{ marginBottom: 20 }}>
          Could not load reference data: {bootError}. Is the API running on port 8000?
        </div>
      )}

      <div className="columns">
        <div>
          <StudentForm
            meta={meta}
            branches={branches}
            colleges={colleges}
            loading={loading}
            onSubmit={handleSubmit}
          />
          <DataTransparency meta={meta} />
        </div>

        <div>
          {error && <div className="callout error" style={{ marginBottom: 18 }}>{error}</div>}

          {!result && !error && (
            <div className="card">
              <h2>How this works</h2>
              <p style={{ color: 'var(--muted)', fontSize: '0.9rem', marginTop: 0 }}>
                Enter your cutoff mark, rank, community and the round you are choosing for. If you
                already hold an allotment, add it too and the three modes will each tell you whether
                moving up is worth it.
              </p>
              <h3>The three modes</h3>
              <p style={{ color: 'var(--muted)', fontSize: '0.88rem' }}>
                These are not invented labels. They map onto the confirmation options the
                Directorate of Technical Education actually offers:
              </p>
              <ul className="legend" style={{ paddingLeft: 18 }}>
                <li>
                  <strong style={{ color: 'var(--safe)' }}>Safe</strong> — high-probability upgrades
                  through <em>Accept and Upward</em>. The procedure confirms your existing allotment
                  if no better choice arrives, so your current seat is a floor.
                </li>
                <li>
                  <strong style={{ color: 'var(--optimal)' }}>Optimal</strong> — best expected value,
                  also through <em>Accept and Upward</em>.
                </li>
                <li>
                  <strong style={{ color: 'var(--risk)' }}>Risk</strong> — high-quality stretch
                  targets that in practice need you to decline your seat. Big gain if it lands, a
                  real fall if it does not.
                </li>
              </ul>
              <div className="callout warn">
                Upward movement only considers choices ranked <strong>above</strong> your current
                allotment in your own choice list. A college suggested here is reachable in upward
                movement only if you had already placed it higher; otherwise it has to be pursued in
                a later round.
              </div>
            </div>
          )}

          {result && (
            <>
              <CurrentAllotment current={result.current_allotment} />

              {result.warnings?.length > 0 && (
                <div style={{ margin: '18px 0' }}>
                  {result.warnings.map((warning) => (
                    <div className="callout warn" key={warning}>{warning}</div>
                  ))}
                </div>
              )}

              <div className="card">
                <div className="tabs">
                  {MODES.map((m) => (
                    <button
                      key={m}
                      type="button"
                      data-mode={m}
                      className={`tab ${mode === m ? 'active' : ''}`}
                      onClick={() => setMode(m)}
                    >
                      {result.modes[m].definition.label}
                      <span className="count">{result.modes[m].option_count}</span>
                    </button>
                  ))}
                </div>

                {active && (
                  <>
                    <div style={{ fontSize: '0.85rem', color: 'var(--muted)', marginBottom: 14 }}>
                      <strong>{active.definition.objective}</strong>
                      <div style={{ marginTop: 3 }}>
                        Probability band: {active.definition.probability_band}
                      </div>
                    </div>

                    <VerdictCard mode={mode} verdict={active.verdict} definition={active.definition} />

                    {active.options.length === 0 ? (
                      <div className="empty">
                        Nothing falls in this probability band for your rank, community and round.
                        That is a real result, not a gap in the data.
                      </div>
                    ) : (
                      active.options.map((option, index) => (
                        <OptionCard
                          key={`${option.college_code}-${option.branch_code}`}
                          option={option}
                          rank={index + 1}
                        />
                      ))
                    )}
                  </>
                )}
              </div>

              {result.unscored_available_options?.option_count > 0 && (
                <div className="card">
                  <h2>
                    Also reachable, but not quality-ranked
                    <span style={{ color: 'var(--dim)', fontWeight: 400 }}>
                      {' '}({result.unscored_available_options.option_count})
                    </span>
                  </h2>
                  <div className="callout warn" style={{ marginBottom: 14 }}>
                    {result.unscored_available_options.explanation}
                  </div>
                  {result.unscored_available_options.options.map((option) => (
                    <OptionCard
                      key={`u-${option.college_code}-${option.branch_code}`}
                      option={option}
                      hideUnscorableReason
                    />
                  ))}
                </div>
              )}

              <footer className="fine">
                {result.disclaimer}
                <div style={{ marginTop: 8 }}>
                  Evaluated {result.scored_candidates} quality-scored and{' '}
                  {result.unscored_candidates} unscored college-branch combinations for this query.
                </div>
              </footer>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
