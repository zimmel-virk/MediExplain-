import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'

// This component provides the main clinician-facing safety review interface for
// MediExplain+ consultations. It loads all stored automated safety checks and
// organises warning or failed results into transcript, clinical-grounding,
// medication-safety and patient-delivery groups so they can be reviewed clearly.
// It keeps passed and unavailable checks visible in the overall status, shows the
// evidence and confidence recorded for individual warnings, and requires explicit
// clinician confirmation before sensitive STT, AI-grounding or translation warnings
// can be resolved. This ensures automated safety signals remain review aids rather
// than being silently cleared before the consultation is approved for the patient.


const GROUPS = [
  {
    key: 'transcript',
    title: 'Transcript & speech review',
    icon: '01',
    help: 'Speech confidence, timestamps, language/script and other transcript-level signals are merged here.',
  },
  {
    key: 'grounding',
    title: 'Summary grounding & clinical meaning',
    icon: '02',
    help: 'Grounding, unsupported-claim, contradiction and patient-summary meaning checks are merged here.',
  },
  {
    key: 'medication',
    title: 'Medication safety',
    icon: '03',
    help: 'Medicine identity, discrepancy, dose/number and medication-preservation warnings are merged here.',
  },
  {
    key: 'delivery',
    title: 'Translation & patient delivery',
    icon: '04',
    help: 'Translation integrity, script, number and final patient-delivery warnings are merged here.',
  },
]

function groupFor(check) {
  const type = String(check.check_type || '').toLowerCase()
  const statement = String(check.statement || '').toLowerCase()
  const text = `${type} ${statement}`

  if (
    text.includes('stt') || text.includes('speech') || text.includes('transcript') ||
    text.includes('timestamp') || text.includes('language_detect') || text.includes('diar')
  ) return 'transcript'

  if (
    text.includes('medication') || text.includes('medicine') || text.includes('drug') ||
    text.includes('dose') || text.includes('strength') || text.includes('rxnorm') ||
    text.includes('prescription')
  ) return 'medication'

  if (
    text.includes('translation') || text.includes('script') || text.includes('nllb') ||
    text.includes('number_pres') || text.includes('semantic') || text.includes('tts') ||
    text.includes('patient_delivery')
  ) return 'delivery'

  // NLI, hallucination, factuality, negation and any future unclassified safety
  // signal are kept in the clinical-meaning group so no warning is dropped.
  return 'grounding'
}

