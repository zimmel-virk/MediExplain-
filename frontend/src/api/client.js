// This file is the central API client used by the MediExplain+ frontend. It keeps
// backend requests in one place, manages the locally stored access token, attaches
// JWT authentication to protected requests, prepares JSON or multipart payloads,
// and converts unsuccessful HTTP responses into errors that the interface can
// handle consistently. The exported API object then provides named methods for
// the application's authentication, consultation, safety, medication, scheduling,
// cross-check, assistant-review, support, learning and patient-sharing workflows.

const BASE = '/api'

function getToken() { return localStorage.getItem('mxp_token') }
export function setToken(t) { localStorage.setItem('mxp_token', t) }
export function clearToken() { localStorage.removeItem('mxp_token') }

async function request(method, path, { body, formData, query } = {}) {
  const url = new URL(BASE + path, window.location.origin)
  if (query) Object.entries(query).forEach(([k, v]) => v != null && url.searchParams.set(k, v))

    // Authentication tokens are stored under one frontend key so login, session
// restoration and logout all use the same credential source.
  const headers = {}
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`

  // Shared request handling builds the API URL, adds optional query parameters and
// the current Bearer token, chooses JSON or FormData encoding, and returns either
// decoded JSON or binary content. Non-success responses are raised as errors so
// individual page components do not need to repeat this handling.
  let payload
  if (formData) {
    payload = formData
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }

  const res = await fetch(url, { method, headers, body: payload })
  if (res.status === 204) return null
  const isJson = res.headers.get('content-type')?.includes('application/json')
  const data = isJson ? await res.json() : await res.blob()
  if (!res.ok) {
    const msg = (data && data.detail) || res.statusText
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return data
}

export const api = {
  // auth
  async register(payload) { return request('POST', '/auth/register', { body: payload }) },
  async login(email, password) {
    const fd = new FormData()
    fd.set('username', email)
    fd.set('password', password)
    return request('POST', '/auth/login', { formData: fd })
  },
  async verifyMfaSetup(mfa_token, code) {
    return request('POST', '/auth/mfa/setup/verify', {
      body: { mfa_token, code },
    })
  },
  async verifyMfa(mfa_token, code) {
    return request('POST', '/auth/mfa/verify', {
      body: { mfa_token, code },
    })
  },
  async me() { return request('GET', '/users/me') },

  // languages
  async languages() { return request('GET', '/languages') },

  // users
  async listPatients() { return request('GET', '/users/patients') },
  async listDoctors() { return request('GET', '/users/doctors') },
  async listAssistants() { return request('GET', '/users/assistants') },

  // consultations
  async createConsultation(body) { return request('POST', '/consultations/', { body }) },
  async uploadAudio(id, file) {
    const fd = new FormData()
    fd.set('file', file, file.name || 'rec.webm')
    return request('POST', `/consultations/${id}/audio`, { formData: fd })
  },
  async uploadPrescription(id, file) {
    const fd = new FormData()
    fd.set('file', file, file.name || 'rx.png')
    return request('POST', `/consultations/${id}/prescription`, { formData: fd })
  },
  async getConsultation(id) { return request('GET', `/consultations/${id}`) },
  async listConsultations(status) { return request('GET', '/consultations/', { query: { status } }) },
  async approve(id, body) { return request('POST', `/consultations/${id}/approve`, { body }) },
  async release(id) { return request('POST', `/consultations/${id}/release`) },
  async retranslate(id, target_lang) {
    return request('POST', `/consultations/${id}/translate`, { query: { target_lang } })
  },
  async deleteConsultation(id) { return request('DELETE', `/consultations/${id}`) },
  async createShareLink(id, phone) {
    return request('POST', `/consultations/${id}/share`, { query: { phone } })
  },
  async sendWhatsAppPdf(id, phone) {
    return request('POST', `/consultations/${id}/whatsapp-pdf`, { query: { phone } })
  },
  audioSummaryUrl(id) {
    return `/api/consultations/${id}/audio-summary`
  },
  pdfUrl(id) {
    return `/api/consultations/${id}/pdf`
  },

  // cross-check
  async requestCrossCheck(body) { return request('POST', '/cross-check/request', { body }) },
  async submitCrossCheck(id, body) { return request('POST', `/cross-check/${id}/submit`, { body }) },
  async pendingCrossChecks() { return request('GET', '/cross-check/pending') },
  async crossChecksForConsultation(cid) {
    return request('GET', `/cross-check/for-consultation/${cid}`)
  },

  // medications
  async suggestMedications(query, top_k = 5) {
    return request('GET', '/medications/suggest', { query: { q: query, top_k } })
  },
  async listAllMedications() { return request('GET', '/medications/all') },
  async updateMedication(cid, idx, body) {
    return request('POST', `/consultations/${cid}/medications/${idx}`, { body })
  },
  async removeMedication(cid, idx) {
    return request('DELETE', `/consultations/${cid}/medications/${idx}`)
  },
  async addMedication(cid, body) {
    return request('POST', `/consultations/${cid}/medications`, { body })
  },

  // transcript / safety
  async transcriptSegments(id) { return request('GET', `/consultations/${id}/transcript-segments`) },
  async updateTranscriptSegment(cid, sid, body) {
    return request('PATCH', `/consultations/${cid}/transcript-segments/${sid}`, { body })
  },
  async regenerateReviewedTranscript(id) {
  return request(
    'POST',
    `/consultations/${id}/regenerate-reviewed`
  )
},
  async safetyChecks(id) { return request('GET', `/consultations/${id}/safety`) },
  async resolveSafety(
    cid,
    checkId,
    {
      confirmTranslation = false,
      confirmGrounding = false,
    } = {}
  ) {
    const params = new URLSearchParams()

    if (confirmTranslation) {
      params.set(
        'confirm_translation',
        'true'
      )
    }

    if (confirmGrounding) {
      params.set(
        'confirm_grounding',
        'true'
      )
    }

    const suffix =
      params.toString()
        ? `?${params.toString()}`
        : ''

    return request(
      'POST',
      `/consultations/${cid}/safety/${checkId}/resolve${suffix}`
    )
  },
  async correctPrescriptionOcr(cid, text) {
    return request('PATCH', `/consultations/${cid}/prescription/ocr`, { body: { text } })
  },
  async generateSchedules(cid) { return request('POST', `/schedules/consultation/${cid}/generate`) },
  async schedulesForConsultation(cid) { return request('GET', `/schedules/consultation/${cid}`) },
  async mySchedules() { return request('GET', '/schedules/mine') },
  async medicationEventAction(eventId, action, snooze_minutes = 15) {
    return request('POST', `/schedules/events/${eventId}/action`, { body: { action, snooze_minutes } })
  },
  medicationEventAudioUrl(eventId) { return `/api/schedules/events/${eventId}/audio` },


  // delegated assistant pre-review (additive to original doctor release flow)
  async assignAssistant(body) { return request('POST', '/assistant-reviews/assign', { body }) },
  async pendingAssistantReviews() { return request('GET', '/assistant-reviews/pending') },
  async assistantReview(id) { return request('GET', `/assistant-reviews/${id}`) },
  async assistantReviewCase(id) { return request('GET', `/assistant-reviews/${id}/case`) },
  async submitAssistantReview(id, body) { return request('POST', `/assistant-reviews/${id}/submit`, { body }) },
  async latestAssistantReview(cid) { return request('GET', `/assistant-reviews/consultation/${cid}/latest`) },

  // support + patient learning centre
  async createSupportTicket(body) { return request('POST', '/support/tickets', { body }) },
  async mySupportTickets() { return request('GET', '/support/mine') },
  async learning(lang) { return request('GET', '/learning', { query: { lang } }) },

  // public share (no auth needed)
  async getSharedView(token) {
    const r = await fetch(`/api/share/${token}`)
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText)
    return r.json()
  },
  sharedAudioUrl(token) { return `/api/share/${token}/audio` },
  sharedPdfUrl(token) { return `/api/share/${token}/pdf` },
}
