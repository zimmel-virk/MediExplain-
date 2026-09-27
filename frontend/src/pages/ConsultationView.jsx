import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { api } from '../api/client'
import { useAuth } from '../api/auth'

import AuthAudio from '../components/AuthAudio'
import SafetyBanner from '../components/SafetyBanner'
import LanguagePicker from '../components/LanguagePicker'
import PrescriptionUpload from '../components/PrescriptionUpload'
import ShareDialog from '../components/ShareDialog'
import MedicationEditor from '../components/MedicationEditor'
import PatientCrossCheck from '../components/PatientCrossCheck'
import TranscriptReview from '../components/TranscriptReview'
import SafetyChecks from '../components/SafetyChecks'
import MedicationSchedulePanel from '../components/MedicationSchedulePanel'
import WhatsAppDelivery from '../components/WhatsAppDelivery'


/**
 * This file provides the main consultation workspace for MediExplain+ and changes
 * what is shown according to the signed-in user's role and the consultation state.
 * It keeps processing consultations refreshed while the AI pipeline is running and
 * brings together the complete clinical workflow for the treating doctor, including
 * transcript review, regeneration after transcript corrections, the AI-generated
 * clinical draft, patient-summary editing, multilingual translation, merged safety
 * checks, prescription OCR, medication verification, assistant pre-review, final
 * doctor approval, patient release, PDF generation, WhatsApp delivery and previous
 * cross-check results. For patients, it presents the released summary, translated
 * text, protected audio, confirmed medications, reminder schedules, warning signs,
 * glossary, PDF download and second-opinion requests. It also provides the separate
 * assigned-review view used by cross-check doctors to inspect the consultation,
 * review its safety information and submit an independent verdict without replacing
 * the treating doctor's original clinical decision.
 */

const POLL_MS = 3500

const PROCESSING = new Set([
  'recording',
  'transcribing',
  'transcribed',
  'transcript_review',
  'summarising',
  'safety_check',
  'translating',
])


