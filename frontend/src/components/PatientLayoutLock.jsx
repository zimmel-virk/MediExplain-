import { useEffect } from 'react'
import { useAuth } from '../api/auth'

// This component keeps the main patient interface layout left-to-right for Urdu
// and Shahmukhi Punjabi so navigation, cards and page structure stay consistent,
// while elements explicitly marked as RTL can still display their text in the
// correct right-to-left direction. The original document direction settings are
// restored when the component is removed or the patient's language changes.

const LAYOUT_ONLY_LANGUAGES =
  new Set([
    'ur',
    'pa_shah',
  ])


export default function PatientLayoutLock() {
  const { user } = useAuth()

  useEffect(() => {
    if (
      user?.role !== 'patient'
      || !LAYOUT_ONLY_LANGUAGES.has(
        user?.preferred_language
      )
    ) {
      return undefined
    }

    const html =
      document.documentElement

    const body =
      document.body

    const oldHtmlDir =
      html.getAttribute('dir')

    const oldBodyDir =
      body.getAttribute('dir')

    const oldMarker =
      html.getAttribute(
        'data-mxp-layout-lock'
      )

    const style =
      document.createElement('style')

    style.id =
      'mxp-patient-layout-lock-style'

    style.textContent = `
      html[data-mxp-layout-lock="1"],
      html[data-mxp-layout-lock="1"] body {
        direction: ltr !important;
      }

      html[data-mxp-layout-lock="1"] .topbar,
      html[data-mxp-layout-lock="1"] .brand,
      html[data-mxp-layout-lock="1"] .user-chip,
      html[data-mxp-layout-lock="1"] .nav-strip,
      html[data-mxp-layout-lock="1"] .page,
      html[data-mxp-layout-lock="1"] .hero-panel,
      html[data-mxp-layout-lock="1"] .hero-actions,
      html[data-mxp-layout-lock="1"] .stat-grid,
      html[data-mxp-layout-lock="1"] .section-head,
      html[data-mxp-layout-lock="1"] .table-wrap,
      html[data-mxp-layout-lock="1"] .schedule-grid,
      html[data-mxp-layout-lock="1"] .schedule-card,
      html[data-mxp-layout-lock="1"] .detail-grid {
        direction: ltr !important;
      }

      html[data-mxp-layout-lock="1"] .rtl {
        direction: rtl !important;
        text-align: right;
        unicode-bidi: plaintext;
      }
    `

    html.setAttribute(
      'data-mxp-layout-lock',
      '1'
    )

    html.setAttribute(
      'dir',
      'ltr'
    )

    body.setAttribute(
      'dir',
      'ltr'
    )

    document.head.appendChild(
      style
    )

    return () => {
      style.remove()

      if (oldHtmlDir === null) {
        html.removeAttribute('dir')
      } else {
        html.setAttribute(
          'dir',
          oldHtmlDir
        )
      }

      if (oldBodyDir === null) {
        body.removeAttribute('dir')
      } else {
        body.setAttribute(
          'dir',
          oldBodyDir
        )
      }

      if (oldMarker === null) {
        html.removeAttribute(
          'data-mxp-layout-lock'
        )
      } else {
        html.setAttribute(
          'data-mxp-layout-lock',
          oldMarker
        )
      }
    }
  }, [
    user?.role,
    user?.preferred_language,
  ])

  return null
}
