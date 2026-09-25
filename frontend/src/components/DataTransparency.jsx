export default function DataTransparency({ meta }) {
  if (!meta) return null

  return (
    <div className="card">
      <h2>Where the data comes from</h2>
      <dl className="kv">
        <dt>Admission year</dt>
        <dd>{meta.admission_year}</dd>
        <dt>Colleges in the official TNEA list</dt>
        <dd>{meta.college_count}</dd>
        <dt>With verifiable quality data</dt>
        <dd>{meta.recommendable_count}</dd>
        <dt>Rounds published by TNEA</dt>
        <dd>{meta.rounds_with_official_data.join(', ')}</dd>
      </dl>

      <h3>Data confidence</h3>
      <ul className="legend" style={{ paddingLeft: 18, margin: 0 }}>
        {Object.entries(meta.data_confidence_legend).map(([grade, text]) => (
          <li key={grade}>
            <span className="g">{grade}</span>
            {text}
            {meta.data_confidence_counts?.[grade] != null && (
              <> <em style={{ color: 'var(--dim)' }}>({meta.data_confidence_counts[grade]} colleges)</em></>
            )}
          </li>
        ))}
      </ul>

      <h3>Quality weights</h3>
      <table className="components">
        <tbody>
          {Object.entries(meta.scoring_weights).map(([key, weight]) => (
            <tr key={key}>
              <td>{key.replace(/_/g, ' ')}</td>
              <td className="num">{Math.round(weight * 100)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p style={{ fontSize: '0.78rem', color: 'var(--dim)', marginTop: 8 }}>
        Placement carries 50% in total. Weights are a modelling choice, published so they
        can be argued with. The figures they are applied to are official.
      </p>

      <h3>Sources</h3>
      <ul className="legend" style={{ paddingLeft: 18, margin: 0 }}>
        {meta.sources.map((source) => (
          <li key={source}>{source}</li>
        ))}
      </ul>
    </div>
  )
}
