import { useState } from 'react'
import { api } from '../api/client'

/**
 * This component handles patient sharing for a released MediExplain+ consultation.
 * It can request a short-lived signed share link from the backend, optionally build
 * a WhatsApp deep-link for the patient's phone number, copy the generated public
 * link to the clipboard, and download the authenticated patient PDF summary. The
 * shared link can be opened without a patient account and remains valid only for
 * the expiry period returned by the backend.
 */
export default function ShareDialog({ consultationId }) {
  const [phone, setPhone] = useState('')
  const [link, setLink] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [copied, setCopied] = useState(false)

  async function generate() {
    setBusy(true); setErr(null); setCopied(false)
    try {
      const res = await api.createShareLink(consultationId, phone || undefined)
      setLink(res)
    } catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }

  function copyLink() {
    if (!link) return
    navigator.clipboard.writeText(link.share_url)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  async function downloadPdf() {
    try {
      const token = localStorage.getItem('mxp_token')
      const res = await fetch(api.pdfUrl(consultationId), {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) throw new Error(await res.text())
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `care_summary_${consultationId}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) { setErr(String(e)) }
  }

  return (
    <div className="share-box">
      <strong>Share this summary with the patient</strong>
      <div style={{ marginTop: 10 }}>
        <label>Patient phone (optional — for WhatsApp deep-link)</label>
        <input
          type="tel" placeholder="+923001234567"
          value={phone} onChange={e => setPhone(e.target.value)}
        />
      </div>
      <div style={{ marginTop: 10, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button onClick={generate} disabled={busy}>
          {busy ? 'Generating…' : link ? 'Regenerate link' : 'Generate share link'}
        </button>
        <button onClick={downloadPdf} className="btn-pdf">📄 Download PDF</button>
      </div>
      {err && <div className="error">{err}</div>}
      {link && (
        <>
          <code>{link.share_url}</code>
          <div className="share-actions">
            <a href={link.whatsapp_url} target="_blank" rel="noreferrer" className="btn-whatsapp">
              📱 Open WhatsApp
            </a>
            <button className="secondary" onClick={copyLink}>
              {copied ? '✓ Copied' : '📋 Copy link'}
            </button>
          </div>
          <div className="muted" style={{ marginTop: 8 }}>
            Link is valid for {link.expires_in_hours} hours. Patient does not need an account.
          </div>
        </>
      )}
    </div>
  )
}
