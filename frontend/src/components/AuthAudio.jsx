import { useEffect, useState } from 'react'

/**
 * This component loads protected MediExplain+ audio that cannot be requested
 * directly through a normal <audio> element with an Authorization header.
 * It fetches the audio using the current JWT, converts the response into a
 * temporary in-memory object URL, and releases that URL when the component
 * changes or unmounts so protected audio is not kept unnecessarily in memory.
 */
export default function AuthAudio({ url }) {
  const [src, setSrc] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let objectUrl = null
    const controller = new AbortController()
    const token = localStorage.getItem('mxp_token')

    setSrc(null)
    setError(null)

    fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    })
      .then(r => r.ok ? r.blob() : Promise.reject(new Error(`Audio request failed (${r.status})`)))
      .then(blob => {
        objectUrl = URL.createObjectURL(blob)
        setSrc(objectUrl)
      })
      .catch(err => {
        if (err.name !== 'AbortError') setError(err)
      })

    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [url])

  if (error) return <div className="error">Audio failed: {String(error.message || error)}</div>
  if (!src) return <div className="muted">Loading audio…</div>
  return <audio controls src={src} style={{ width: '100%' }} />
}
