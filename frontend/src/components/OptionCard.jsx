function percent(value) {
  if (value === null || value === undefined) return '—'
  return `${Math.round(value * 100)}%`
}

const GRADE_CLASS = { A: 'good', S: 'info', B: 'warn', U: 'bad' }
const GRADE_LABEL = {
  A: 'Grade A · Ministry-published figures',
  S: 'Grade S · college-published figures',
  B: 'Grade B · NIRF band only',
  U: 'Grade U · no NIRF data',
}

function availabilityBadge(admission) {
  const seats = admission.seats_vacant_entering_round
  if (admission.availability === 'none') {
    return <span className="badge bad">No seats were vacant</span>
  }
  if (admission.availability === 'unknown') {
    return <span className="badge warn">Vacancy not published</span>
  }
  const cls = admission.availability === 'scarce' ? 'badge warn' : 'badge good'
  return <span className={cls}>{seats} seat(s) vacant entering the round</span>
}

export default function OptionCard({ option, rank, hideUnscorableReason = false }) {
  const { quality, admission } = option
  const scorable = quality.quality_score !== null && quality.quality_score !== undefined

  return (
    <div className="option">
      <div className="option-head">
        <div>
          <div className="option-title">
            {rank ? `${rank}. ` : ''}{option.college_name}
          </div>
          <div className="option-sub">
            {option.branch_code} — {option.branch_name}
            {option.city ? ` · ${option.city}` : ''}
          </div>
        </div>
        <div className="option-num">
          <div className="q">{scorable ? quality.quality_score : '—'}</div>
          <div className="p">{percent(admission.probability)} chance</div>
        </div>
      </div>

      <div className="badges">
        <span className="badge">Code {option.college_code}</span>
        {option.data_confidence && (
          <span className={`badge ${GRADE_CLASS[option.data_confidence] || ''}`}>
            {GRADE_LABEL[option.data_confidence] || option.data_confidence}
          </span>
        )}
        {option.nirf?.rank ? (
          <span className="badge good">NIRF {option.nirf.year} rank {option.nirf.rank}</span>
        ) : option.nirf?.rank_band ? (
          <span className="badge">NIRF {option.nirf.year} band {option.nirf.rank_band}</span>
        ) : null}
        <span className="badge">{option.fee_band?.band}</span>
        {availabilityBadge(admission)}
        <span className="badge">
          Closing rank {admission.closing_rank?.toLocaleString('en-IN')} (round {admission.evidence_round})
        </span>
        {scorable && quality.evidence_completeness < 1 && (
          <span className="badge warn">
            Evidence {Math.round(quality.evidence_completeness * 100)}% complete
          </span>
        )}
      </div>

      {admission.notes?.length > 0 && (
        <ul className="notes">
          {admission.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}

      {!scorable && quality.unscorable_reason && !hideUnscorableReason && (
        <div className="callout warn" style={{ marginTop: 10 }}>
          <strong>No quality score.</strong> {quality.unscorable_reason}
        </div>
      )}
      {!scorable && hideUnscorableReason && (
        <div style={{ marginTop: 8, fontSize: '0.8rem', color: 'var(--dim)' }}>
          No quality score: NIRF publishes no placement figure for this college.
        </div>
      )}

      {scorable && option.data_confidence === 'S' && (
        <div style={{ marginTop: 10, fontSize: '0.8rem', color: '#c4b5fd' }}>
          Placement and laboratory figures for this college come from its own NIRF
          submission published on its website, because the Ministry publishes
          per-institute data only down to rank 200. The document was checked for the
          right submission year, the Engineering category and a matching institute
          identity, but it is not a Ministry-hosted copy.
        </div>
      )}

      {scorable && (
        <details className="disclosure">
          <summary>How this quality score of {quality.quality_score} is built</summary>
          <table className="components">
            <thead>
              <tr>
                <th>Factor</th>
                <th>Weight</th>
                <th>Official figure</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {quality.components.map((component) => (
                <tr key={component.component} className={component.available ? '' : 'absent'}>
                  <td>{component.label}</td>
                  <td className="num">{Math.round(component.weight * 100)}%</td>
                  <td>
                    {component.available ? component.value : <em>{component.reason}</em>}
                    {component.as_of ? ` (${component.as_of})` : ''}
                    {component.hosted_by === 'institution' && (
                      <span className="selfhosted-flag" title={component.caveat}>
                        college-hosted
                      </span>
                    )}
                    {component.basis ? <div style={{ fontSize: '0.74rem', opacity: 0.75 }}>{component.basis}</div> : null}
                    {component.host_note ? <div style={{ fontSize: '0.74rem', opacity: 0.75 }}>{component.host_note}</div> : null}
                  </td>
                  <td>
                    {component.source_url ? (
                      <a href={component.source_url} target="_blank" rel="noreferrer">
                        {component.hosted_by === 'institution' ? 'college copy' : 'official document'}
                      </a>
                    ) : component.source ? (
                      <span style={{ fontSize: '0.74rem', opacity: 0.8 }}>{component.source}</span>
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {quality.scoring_note && (
            <p style={{ fontSize: '0.78rem', color: 'var(--dim)', marginTop: 10 }}>{quality.scoring_note}</p>
          )}
        </details>
      )}

      <details className="disclosure">
        <summary>How this {percent(admission.probability)} chance is estimated</summary>
        <dl className="kv" style={{ marginTop: 10 }}>
          <dt>Official closing rank</dt>
          <dd>{admission.closing_rank?.toLocaleString('en-IN')} (round {admission.evidence_round})</dd>
          <dt>Official opening rank</dt>
          <dd>{admission.opening_rank?.toLocaleString('en-IN')}</dd>
          {admission.closing_mark != null && (
            <>
              <dt>Lowest mark allotted</dt>
              <dd>{admission.closing_mark} / 200</dd>
            </>
          )}
          <dt>Seats allotted then</dt>
          <dd>{admission.seats_allotted_in_evidence_round ?? '—'}</dd>
          <dt>Seats vacant entering round</dt>
          <dd>{admission.seats_vacant_entering_round ?? 'not published'}</dd>
          <dt>Rank component</dt>
          <dd>{percent(admission.rank_component)}</dd>
          <dt>Scarcity discount</dt>
          <dd>×{admission.availability_factor}</dd>
        </dl>
        <p style={{ fontSize: '0.78rem', color: 'var(--dim)', marginTop: 10 }}>{admission.method}</p>
      </details>
    </div>
  )
}
