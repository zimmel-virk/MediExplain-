import { useEffect, useState } from 'react'
import { api } from '../api/client'

/**
/**
 * This panel lets a patient request a second opinion for a released consultation.
 * It loads eligible reviewing doctors and any existing cross-check requests, keeps
 * the treating doctor out of the reviewer list, prevents duplicate requests to the
 * same reviewer, and shows both pending reviews and completed reviewer verdicts.
 * The second opinion is displayed separately from the original treating doctor's
 * consultation and does not directly change the patient's prescription.
 */
export default function PatientCrossCheck({ consultation, onChange }) {
  const [doctors, setDoctors] = useState([])
  const [reviews, setReviews] = useState([])
  const [pickedId, setPickedId] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [success, setSuccess] = useState(null)


    // Load both the available doctors and the cross-checks already linked to this
  // consultation so the reviewer list and review status stay in sync.

  async function loadAll() {
    try {
      const [docs, ccs] = await Promise.all([
        api.listDoctors(),
        api.crossChecksForConsultation(consultation.id),
      ])
      // Exclude the treating doctor — they can't review their own case
      setDoctors(docs.filter(d => d.id !== consultation.doctor_id))
      setReviews(ccs)
    } catch (e) { setErr(e.message) }
  }

  useEffect(() => { loadAll() }, [consultation.id])

  async function requestReview() {
    if (!pickedId) return setErr('Please choose a doctor to review your case.')
    setBusy(true); setErr(null); setSuccess(null)
    try {
      await api.requestCrossCheck({
        consultation_id: consultation.id,
        reviewer_id: Number(pickedId),
      })
            // A second opinion must come from a different doctor, so the treating
      // doctor is removed from the list of available reviewers.
      setSuccess('Your request has been sent. The doctor will review and reply soon.')
      setPickedId('')
      await loadAll()
      onChange?.()
    } catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }

    // Keep outstanding requests separate from completed second opinions so the
  // patient can clearly see which reviews are still waiting for a response.
  
  const pendingReviews = reviews.filter(r => r.request_status !== 'completed')
  const completedReviews = reviews.filter(r => r.request_status === 'completed')

  // IDs of doctors the patient has already asked → hide from the picker so
  // they don't accidentally ask the same person twice.
  const askedAlready = new Set(reviews.map(r => r.reviewer_id))
  const availableDoctors = doctors.filter(d => !askedAlready.has(d.id))

  return (
    <div style={{ marginTop: 20 }}>
      <h3>Want a second opinion?</h3>
      <p className="muted">
        You can ask another doctor to review your summary. This does not change
        your prescription — it just gives you a second medical view of your case.
      </p>

      {availableDoctors.length === 0 && reviews.length === 0 ? (
        <div className="muted">No other doctors are currently available for review.</div>
      ) : null}

      {availableDoctors.length > 0 ? (
        <div style={{ marginTop: 10 }}>
          <label>Choose a doctor to review your case</label>
          <select value={pickedId} onChange={e => setPickedId(e.target.value)}
                  disabled={busy}>
            <option value="">— Pick a doctor —</option>
            {availableDoctors.map(d => (
              <option key={d.id} value={d.id}>
                {d.full_name}
                {d.specialty ? ' · ' + d.specialty : ''}
                {d.clinic ? ' · ' + d.clinic : ''}
              </option>
            ))}
          </select>
          <div style={{ marginTop: 10 }}>
            <button onClick={requestReview} disabled={busy || !pickedId}>
              {busy ? 'Sending request…' : 'Request second opinion'}
            </button>
          </div>
        </div>
      ) : null}

      {err ? <div className="error">{err}</div> : null}
      {success ? <div className="success">{success}</div> : null}

      {pendingReviews.length > 0 ? (
        <div style={{ marginTop: 16 }}>
          <h3 style={{ fontSize: 14 }}>Waiting for review</h3>
          {pendingReviews.map(r => {
            const doc = doctors.find(d => d.id === r.reviewer_id)
            return (
              <div key={r.id} className="quality-notice" style={{ marginBottom: 6 }}>
                ⏳ Awaiting reply from {doc ? doc.full_name : `doctor #${r.reviewer_id}`}
                {doc?.specialty ? ' (' + doc.specialty + ')' : ''} —
                requested {new Date(r.created_at).toLocaleString()}
              </div>
            )
          })}
        </div>
      ) : null}

      {completedReviews.length > 0 ? (
        <div style={{ marginTop: 16 }}>
          <h3 style={{ fontSize: 14 }}>Second opinions received</h3>
          {completedReviews.map(r => {
            const doc = doctors.find(d => d.id === r.reviewer_id)
            const verdictLabel = {
              'agree': '✓ Agrees with your treating doctor',
              'partially_agree': '◐ Partially agrees',
              'disagree': '⚠ Disagrees with part of the treating plan',
              'suggest_followup': '⓲ Suggests a follow-up visit',
              'flag': '⚠ Flagged a concern',
            }[r.verdict] || r.verdict
            const verdictClass = r.verdict === 'agree' ? 'success'
                               : r.verdict === 'flag' ? 'quality-warning'
                               : 'quality-notice'
            return (
              <div key={r.id} className={verdictClass} style={{ marginBottom: 8 }}>
                <strong>{doc ? doc.full_name : `Doctor #${r.reviewer_id}`}</strong>
                {doc?.specialty ? ' (' + doc.specialty + ')' : ''}
                <div style={{ marginTop: 4 }}>{verdictLabel}</div>
                {r.comments ? (
                  <div style={{ marginTop: 8, fontStyle: 'italic' }}>
                    "{r.comments}"
                  </div>
                ) : null}
              </div>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}
