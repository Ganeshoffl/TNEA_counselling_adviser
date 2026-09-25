const ACTION_LABEL = {
  stay: 'Stay',
  move_up: 'Move up',
  move_up_with_risk: 'Gamble',
  pursue: 'Pursue',
  compare_not_possible: 'Cannot compare',
}

export default function VerdictCard({ mode, verdict, definition }) {
  const ev = verdict.expected_value
  const label = ACTION_LABEL[verdict.action] || verdict.action
  const headline = verdict.headline || ''
  // Avoid reading "Move up: Move up" when the headline already says the action.
  const showLabel = headline.trim().toLowerCase() !== label.trim().toLowerCase()

  return (
    <div className="verdict" data-mode={mode}>
      <div className="headline">
        {showLabel ? `${label}: ${headline}` : headline}
      </div>
      <div className="why">{verdict.reasoning}</div>

      {verdict.target && (
        <div className="metrics">
          <div className="metric">
            <div className="k">Best option</div>
            <div className="v" style={{ fontSize: '0.95rem', fontFamily: 'inherit' }}>{verdict.target}</div>
          </div>
          {verdict.current_quality != null && (
            <div className="metric">
              <div className="k">Your seat</div>
              <div className="v">{verdict.current_quality}</div>
            </div>
          )}
          {verdict.target_quality != null && (
            <div className="metric">
              <div className="k">That seat</div>
              <div className="v">{verdict.target_quality}</div>
            </div>
          )}
          {verdict.quality_uplift != null && (
            <div className="metric">
              <div className="k">Gain</div>
              <div className="v">{verdict.quality_uplift > 0 ? '+' : ''}{verdict.quality_uplift}</div>
            </div>
          )}
          {verdict.probability != null && (
            <div className="metric">
              <div className="k">Chance</div>
              <div className="v">{Math.round(verdict.probability * 100)}%</div>
            </div>
          )}
          {ev?.expected_quality != null && (
            <div className="metric">
              <div className="k">Expected</div>
              <div className="v">{ev.expected_quality}</div>
            </div>
          )}
        </div>
      )}

      {ev?.explanation && (
        <div style={{ fontSize: '0.82rem', color: 'var(--muted)', marginTop: 4 }}>{ev.explanation}</div>
      )}

      <div className="mechanism">
        <div>
          Official TNEA route: <code>{verdict.tnea_mechanism}</code>
        </div>
        <div style={{ marginTop: 5 }}>{definition.downside}</div>
      </div>
    </div>
  )
}
