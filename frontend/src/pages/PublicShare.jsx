import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api/client'
import SafetyBanner from '../components/SafetyBanner'

/**
 * This file provides the public shared-summary page for MediExplain+. It uses the
 * signed share token in the URL to load a doctor-released consultation without
 * requiring the recipient to sign in. The page presents the patient-facing summary
 * in the correct language direction, optional summary audio, confirmed medication
 * information, warning signs and glossary explanations, and provides access to the
 * released PDF when available. It also handles expired or invalid share links and
 * keeps all public audio and document access tied to the same token-based sharing
 * workflow.
 */

export default function PublicShare() {
  const { token } = useParams()
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [langs, setLangs] = useState([])
  const [audioSrc, setAudioSrc] = useState(null)

  useEffect(() => {
    api.languages().then(setLangs).catch(() => {})
    api.getSharedView(token).then(setData).catch(e => setErr(e.message))
  }, [token])

  useEffect(() => {
    if (!data?.has_audio) return
    // No auth header is needed on /api/share/{token}/audio.
    setAudioSrc(api.sharedAudioUrl(token))
  }, [data, token])

  if (err) {
    return (
      <div className="public-shell">
        <div className="card">
          <h2>Link is no longer valid</h2>
          <p className="muted">{err}</p>
          <p className="muted">Please ask your doctor for a new link.</p>
        </div>
      </div>
    )
  }

  if (!data) return <div className="public-shell"><div className="muted">Loading…</div></div>

  const lang = langs.find(l => l.code === data.patient_language)
  const rtl = lang?.rtl
  const meds = data.structured_data?.medications || []
  const warnings = data.structured_data?.warning_signs || []
  const glossary = data.structured_data?.glossary || []

  return (
    <div className="public-shell">
      <div className="card">
        <h2>Your care summary</h2>
        <SafetyBanner />

        <h3>Summary {lang ? `(${lang.native})` : ''}</h3>
        <p className={rtl ? 'rtl' : ''} style={{ whiteSpace: 'pre-wrap' }}>
          {data.patient_summary}
        </p>

        {audioSrc && (
          <>
            <h3>Listen</h3>
            <audio controls src={audioSrc} style={{ width: '100%' }} />
          </>
        )}

        {meds.length > 0 && (
          <>
            <h3>Your medications</h3>
            <table>
              <thead>
                <tr><th>Medicine</th><th>How much</th><th>How often</th><th>For how long</th></tr>
              </thead>
              <tbody>
                {meds.map((m, i) => (
                  <tr key={i}>
                    <td>{m.name}</td><td>{m.dose}</td><td>{m.frequency}</td><td>{m.duration}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}

        {warnings.length > 0 && (
          <>
            <h3>Warning signs</h3>
            <ul>{warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
          </>
        )}

        {glossary.length > 0 && (
          <>
            <h3>Glossary</h3>
            <ul>{glossary.map((g, i) =>
              <li key={i}><strong>{g.term}</strong>: {g.plain_explanation}</li>
            )}</ul>
          </>
        )}

        {data.has_pdf && (
          <div style={{ marginTop: 18 }}>
            <a href={api.sharedPdfUrl(token)} target="_blank" rel="noreferrer"
               className="btn-pdf"
               style={{ display: 'inline-flex', textDecoration: 'none', padding: '10px 16px', borderRadius: 6 }}>
              📄 Download PDF
            </a>
          </div>
        )}
      </div>
    </div>
  )
}
