const GRADE_CLASS = { A: 'good', S: 'info', B: 'warn', U: 'bad' }
const GRADE_LABEL = {
  A: 'Grade A · Ministry-published figures',
  S: 'Grade S · college-published figures',
  B: 'Grade B · NIRF band only',
  U: 'Grade U · no NIRF data',
}

export default function CurrentAllotment({ current }) {
  if (!current) {
    return (
      <div className="callout">
        No current allotment was given, so every suggestion below is simply the best option
        available for your rank rather than a comparison against a seat you already hold.
      </div>
    )
  }

  if (!current.known) {
    return <div className="callout error">{current.message}</div>
  }

  const score = current.quality?.quality_score

  return (
    <div className="card">
      <h2>Your current allotment</h2>
      <div className="option-head">
        <div>
          <div className="option-title">{current.college_name}</div>
          <div className="option-sub">
            {current.branch_code ? `${current.branch_code} — ${current.branch_name}` : 'Branch not given'}
          </div>
        </div>
        <div className="option-num">
          <div className="q">{score ?? '—'}</div>
          <div className="p">quality score</div>
        </div>
      </div>

      <div className="badges">
        <span className="badge">Code {current.college_code}</span>
        <span className="badge">{current.institution_type.replace(/_/g, ' ')}</span>
        <span className={`badge ${GRADE_CLASS[current.data_confidence] || 'bad'}`}>
          {GRADE_LABEL[current.data_confidence] || `Data confidence ${current.data_confidence}`}
        </span>
      </div>

      {current.quality_unavailable_reason && (
        <div className="callout warn" style={{ marginTop: 12 }}>
          <strong>Quality cannot be scored.</strong> {current.quality_unavailable_reason}
        </div>
      )}
    </div>
  )
}
