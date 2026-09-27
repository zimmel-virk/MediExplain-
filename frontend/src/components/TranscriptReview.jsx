import { useEffect, useState } from 'react'
import { api } from '../api/client'

/**
 * This component provides the clinician transcript-review interface for a
 * MediExplain+ consultation. It loads the stored speech-to-text segments, shows
 * timestamps, detected language, speaker labels and STT confidence, and highlights
 * segments that require manual review. Clinicians can correct the recognised text,
 * update the speaker label, or explicitly confirm that low-confidence transcription
 * is accurate. The reviewed version is saved separately while the original raw STT
 * text remains preserved, allowing downstream summaries and safety checks to use
 * clinician-reviewed transcript content without losing the original recognition output.
 */

export default function TranscriptReview({
  consultationId,
  readOnly = false,
  onChanged,
}) {
  const [segments, setSegments] = useState([])
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(null)

  async function load() {
    try {
      setSegments(
        await api.transcriptSegments(
          consultationId
        )
      )
    } catch (e) {
      setErr(e.message)
    }
  }

  useEffect(() => {
    load()
  }, [consultationId])

  async function save(
    seg,
    text,
    speaker
  ) {
    setBusy(seg.id)
    setErr(null)

    try {
      const updated =
        await api.updateTranscriptSegment(
          consultationId,
          seg.id,
          {
            // Sending the text even when unchanged is deliberate.
            // It records explicit clinician acceptance of the
            // low-confidence speech.
            text_reviewed: text,
            speaker_label: speaker,
            needs_review: false,
          }
        )

      setSegments(
        xs => xs.map(
          x =>
            x.id === seg.id
              ? updated
              : x
        )
      )

      await onChanged?.()
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(null)
    }
  }

  if (err) {
    return (
      <div className="error">
        {err}
      </div>
    )
  }

  if (!segments.length) {
    return (
      <div className="muted">
        Segment-level transcript is not available
        for this older consultation.
      </div>
    )
  }

  return (
    <div>
      <div
        className="muted"
        style={{ marginBottom: 8 }}
      >
        Low-confidence speech is highlighted.
        Listen to each highlighted segment and either
        correct it or explicitly confirm that the
        transcription is accurate. Raw STT text is
        always preserved.
      </div>

      {segments.map(seg => (
        <Segment
          key={seg.id}
          seg={seg}
          readOnly={readOnly}
          busy={busy === seg.id}
          onSave={save}
        />
      ))}
    </div>
  )
}


function Segment({
  seg,
  readOnly,
  busy,
  onSave,
}) {
  const [text, setText] = useState(
    seg.text_reviewed
    ?? seg.text_raw
  )

  const [speaker, setSpeaker] = useState(
    seg.speaker_label
    ?? ''
  )

  const low = seg.needs_review

  const textChanged =
    text !== (
      seg.text_reviewed
      ?? seg.text_raw
    )

  const speakerChanged =
    speaker !== (
      seg.speaker_label
      ?? ''
    )

  const changed =
    textChanged
    || speakerChanged

  return (
    <div
      className={
        low
          ? 'quality-warning'
          : 'quality-notice'
      }
      style={{
        marginBottom: 8,
        background:
          low
            ? undefined
            : 'transparent',
      }}
    >
      <div
        style={{
          display: 'flex',
          gap: 10,
          alignItems: 'center',
          flexWrap: 'wrap',
        }}
      >
        <strong>
          {seg.start_seconds.toFixed(1)}
          –
          {seg.end_seconds.toFixed(1)}s
        </strong>

        {seg.language ? (
          <span className="badge">
            {seg.language.toUpperCase()}
          </span>
        ) : null}

        {seg.confidence != null ? (
          <span className="muted">
            STT confidence{' '}
            {Math.round(
              seg.confidence * 100
            )}%
          </span>
        ) : null}

        {low ? (
          <strong>
            ⚠ Clinician review required
          </strong>
        ) : null}

        {!low && seg.text_reviewed ? (
          <span className="conf-badge approved">
            Reviewed
          </span>
        ) : null}
      </div>


      <div
        className="row"
        style={{ marginTop: 6 }}
      >
        <input
          value={speaker}
          onChange={
            e =>
              setSpeaker(
                e.target.value
              )
          }
          disabled={readOnly}
          placeholder="Speaker (Doctor / Patient)"
        />

        <input
          value={text}
          onChange={
            e =>
              setText(
                e.target.value
              )
          }
          disabled={readOnly}
        />
      </div>


      {!readOnly
       && (
         low
         || changed
       ) ? (
        <button
          className="secondary"
          disabled={
            busy
            || !text.trim()
          }
          onClick={
            () =>
              onSave(
                seg,
                text,
                speaker
              )
          }
          style={{ marginTop: 8 }}
        >
          {busy
            ? 'Saving…'
            : low && !textChanged
              ? 'I listened and confirm this transcript is accurate'
              : low
                ? 'Save correction and mark reviewed'
                : 'Save reviewed segment'}
        </button>
      ) : null}
    </div>
  )
}
