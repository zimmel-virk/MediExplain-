import { useState } from 'react'
import { api } from '../api/client'

/**
 * This component manages WhatsApp delivery for a released MediExplain+ patient
 * summary. It lets the clinician confirm or edit the patient's WhatsApp number,
 * preview the generated PDF, send the final doctor-released PDF through the
 * backend WhatsApp delivery service, or open a signed WhatsApp share link for
 * manual sending. Delivery actions remain disabled until the consultation has
 * been formally released, and the interface reports either the returned delivery
 * confirmation or any error from the sharing process.
 */

export default function WhatsAppDelivery({ consultation, downloadPdf }) {
  const [phone, setPhone] = useState(consultation.patient_phone || '')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  const released = Boolean(consultation.released_at)

  async function sendPdf() {
    setBusy(true)
    setNotice('')
    setError('')

    try {
      if (!released) {
        throw new Error('Release the consultation before sending the patient PDF.')
      }

      const result = await api.sendWhatsAppPdf(
        consultation.id,
        phone.trim() || undefined
      )

      setNotice(
        result?.message_id
          ? `PDF sent successfully on WhatsApp · ${result.message_id}`
          : 'PDF sent successfully on WhatsApp.'
      )
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function openWhatsApp() {
    setBusy(true)
    setNotice('')
    setError('')

    try {
      if (!released) {
        throw new Error('Release the consultation before sharing it.')
      }

      const result = await api.createShareLink(
        consultation.id,
        phone.trim() || undefined
      )

      if (!result?.whatsapp_url) {
        throw new Error('Could not create WhatsApp link.')
      }

      window.open(result.whatsapp_url, '_blank', 'noopener,noreferrer')
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card" style={{ marginTop: 18 }}>
      <div className="section-head">
        <div>
          <span className="eyebrow">PATIENT DELIVERY</span>
          <h2>Send summary on WhatsApp</h2>
          <p>
            Send the final doctor-released patient summary PDF directly
            to the patient's WhatsApp number.
          </p>
        </div>

        <button
          type="button"
          className="secondary"
          onClick={downloadPdf}
        >
          Preview PDF
        </button>
      </div>

      {!released && (
        <div className="quality-notice">
          The summary can be previewed now. WhatsApp delivery becomes
          available only after final doctor release.
        </div>
      )}

      <div className="whatsapp-row">
        <label>
          Patient WhatsApp number
          <input
            value={phone}
            onChange={e => setPhone(e.target.value)}
            placeholder="+923001234567"
          />
        </label>

        <button
          type="button"
          disabled={busy || !released || !phone.trim()}
          onClick={sendPdf}
        >
          {busy ? 'Sending…' : 'Send PDF on WhatsApp'}
        </button>

        <button
          type="button"
          className="secondary"
          disabled={busy || !released || !phone.trim()}
          onClick={openWhatsApp}
        >
          Open WhatsApp
        </button>
      </div>

      {notice && <div className="success panel">{notice}</div>}
      {error && <div className="error panel">{error}</div>}
    </section>
  )
}