export default function ConsultationView() {
  const { id } = useParams()
  const { user } = useAuth()

  const [c, setC] = useState(null)
  const [err, setErr] = useState(null)
  const [edit, setEdit] = useState('')

  const [reviews, setReviews] = useState([])
  const [doctors, setDoctors] = useState([])
  const [langs, setLangs] = useState([])

  const [busy, setBusy] = useState(false)
  const [assistantReview, setAssistantReview] = useState(null)


  async function refresh() {
    const x = await api.getConsultation(id)
    setC(x)
    return x
  }


  useEffect(() => {
    let active = true
    let timer

    async function tick() {
      try {
        const x = await api.getConsultation(id)

        if (!active) return

        setC(x)

        if (PROCESSING.has(x.status)) {
          timer = setTimeout(
            tick,
            POLL_MS
          )
        }
      } catch (e) {
        if (active) {
          setErr(e.message)
        }
      }
    }

    tick()

    return () => {
      active = false

      if (timer) {
        clearTimeout(timer)
      }
    }
  }, [id])


  useEffect(() => {
    api.languages()
      .then(setLangs)
      .catch(() => {})
  }, [])


  useEffect(() => {
    if (!c?.id) return

    api.crossChecksForConsultation(c.id)
      .then(setReviews)
      .catch(() => {})

    api.listDoctors()
      .then(setDoctors)
      .catch(() => {})
  }, [c?.id, c?.status])


  useEffect(() => {
    if (!c?.id) return

    if (!['doctor', 'admin'].includes(user.role)) {
      setAssistantReview(null)
      return
    }

    let active = true
    async function loadAssistantReview() {
      try {
        const review = await api.latestAssistantReview(c.id)
        if (active) setAssistantReview(review)
      } catch {
        if (active) setAssistantReview(null)
      }
    }
    loadAssistantReview()
    const timer = setInterval(loadAssistantReview, 5000)
    return () => { active = false; clearInterval(timer) }
  }, [c?.id, c?.status, user.role])


  useEffect(() => {
    if (!c) return

    setEdit(
      c.doctor_edited_summary ||
      c.patient_summary_en ||
      ''
    )
  }, [
    c?.id,
    c?.patient_summary_en,
    c?.doctor_edited_summary,
  ])


  if (err) {
    return (
      <div className="container">
        <div className="error">
          {err}
        </div>
      </div>
    )
  }


  if (!c) {
    return (
      <div className="container">
        <div className="muted">
          Loading…
        </div>
      </div>
    )
  }


  const isTreating =
    (
      user.role === 'doctor' ||
      user.role === 'admin'
    ) &&
    (
      user.role === 'admin' ||
      c.doctor_id === user.id
    )


  const isReviewer =
    user.role === 'cross_check_doctor' ||
    (
      user.role === 'doctor' &&
      !isTreating
    )


  const processing = PROCESSING.has(
    c.status
  )


  const meds =
    c.structured_data?.medications || []


  const langMeta = langs.find(
    l => l.code === c.patient_language
  )


  const rtl = langMeta?.rtl


  const transcriptStale = Boolean(
    c.model_metadata
      ?.reviewed_transcript_stale
  )


  const editableSummary = [
    'drafted',
    'safety_review_required',
  ].includes(c.status)


  // Do not allow the doctor to approve/edit an old
  // patient summary after changing the transcript.
  const summaryReadyForReview =
    editableSummary &&
    !transcriptStale


  async function act(fn) {
    setBusy(true)
    setErr(null)

    try {
      const result = await fn()

      if (result) {
        setC(result)
      }

      return result
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }


  const approve = () =>
    act(() =>
      api.approve(
        c.id,
        {
          edited_summary: edit,
          approve: true,
        }
      )
    )


  const regenerateReviewed = () =>
    act(() =>
      api.regenerateReviewedTranscript(
        c.id
      )
    )


  const release = () => {
    const incomplete = meds.filter(
      m => {
        const frequency = (
          m.frequency || ''
        ).trim()

        const duration = (
          m.duration || ''
        ).trim()

        const f =
          frequency.toLowerCase()

        const prn =
          m.as_needed ||
          f.includes('as needed') ||
          f.includes('prn')

        return (
          !prn &&
          (
            !frequency ||
            !duration
          )
        )
      }
    )


    if (incomplete.length) {
      const names = incomplete
        .map(
          m =>
            m.name ||
            m.canonical_name ||
            'Medication'
        )
        .join(', ')

      setErr(
        `Cannot release yet. Complete frequency and duration for: ${names}. ` +
        `MediExplain+ will not invent medication duration.`
      )

      return
    }


    return act(() =>
      api.release(c.id)
    )
  }


  const retranslate = lang =>
    act(() =>
      api.retranslate(
        c.id,
        lang
      )
    )


  async function addMed() {
    await act(() =>
      api.addMedication(
        c.id,
        {
          name: '',
          dose: '',
          frequency: '',
          duration: '',
          confirm_identity: false,
          confirm_instructions: false,
        }
      )
    )
  }


  async function downloadPdf() {
    setErr(null)

    try {
      const token =
        localStorage.getItem(
          'mxp_token'
        )

      const res = await fetch(
        api.pdfUrl(c.id),
        {
          headers: {
            Authorization:
              'Bearer ' + token,
          },
        }
      )

      if (!res.ok) {
        let message =
          res.statusText

        try {
          const body =
            await res.json()

          message =
            body.detail ||
            message
        } catch {}

        throw new Error(message)
      }

      const blob =
        await res.blob()

      const url =
        URL.createObjectURL(blob)

      const a =
        document.createElement('a')

      a.href = url

      a.download =
        `care_summary_${c.id}.pdf`

      a.click()

      URL.revokeObjectURL(url)

    } catch (e) {
      setErr(e.message)
    }
  }


  return (
    <main className="page">
      <div className="breadcrumb">
        <Link to="/">Dashboard</Link>
        <span>›</span>
        <span>Consultation #{c.id}</span>
      </div>

      <section className="case-header">
        <div>
          <span className="eyebrow">CASE #{c.id}</span>
          <h1>{isTreating ? 'Consultation review' : user.role === 'patient' ? 'Your consultation' : 'Clinical cross-check'}</h1>
          <p>Patient language: <strong>{langMeta?.native || c.patient_language?.toUpperCase() || 'Not set'}</strong></p>
        </div>
        <span className={`badge large-badge ${c.status}`}>{c.status.replaceAll('_', ' ')}</span>
      </section>

      {processing ? (
        <div className="info-panel">
          AI pipeline is processing the consented consultation. Speech, structured extraction, independent summaries, safety checks, translation and audio remain separate stages. This page refreshes automatically.
        </div>
      ) : null}

      {c.pipeline_error ? (
        <div className="quality-warning">
          <strong>Pipeline warning:</strong> {c.pipeline_error}
        </div>
      ) : null}

      {isTreating && !processing ? (
        <DoctorView
          c={c}
          setC={setC}
          edit={edit}
          setEdit={setEdit}
          meds={meds}
          langMeta={langMeta}
          rtl={rtl}
          busy={busy}
          editableSummary={summaryReadyForReview}
          transcriptStale={transcriptStale}
          approve={approve}
          release={release}
          regenerateReviewed={regenerateReviewed}
          retranslate={retranslate}
          addMed={addMed}
          refresh={refresh}
          reviews={reviews}
          doctors={doctors}
          assistantReview={assistantReview}
          downloadPdf={downloadPdf}
        />
      ) : null}

      {user.role === 'patient' ? (
        <PatientView
          c={c}
          meds={meds}
          langMeta={langMeta}
          rtl={rtl}
          busy={busy}
          retranslate={retranslate}
          downloadPdf={downloadPdf}
          refresh={refresh}
        />
      ) : null}

      {isReviewer ? <CrossCheckPanel consultation={c} /> : null}
    </main>
  )
}



function DoctorView({
  c,
  setC,
  edit,
  setEdit,
  meds,
  langMeta,
  rtl,
  busy,
  editableSummary,
  transcriptStale,
  approve,
  release,
  regenerateReviewed,
  retranslate,
  addMed,
  refresh,
  reviews,
  doctors,
  assistantReview,
  downloadPdf,
}) {
  const [assistants, setAssistants] = useState([])
  const [assistantId, setAssistantId] = useState('')
  const [assistantBusy, setAssistantBusy] = useState(false)
  const [assistantErr, setAssistantErr] = useState(null)
  const [assistantNotice, setAssistantNotice] = useState(null)

  useEffect(() => {
    let active = true
    api.listAssistants()
      .then(rows => { if (active) setAssistants(rows || []) })
      .catch(() => { if (active) setAssistants([]) })
    return () => { active = false }
  }, [c.id])

  async function sendToAssistant() {
    if (!assistantId) {
      setAssistantErr('Choose an assistant first.')
      return
    }
    setAssistantBusy(true)
    setAssistantErr(null)
    setAssistantNotice(null)
    try {
      await api.assignAssistant({
        consultation_id: c.id,
        assistant_id: Number(assistantId),
      })
      setAssistantNotice('Sent for assistant pre-review. Final approval and release remain with you.')
      await refresh()
    } catch (e) {
      setAssistantErr(e.message)
    } finally {
      setAssistantBusy(false)
    }
  }

  const locked = ['approved', 'released', 'under_cross_check', 'cross_checked'].includes(c.status)
  const released = Boolean(c.released_at) || ['released', 'under_cross_check', 'cross_checked'].includes(c.status)
  const assistantPending = assistantReview?.status === 'pending'
  const assistantReturned = assistantReview?.status === 'reviewed'

  return (
    <div className="doctor-review-page">
      {assistantNotice ? <div className="success panel">{assistantNotice}</div> : null}
      {assistantErr ? <div className="error panel">{assistantErr}</div> : null}

      {assistantPending ? (
        <div className="assistant-signal pending">
          <div>
            <strong>Assistant pre-review in progress</strong>
            <p>The assigned assistant can inspect only this case and return a checklist/notes. They cannot approve or release it. Final clinical review stays with the treating doctor.</p>
          </div>
          <span className="pill warn-pill">Waiting for assistant</span>
        </div>
      ) : null}

      {assistantReturned ? (
        <div className="assistant-signal reviewed">
          <div>
            <strong>Assistant has checked this case</strong>
            <p>The pre-review has returned to you. Re-check the original transcript, merged warning groups, medication information and patient wording before final approval.</p>
            {assistantReview.notes ? (
              <div className="assistant-note"><strong>Assistant note:</strong> {assistantReview.notes}</div>
            ) : null}
          </div>
          <span className="pill success-pill">Checked & returned</span>
        </div>
      ) : null}

      {c.code_switched ? (
        <div className="cs-banner">
          <strong>Mixed-language transcription mode was used.</strong>{' '}
          The original STT output is preserved. Segment corrections create the reviewed transcript without replacing the immutable source.
        </div>
      ) : null}

      <section className="grid-2 doctor-source-grid">
        <div className="card">
          <div className="section-head">
            <div>
              <div><span className="step">01</span><h2>Source consultation</h2></div>
              <p>Review the exact recognised consultation before checking any generated content.</p>
            </div>
          </div>

          <label>Raw transcript — immutable source</label>
          <textarea
            readOnly
            value={c.raw_transcript || ''}
            className={`tall ${['ur', 'pa_shah', 'ps', 'sd', 'ar'].includes(c.stt_primary_language) ? 'rtl' : ''}`}
          />
          <p className="field-note">Your original multilingual STT, code-switch, confidence and Shahmukhi safeguards are unchanged.</p>

          {(c.model_metadata?.doctor_transcript_en || (c.languages_detected?.length === 1 && c.languages_detected[0] === 'en')) ? (
            <details className="tool-details">
              <summary>Open doctor working transcript — English</summary>
              <textarea
                readOnly
                value={c.model_metadata?.doctor_transcript_en || c.raw_transcript || ''}
                className="doctor-working-transcript"
              />
              <p className="field-note">This is a review aid, not the patient-facing summary.</p>
            </details>
          ) : null}

          <details className="tool-details" open>
            <summary>Review transcript segments</summary>
            <TranscriptReview
              consultationId={c.id}
              readOnly={locked}
              onChanged={refresh}
            />
          </details>

          {transcriptStale ? (
            <div className="quality-warning compact-warning">
              <strong>⚠ Transcript changed by the doctor</strong>
              <p>The existing clinical note, patient explanation, medication extraction, safety checks, translation and audio were produced from the previous transcript.</p>
              <button onClick={regenerateReviewed} disabled={busy}>
                {busy ? 'Regenerating…' : '↻ Regenerate from doctor-reviewed transcript'}
              </button>
            </div>
          ) : null}
        </div>

        <div className="card">
          <div className="section-head">
            <div>
              <div><span className="step">02</span><h2>Clinical draft</h2></div>
              <p>Internal clinician-facing SOAP draft generated from the reviewed consultation source.</p>
            </div>
          </div>
          <label>AI clinical note — English SOAP draft</label>
          <textarea readOnly value={c.clinical_note || ''} className="tall" />
          <p className="field-note">This content is for clinician review and is not released directly to the patient.</p>
        </div>
      </section>

      <section className="card">
        <div className="section-head">
          <div>
            <div><span className="step">03</span><h2>Patient explanation</h2></div>
            <p>Edit the patient-facing English source before final approval. Translation and audio remain downstream of the doctor-reviewed version.</p>
          </div>
        </div>

        {transcriptStale ? (
          <div className="quality-warning compact-warning">This summary is outdated because the transcript was corrected. Regenerate the AI outputs before making final edits.</div>
        ) : null}

        <textarea
          value={edit}
          onChange={e => setEdit(e.target.value)}
          disabled={!editableSummary}
          className="summary-editor"
        />

        <div className="patient-version-tools">
          <div>
            <label>Patient output language</label>
            <LanguagePicker
              value={c.patient_language}
              onChange={retranslate}
              disabled={busy || transcriptStale || locked}
            />
          </div>
          <span className="field-note">Language conversion still uses the original MediExplain+ translation/script pipeline.</span>
        </div>

        {c.patient_summary_translated && c.patient_language !== 'en' ? (
          <div className="translation-box">
            <div className="translation-head">
              <div>
                <strong>Current {langMeta?.native || c.patient_language} version</strong>
                <span className={`pill ${c.translation_verified ? 'success-pill' : 'warn-pill'}`}>
                  {c.translation_verified ? 'integrity checks passed' : 'doctor review required'}
                </span>
              </div>
              <button className="ghost compact" disabled={busy || transcriptStale || locked} onClick={() => retranslate(c.patient_language)}>
                Regenerate translation
              </button>
            </div>
            <p className={rtl ? 'rtl' : ''}>{c.patient_summary_translated}</p>
            <small>Review medicine names, numbers, frequency, duration, negation and clinical meaning before release.</small>
          </div>
        ) : null}
      </section>

      <section className="grid-2 doctor-safety-med-grid">
        <div className="card">
          <div className="section-head">
            <div>
              <div><span className="step">04</span><h2>Merged safety review</h2></div>
              <p>Every stored warning is retained, but related warnings are merged into at most four review groups to reduce repeated checking.</p>
            </div>
          </div>
          <SafetyChecks consultationId={c.id} canResolve={true} />
        </div>

        <div className="card">
          <div className="section-head">
            <div>
              <div><span className="step">05</span><h2>Medication verification</h2></div>
              <p>Keep medicine identity, dose, frequency, timing and duration explicit. The original confirmation rules remain unchanged.</p>
            </div>
          </div>

          <div className="prescription-subsection">
            <h3>Prescription OCR</h3>
            {locked ? (
              <div className="muted">Prescription processing is locked after doctor approval.</div>
            ) : (
              <PrescriptionUpload consultationId={c.id} onExtracted={refresh} />
            )}
          </div>

          <div className="medication-subsection">
            <h3>Medication instructions</h3>
            {!meds.length ? <div className="empty-inline">No medication instructions extracted.</div> : null}
            {meds.map((m, i) => (
              <MedicationEditor
                key={`${i}-${m.name || m.canonical_name || ''}`}
                consultationId={c.id}
                index={i}
                med={m}
                readOnly={released}
                onChange={setC}
              />
            ))}
            {!released ? (
              <button className="secondary" onClick={addMed} disabled={busy}>+ Add medication manually</button>
            ) : null}
          </div>
        </div>
      </section>

      <section className="card release-card">
        <div className="section-head">
          <div>
            <div><span className="step">06</span><h2>Choose the review pathway</h2></div>
            <p>Review directly or send the same case to an authorised assistant for a first-pass check. The assistant cannot approve or release patient content.</p>
          </div>
        </div>

        {!released && c.status !== 'approved' ? (
          assistantPending ? (
            <div className="pending-panel">
              <div className="spinner-dot"></div>
              <div>
                <strong>Assistant review in progress</strong>
                <p>Patient release stays blocked until the assigned assistant selects “I have checked this case” and returns the checklist.</p>
              </div>
            </div>
          ) : (
            <div className="path-grid">
              <div className="path-card primary-path">
                <div className="path-icon">✓</div>
                <h3>{assistantReturned ? 'Complete final doctor review' : 'Doctor reviews directly'}</h3>
                <p>{assistantReturned ? 'The assistant has returned the case. Review their note and complete your own final clinical communication decision.' : 'Complete the review yourself using the original transcript, merged warning groups and confirmed medication information.'}</p>
                <button disabled={busy || transcriptStale || !editableSummary} onClick={approve}>
                  {busy ? 'Working…' : 'Final doctor approval'}
                </button>
              </div>

              <div className={`path-card ${assistantReturned ? 'path-card-complete' : ''}`}>
                <div className="path-icon">↗</div>
                <h3>{assistantReturned ? 'Assistant pre-review completed' : 'Send to assistant first'}</h3>
                {assistantReturned ? (
                  <>
                    <p>The assistant checklist is complete. Final approval still belongs only to the treating doctor.</p>
                    {assistantReview.notes ? <div className="assistant-note"><strong>Assistant note:</strong> {assistantReview.notes}</div> : null}
                  </>
                ) : assistants.length ? (
                  <>
                    <p>Assign an authorised assistant to inspect the transcript, patient explanation, medications, warnings and translation before the case returns to you.</p>
                    <select value={assistantId} onChange={e => setAssistantId(e.target.value)}>
                      <option value="">Select assistant…</option>
                      {assistants.map(a => <option key={a.id} value={a.id}>{a.full_name}{a.specialty ? ` · ${a.specialty}` : ''}</option>)}
                    </select>
                    <button className="secondary wide" disabled={assistantBusy || !assistantId || transcriptStale} onClick={sendToAssistant}>
                      {assistantBusy ? 'Sending…' : 'Send for assistant review'}
                    </button>
                  </>
                ) : (
                  <div className="empty-inline">No active verified assistant account is currently provisioned. Use the direct doctor pathway.</div>
                )}
              </div>
            </div>
          )
        ) : null}

        {c.status === 'approved' && !released ? (
          <div className="assistant-return">
            <div>
              <span className="pill success-pill">Doctor approved</span>
              <h3>Ready for patient release</h3>
              <p>Release only after the patient-facing wording, all unresolved safety warnings and medication instructions have been checked. Reminder schedules still follow the original deterministic scheduler rules.</p>
            </div>
            <button disabled={busy} onClick={release}>{busy ? 'Releasing…' : 'Release to patient'}</button>
          </div>
        ) : null}

        {released ? (
          <div className="released-panel">
            <strong>Patient release completed</strong>
            <p>The patient can access the doctor-released summary, confirmed medicines, audio/PDF where available, and deterministic medication reminders.</p>
          </div>
        ) : null}
      </section>

      <WhatsAppDelivery
        consultation={c}
        downloadPdf={downloadPdf}
      />

      {reviews.length ? (
        <section className="card">
          <div className="section-head"><div><h2>Cross-check reviews</h2><p>This remains the original independent cross-check pathway and is separate from assistant pre-review.</p></div></div>
          {reviews.map(r => {
            const d = doctors.find(x => x.id === r.reviewer_id)
            return (
              <div key={r.id} className={r.verdict === 'disagree' || r.verdict === 'flag' ? 'quality-warning' : 'quality-notice'}>
                <strong>{d?.full_name || `Doctor #${r.reviewer_id}`}</strong>{' · '}{r.request_status}{' · '}{r.verdict}
                {r.reason ? <div>Reason: {r.reason}</div> : null}
                {r.comments ? <div>Comment: {r.comments}</div> : null}
              </div>
            )
          })}
        </section>
      ) : null}

      {c.released_at ? (
        <section className="card delivery-card">
          <div className="section-head">
            <div><span className="step">07</span><h2>Released patient documents</h2><p>Use the exact doctor-released consultation content for PDF and WhatsApp delivery.</p></div>
            <button className="secondary" disabled={busy} onClick={downloadPdf}>Download patient PDF</button>
          </div>
          <ShareDialog consultationId={c.id} />
        </section>
      ) : null}
    </div>
  )
}


function PatientView({
  c,
  meds,
  langMeta,
  rtl,
  busy,
  retranslate,
  downloadPdf,
  refresh,
}) {
  return (
    <div>

      <SafetyBanner />


      <h3>
        Your doctor-approved summary{' '}

        {langMeta
          ? `(${langMeta.native})`
          : ''}
      </h3>


      <p
        className={
          rtl ? 'rtl' : ''
        }
        style={{
          whiteSpace: 'pre-wrap',
        }}
      >
        {c.patient_summary_translated ||
          c.doctor_edited_summary ||
          c.patient_summary_en}
      </p>


      {c.audio_summary_path ? (
        <div>
          <h3>
            Listen to your summary
          </h3>

          <AuthAudio
            url={
              api.audioSummaryUrl(
                c.id
              )
            }
          />
        </div>
      ) : (
        <div className="quality-notice">
          Audio is unavailable for this
          saved summary. The approved text
          remains available.
        </div>
      )}


      <h3>
        Switch language
      </h3>

      <LanguagePicker
        value={
          c.patient_language
        }
        onChange={
          retranslate
        }
        disabled={busy}
        includeNotice={false}
      />


      <h3>
        Your medications
      </h3>


      {!meds.length ? (
        <div className="muted">
          None recorded.
        </div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>
                Medicine
              </th>

              <th>
                Dose
              </th>

              <th>
                How often
              </th>

              <th>
                Timing
              </th>

              <th>
                Duration
              </th>
            </tr>
          </thead>

          <tbody>
            {meds.map(
              (m, i) => (
                <tr key={i}>
                  <td>
                    {m.name ||
                      m.canonical_name}
                  </td>

                  <td>
                    {m.dose ||
                      m.strength ||
                      '—'}
                  </td>

                  <td>
                    {m.frequency ||
                      '—'}
                  </td>

                  <td>
                    {m.food_instruction ||
                      m.timing ||
                      '—'}
                  </td>

                  <td>
                    {m.duration ||
                      '—'}
                  </td>
                </tr>
              )
            )}
          </tbody>
        </table>
      )}


      <h3>
        Medication timetable &
        reminders
      </h3>

      <MedicationSchedulePanel
        consultationId={c.id}
      />


      {c.structured_data
        ?.warning_signs
        ?.length ? (
        <>
          <h3>
            Warning signs your doctor
            discussed
          </h3>

          <ul>
            {c.structured_data
              .warning_signs
              .map(
                (w, i) => (
                  <li key={i}>
                    {w}
                  </li>
                )
              )}
          </ul>
        </>
      ) : null}


      {c.structured_data
        ?.glossary
        ?.length ? (
        <>
          <h3>
            Glossary
          </h3>

          <ul>
            {c.structured_data
              .glossary
              .map(
                (g, i) => (
                  <li key={i}>
                    <strong>
                      {g.term}
                    </strong>
                    :{' '}
                    {
                      g.plain_explanation
                    }
                  </li>
                )
              )}
          </ul>
        </>
      ) : null}


      <button
        onClick={
          downloadPdf
        }
        className="btn-pdf"
        style={{
          marginTop: 18,
        }}
      >
        📄 Download my summary as PDF
      </button>


      {c.released_at ? (
        <PatientCrossCheck
          consultation={c}
          onChange={refresh}
        />
      ) : null}

    </div>
  )
}



function CrossCheckPanel({
  consultation,
}) {
  const [verdict, setVerdict] =
    useState('agree')

  const [comments, setComments] =
    useState('')

  const [done, setDone] =
    useState(false)

  const [err, setErr] =
    useState(null)


  async function submit() {
    try {
      const pending =
        await api.pendingCrossChecks()

      const mine =
        pending.find(
          x =>
            x.consultation_id ===
            consultation.id
        )

      if (!mine) {
        throw new Error(
          'No active review is assigned to you for this case'
        )
      }

      await api.submitCrossCheck(
        mine.id,
        {
          verdict,
          comments,
        }
      )

      setDone(true)

    } catch (e) {
      setErr(e.message)
    }
  }


  if (done) {
    return (
      <div className="success">
        Review submitted.
      </div>
    )
  }


  return (
    <div>

      <h3>
        Assigned cross-check
      </h3>


      <div className="quality-notice">
        You can view this case because it
        was explicitly assigned to you.
        Your review does not overwrite the
        treating doctor's decision.
      </div>


      <h3>
        Source transcript
      </h3>

      <textarea
        readOnly
        value={
          consultation
            .verified_transcript ||
          consultation
            .raw_transcript ||
          ''
        }
        style={{
          minHeight: 160,
        }}
      />


      <h3>
        Doctor-approved patient summary
      </h3>

      <textarea
        readOnly
        value={
          consultation
            .doctor_edited_summary ||
          consultation
            .patient_summary_en ||
          ''
        }
        style={{
          minHeight: 140,
        }}
      />


      <h3>
        AI safety checks
      </h3>

      <SafetyChecks
        consultationId={
          consultation.id
        }
      />


      <label>
        Your verdict
      </label>

      <select
        value={verdict}
        onChange={
          e =>
            setVerdict(
              e.target.value
            )
        }
      >
        <option value="agree">
          Agree
        </option>

        <option value="partially_agree">
          Partially agree
        </option>

        <option value="disagree">
          Disagree
        </option>

        <option value="suggest_followup">
          Suggest follow-up
        </option>

        <option value="flag">
          Flag concern
        </option>
      </select>


      <label>
        Clinical comments
      </label>

      <textarea
        value={comments}
        onChange={
          e =>
            setComments(
              e.target.value
            )
        }
        style={{
          minHeight: 100,
        }}
      />


      {err ? (
        <div className="error">
          {err}
        </div>
      ) : null}


      <button onClick={submit}>
        Submit review
      </button>

    </div>
  )
}