export default function SafetyChecks({ consultationId, canResolve = false }) {
  const [checks, setChecks] = useState([])
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(null)

  async function load() {
    try {
      setErr(null)
      setChecks(await api.safetyChecks(consultationId))
    } catch (e) {
      setErr(e.message)
    }
  }

  useEffect(() => {
    load()
  }, [consultationId])

  async function resolve(check) {
    const isTranslation = check.check_type === 'translation_integrity'
    const isGrounding = check.check_type === 'nli_grounding' && ['warning', 'fail'].includes(check.status)
    const isStt = check.check_type === 'stt_confidence'

    if (isTranslation) {
      const confirmed = window.confirm(
        'Confirm this only after manually reviewing the translated patient summary.\n\n' +
        'Check medicine name, dose, frequency, duration, numbers, negation and clinical meaning.\n\n' +
        'Do you confirm that the translation is correct for patient release?'
      )
      if (!confirmed) return
    }

    if (isGrounding) {
      const confirmed = window.confirm(
        'This AI-generated patient-facing claim was not automatically grounded with sufficient confidence.\n\n' +
        `Claim:\n${check.statement || '(not available)'}\n\n` +
        `Evidence:\n${check.evidence || '(not available)'}\n\n` +
        'Confirm only if you have reviewed the consultation and this claim is supported.'
      )
      if (!confirmed) return
    }

    if (isStt) {
      const confirmed = window.confirm(
        'Speech-confidence warnings can only be cleared after every highlighted transcript segment has been reviewed.\n\n' +
        'Have you completed the highlighted transcript review?'
      )
      if (!confirmed) return
    }

    setBusy(check.id)
    setErr(null)
    try {
      await api.resolveSafety(consultationId, check.id, {
        confirmTranslation: isTranslation,
        confirmGrounding: isGrounding,
      })
      await load()
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(null)
    }
  }

  const warningChecks = useMemo(
    () => checks.filter(x => ['warning', 'fail'].includes(x.status)),
    [checks]
  )

  const grouped = useMemo(() => {
    const map = Object.fromEntries(GROUPS.map(g => [g.key, []]))
    warningChecks.forEach(check => map[groupFor(check)].push(check))
    return GROUPS.map(group => ({ ...group, items: map[group.key] }))
      .filter(group => group.items.length > 0)
  }, [warningChecks])

  if (err) return <div className="error">{err}</div>

  if (!checks.length) {
    return <div className="muted">No automated safety checks are stored for this consultation.</div>
  }

  const unresolved = warningChecks.filter(x => !x.resolved).length
  const passed = checks.filter(x => x.status === 'pass').length
  const unavailable = checks.filter(x => x.status === 'unavailable').length

  return (
    <div className="merged-safety-review">
      <div className="safety-summary-strip">
        <span className="conf-badge approved">{passed} passed</span>
        <span className={`conf-badge ${unresolved ? 'medium' : 'high'}`}>{unresolved} need review</span>
        {unavailable ? <span className="conf-badge">{unavailable} unavailable</span> : null}
        <span className="merged-count">{warningChecks.length} warning records merged into {grouped.length || 0} review group{grouped.length === 1 ? '' : 's'}</span>
      </div>

      {!warningChecks.length ? (
        <div className="safety-all-clear">
          <strong>No stored warning/fail checks remain.</strong>
          <span>Passed and unavailable checks are still retained in the consultation record.</span>
        </div>
      ) : (
        <div className="warning-group-grid">
          {grouped.map(group => {
            const groupUnresolved = group.items.filter(x => !x.resolved)
            const hasFail = group.items.some(x => x.status === 'fail' && !x.resolved)
            return (
              <section className={`warning-group-card ${groupUnresolved.length ? 'needs-review' : 'resolved'} ${hasFail ? 'has-fail' : ''}`} key={group.key}>
                <div className="warning-group-head">
                  <div className="warning-group-icon">{group.icon}</div>
                  <div>
                    <h3>{group.title}</h3>
                    <p>{group.help}</p>
                  </div>
                  <span className={`pill ${groupUnresolved.length ? 'warn-pill' : 'success-pill'}`}>
                    {groupUnresolved.length ? `${groupUnresolved.length} to review` : 'reviewed'}
                  </span>
                </div>

                <div className="warning-group-preview">
                  {group.items.slice(0, 2).map(item => (
                    <div className="warning-preview-row" key={item.id}>
                      <span className={`warning-dot ${item.resolved ? 'resolved' : item.status}`}></span>
                      <div>
                        <strong>{label(item.check_type)}</strong>
                        <span>{item.resolved ? 'Clinician reviewed' : item.status === 'fail' ? 'Failed check' : 'Needs review'}</span>
                      </div>
                    </div>
                  ))}
                  {group.items.length > 2 ? <div className="more-warning-count">+ {group.items.length - 2} more warning record{group.items.length - 2 === 1 ? '' : 's'} inside</div> : null}
                </div>

                <details className="warning-details">
                  <summary>Open all {group.items.length} warning record{group.items.length === 1 ? '' : 's'}</summary>
                  <div className="warning-detail-list">
                    {group.items.map(check => (
                      <WarningItem
                        key={check.id}
                        check={check}
                        canResolve={canResolve}
                        busy={busy === check.id}
                        onResolve={() => resolve(check)}
                      />
                    ))}
                  </div>
                </details>
              </section>
            )
          })}
        </div>
      )}
    </div>
  )
}

function WarningItem({ check, canResolve, busy, onResolve }) {
  const isStt = check.check_type === 'stt_confidence'
  const isNli = check.check_type === 'nli_grounding' && ['warning', 'fail'].includes(check.status)
  const isTranslation = check.check_type === 'translation_integrity'

  return (
    <div className={`warning-detail-item ${check.resolved ? 'resolved' : ''}`}>
      <div className="warning-detail-title">
        <div>
          <strong>{label(check.check_type)}</strong>
          <span>{check.status}{check.score != null ? ` · ${Math.round(check.score * 100)}%` : ''}</span>
        </div>
        {check.resolved ? <span className="conf-badge approved">clinician reviewed</span> : null}
      </div>

      {check.statement ? <p>{check.statement}</p> : null}
      {check.evidence ? <p className="muted"><strong>Evidence:</strong> {check.evidence}</p> : null}

      {!check.resolved && isStt ? <p className="muted">Review every highlighted segment in the transcript section before clearing this signal.</p> : null}
      {!check.resolved && isNli ? <p className="muted">Correct/regenerate the explanation if this claim is wrong, or explicitly confirm that the source consultation supports it.</p> : null}
      {!check.resolved && isTranslation ? <p className="muted">Verify medicine names, numbers, negation, script and clinical meaning before patient release.</p> : null}

      {canResolve && !check.resolved && check.status !== 'unavailable' ? (
        <button className="secondary compact" disabled={busy} onClick={onResolve}>
          {busy
            ? 'Saving…'
            : isStt
              ? 'Confirm transcript review complete'
              : isNli
                ? 'I confirm this claim is grounded'
                : isTranslation
                  ? 'I reviewed and confirm this translation'
                  : 'Mark this warning reviewed'}
        </button>
      ) : null}
    </div>
  )
}

function label(v) {
  return ({
    stt_confidence: 'Speech confidence',
    nli_grounding: 'Summary grounding',
    medication_match: 'Medication identity',
    medication_discrepancy: 'Consultation / prescription medication discrepancy',
    translation_integrity: 'Translation integrity',
    script_validity: 'Script validity',
    number_preservation: 'Number preservation',
    medication_preservation: 'Medication preservation',
  })[v] || String(v || 'Safety check').replaceAll('_', ' ')
}
