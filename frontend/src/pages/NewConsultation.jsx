import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import Recorder from '../components/Recorder'
import LanguagePicker from '../components/LanguagePicker'

/**
 * This file provides the doctor workflow for creating a new MediExplain+
 * consultation. It loads available patients and supported languages, lets the
 * doctor choose the patient, define the main and optional secondary spoken
 * languages for transcription and code-switching, select the patient's preferred
 * output language, and confirm both doctor and patient consent before a consultation
 * can be created. Once the consultation exists, it uses the browser recorder to
 * capture the consultation audio, uploads the completed recording to the backend,
 * and then opens the consultation page while the transcription and AI processing
 * pipeline continues in the background.
 */
export default function NewConsultation() {
  const nav = useNavigate()
  const [patients, setPatients] = useState([])
  const [langs, setLangs] = useState([])
  const [patientId, setPatientId] = useState('')
  const [outputLang, setOutputLang] = useState('en')
  const [sttPrimary, setSttPrimary] = useState('')      // '' = auto-detect
  const [sttSecondary, setSttSecondary] = useState('')  // optional
  const [docConsent, setDocConsent] = useState(false)
  const [patConsent, setPatConsent] = useState(false)
  const [consultation, setConsultation] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [err, setErr] = useState(null)

  useEffect(() => {
    api.listPatients().then(setPatients).catch(e => setErr(e.message))
    api.languages().then(setLangs).catch(() => {})
  }, [])

  // When a patient is picked, default the output language to their preference
  useEffect(() => {
    if (!patientId) return
    const p = patients.find(x => String(x.id) === String(patientId))
    if (p?.preferred_language) setOutputLang(p.preferred_language)
  }, [patientId, patients])

  async function start() {
    setErr(null)
    if (!patientId) return setErr('Select a patient')
    if (!docConsent || !patConsent) return setErr('Both consents are required')
    try {
      const c = await api.createConsultation({
        patient_id: Number(patientId),
        doctor_consent: true,
        patient_consent: true,
        patient_language: outputLang,
        stt_primary_language: sttPrimary || null,
        stt_secondary_language: sttSecondary || null,
      })
      setConsultation(c)
    } catch (e) { setErr(e.message) }
  }

  async function onAudio(blob) {
    setUploading(true)
    setErr(null)
    try {
      const file = new File([blob], 'consultation.webm', { type: 'audio/webm' })
      await api.uploadAudio(consultation.id, file)
      nav('/consultation/' + consultation.id)
    } catch (e) {
      setErr(e.message)
      setUploading(false)
    }
  }

  return (
    <div className="container">
      <div className="card">
        <h2>Start a new consultation</h2>

        {!consultation ? (
          <div>
            <label>Patient</label>
            <select value={patientId} onChange={e => setPatientId(e.target.value)}>
              <option value="">— Select patient —</option>
              {patients.map(p => (
                <option key={p.id} value={p.id}>
                  {p.full_name} ({p.email}) — prefers {(p.preferred_language || 'en').toUpperCase()}
                </option>
              ))}
            </select>

            <h3>Spoken language during the consultation</h3>
            <p className="muted">
              Helps the AI transcribe accurately. Leave blank for auto-detect.
              For code-switched consultations (e.g. English mixed with Urdu),
              set both primary and secondary.
            </p>

            <label>Primary spoken language</label>
            <select value={sttPrimary} onChange={e => setSttPrimary(e.target.value)}>
              <option value="">— Auto-detect —</option>
              {langs.map(l => (
                <option key={l.code} value={l.code}>{l.name} ({l.native})</option>
              ))}
            </select>

            <label>Secondary spoken language (optional, for code-switching)</label>
            <select value={sttSecondary} onChange={e => setSttSecondary(e.target.value)}>
              <option value="">— None —</option>
              {langs.filter(l => l.code !== sttPrimary).map(l => (
                <option key={l.code} value={l.code}>{l.name} ({l.native})</option>
              ))}
            </select>

            <h3>Patient's preferred language for the written/audio summary</h3>
            <LanguagePicker value={outputLang} onChange={setOutputLang} />

            <h3>Consent</h3>
            <p className="muted">
              Recording cannot start until both parties consent. Consent can be
              withdrawn later and the recording deleted.
            </p>
            <label>
              <input type="checkbox" checked={docConsent}
                     onChange={e => setDocConsent(e.target.checked)} />
              {' '}I (the doctor) consent to recording for documentation and prototype use.
            </label>
            <label>
              <input type="checkbox" checked={patConsent}
                     onChange={e => setPatConsent(e.target.checked)} />
              {' '}The patient has given informed verbal consent to record this consultation.
            </label>

            {err ? <div className="error">{err}</div> : null}
            <div style={{ marginTop: 18 }}>
              <button onClick={start}>Create consultation</button>
            </div>
          </div>
        ) : (
          <div>
            <h3>Consultation #{consultation.id} ready</h3>
            <p className="muted">
              Record the consultation. When you stop, the audio uploads and the
              AI pipeline runs in the background.
            </p>
            <Recorder onComplete={onAudio} disabled={uploading} />
            {uploading ? <div className="muted">Uploading…</div> : null}
            {err ? <div className="error">{err}</div> : null}
          </div>
        )}
      </div>
    </div>
  )
}
