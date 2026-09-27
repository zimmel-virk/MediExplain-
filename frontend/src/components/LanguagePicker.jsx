import { useEffect, useState } from 'react'
import { api } from '../api/client'

// This component loads the languages supported by MediExplain+, presents them in
// a reusable selector, and shows whether each language supports both text and
// audio. When a language is still marked as evaluation pending, it also displays
// the patient-safety reminder that translated medical instructions must be
// verified by the doctor before release.

export default function LanguagePicker({ value, onChange, disabled, includeNotice = true }) {
  const [langs, setLangs] = useState([])

  useEffect(() => {
    api.languages().then(setLangs).catch(() => setLangs([]))
  }, [])

  const current = langs.find(l => l.code === value)

  return (
    <>
      <select value={value} onChange={e => onChange(e.target.value)} disabled={disabled}>
        {langs.map(l => (
          <option key={l.code} value={l.code}>
            {l.name} ({l.native}) — {l.has_tts ? 'audio + text' : 'text only'}
          </option>
        ))}
      </select>

      {includeNotice && current && current.quality === 'evaluation_pending' && (
        <div className="quality-notice">
          <strong>{current.name}: final evaluation pending.</strong>{' '}
          The doctor must verify translated medical instructions before release.
        </div>
      )}
    </>
  )
}

export function langDirection(langs, code) {
  const l = langs.find(x => x.code === code)
  return l?.rtl ? 'rtl' : 'ltr'
}
