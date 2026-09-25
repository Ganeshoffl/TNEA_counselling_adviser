import { useMemo, useState } from 'react'

export default function StudentForm({ meta, branches, colleges, loading, onSubmit }) {
  const [form, setForm] = useState({
    cutoff_mark: '',
    rank: '',
    community: 'OC',
    current_round: 2,
    current_college_code: '',
    current_branch_code: '',
  })
  const [collegeQuery, setCollegeQuery] = useState('')
  const [error, setError] = useState(null)

  const set = (key) => (event) => setForm((f) => ({ ...f, [key]: event.target.value }))

  const collegeMatches = useMemo(() => {
    const q = collegeQuery.trim().toLowerCase()
    if (!q) return []
    return colleges.filter((c) => c.official_name.toLowerCase().includes(q)).slice(0, 12)
  }, [collegeQuery, colleges])

  const selectedCollege = useMemo(
    () => colleges.find((c) => String(c.college_code) === String(form.current_college_code)),
    [colleges, form.current_college_code]
  )

  const branchOptions = useMemo(() => {
    if (selectedCollege?.branches?.length) {
      return selectedCollege.branches.map((code) => [code, branches[code] || code])
    }
    return Object.entries(branches)
  }, [selectedCollege, branches])

  function submit(event) {
    event.preventDefault()
    setError(null)

    const cutoff = Number(form.cutoff_mark)
    const rank = Number(form.rank)

    if (!form.cutoff_mark || Number.isNaN(cutoff) || cutoff < 0 || cutoff > 200) {
      setError('Enter a cutoff mark between 0 and 200.')
      return
    }
    if (!form.rank || Number.isNaN(rank) || rank < 1) {
      setError('Enter your TNEA rank (1 or higher).')
      return
    }
    if (form.current_college_code && !form.current_branch_code) {
      setError('You picked a current college, so also pick its branch (or clear the college).')
      return
    }

    onSubmit({
      cutoff_mark: cutoff,
      rank,
      community: form.community,
      current_round: Number(form.current_round),
      current_college_code: form.current_college_code ? Number(form.current_college_code) : null,
      current_branch_code: form.current_branch_code || null,
      limit: 10,
    })
  }

  return (
    <form className="card" onSubmit={submit}>
      <h2>Your details</h2>

      <div className="row-2">
        <div className="field">
          <label htmlFor="cutoff">Cutoff mark (out of 200)</label>
          <input
            id="cutoff"
            type="number"
            step="0.01"
            min="0"
            max="200"
            placeholder="e.g. 191.5"
            value={form.cutoff_mark}
            onChange={set('cutoff_mark')}
          />
        </div>
        <div className="field">
          <label htmlFor="rank">TNEA rank</label>
          <input
            id="rank"
            type="number"
            min="1"
            placeholder="e.g. 12000"
            value={form.rank}
            onChange={set('rank')}
          />
        </div>
      </div>

      <div className="row-2">
        <div className="field">
          <label htmlFor="community">Community</label>
          <select id="community" value={form.community} onChange={set('community')}>
            {(meta?.communities || ['OC']).map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          <div className="hint">Allotment competes within your own community.</div>
        </div>
        <div className="field">
          <label htmlFor="round">Counselling round</label>
          <select id="round" value={form.current_round} onChange={set('current_round')}>
            {(meta?.supported_rounds || [1, 2, 3, 4]).map((r) => {
              const official = (meta?.rounds_with_official_data || []).includes(r)
              return (
                <option key={r} value={r}>
                  Round {r}{official ? '' : ' (simulated)'}
                </option>
              )
            })}
          </select>
          <div className="hint">
            The round you are choosing for.
          </div>
        </div>
      </div>

      <h3>Current allotment (optional)</h3>
      <div className="field">
        <label htmlFor="college-search">Search your allotted college</label>
        <input
          id="college-search"
          type="text"
          placeholder="Type part of the college name"
          value={collegeQuery}
          onChange={(e) => setCollegeQuery(e.target.value)}
        />
        {collegeMatches.length > 0 && (
          <div className="hint">
            {collegeMatches.map((c) => (
              <div key={c.college_code} style={{ marginTop: 4 }}>
                <button
                  type="button"
                  className="link"
                  onClick={() => {
                    setForm((f) => ({
                      ...f,
                      current_college_code: String(c.college_code),
                      current_branch_code: '',
                    }))
                    setCollegeQuery('')
                  }}
                >
                  [{c.college_code}] {c.display_name}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {selectedCollege && (
        <>
          <div className="callout" style={{ marginBottom: 12 }}>
            <strong>{selectedCollege.display_name}</strong>
            <div style={{ fontSize: '0.78rem', marginTop: 3 }}>
              Code {selectedCollege.college_code} · data confidence {selectedCollege.data_confidence}
            </div>
            <button
              type="button"
              className="link"
              style={{ marginTop: 6 }}
              onClick={() =>
                setForm((f) => ({ ...f, current_college_code: '', current_branch_code: '' }))
              }
            >
              Clear
            </button>
          </div>
          <div className="field">
            <label htmlFor="branch">Allotted branch</label>
            <select id="branch" value={form.current_branch_code} onChange={set('current_branch_code')}>
              <option value="">Select a branch</option>
              {branchOptions.map(([code, name]) => (
                <option key={code} value={code}>{code} — {name}</option>
              ))}
            </select>
          </div>
        </>
      )}

      {error && <div className="callout error" style={{ marginBottom: 12 }}>{error}</div>}

      <button className="primary" type="submit" disabled={loading}>
        {loading ? 'Working…' : 'Get recommendation'}
      </button>
    </form>
  )
}
