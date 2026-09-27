import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useAuth } from '../api/auth'


/**
 * This file provides the MediExplain+ Support & Safety Centre for signed-in users.
 * It lets users report suspected data breaches, technical problems, general help
 * requests and privacy or data-rights concerns, while clearly separating software
 * support from urgent medical care. The page builds the appropriate support form,
 * applies suitable urgency defaults, allows more specific privacy-request types,
 * submits the report to the backend support system, and shows the user's recent
 * support tickets and their current status. It also includes privacy and security
 * guidance so users avoid sharing unnecessary sensitive information and understand
 * that requests such as deletion or restriction are reviewed rather than applied
 * automatically.
 */

const options = [
  {
    key: 'data_breach',
    icon: '!',
    title: 'Report a data breach',
    desc: 'Use this if you suspect patient information, credentials, audio or consultation data was exposed.',
    urgency: 'critical',
  },
  {
    key: 'technical_problem',
    icon: '⚙',
    title: 'Report a technical problem',
    desc: 'Tell us about errors, broken pages, audio issues, reminders or unexpected system behaviour.',
    urgency: 'normal',
  },
  {
    key: 'help_request',
    icon: '?',
    title: 'Get help',
    desc: 'Ask for help using your dashboard, patient portal, assistant review or reminder features.',
    urgency: 'normal',
  },
  {
    key: 'contact',
    icon: '✉',
    title: 'Contact us',
    desc: 'Send a general, privacy or data-rights request to the MediExplain+ project support team.',
    urgency: 'normal',
  },
]

const privacyRequests = [
  {
    value: 'general_support',
    label: 'General support / not a privacy request',
  },
  {
    value: 'access_copy',
    label: 'Access a copy of my information',
  },
  {
    value: 'amend_information',
    label: 'Correct or amend my information',
  },
  {
    value: 'restrict_use_disclosure',
    label: 'Request restriction on use or disclosure',
  },
  {
    value: 'confidential_communication',
    label: 'Request confidential communication',
  },
  {
    value: 'accounting_disclosures',
    label: 'Request an accounting of disclosures',
  },
  {
    value: 'withdraw_consent',
    label: 'Revoke an authorization / withdraw optional consent',
  },
  {
    value: 'delete_data',
    label: 'Request deletion or erasure where legally permitted',
  },
  {
    value: 'privacy_complaint',
    label: 'Report a privacy concern or complaint',
  },
  {
    value: 'security_incident',
    label: 'Report a security incident or suspected data breach',
  },
  {
    value: 'other_privacy_request',
    label: 'Other privacy or data request',
  },
]

function privacyLabel(value) {
  return (
    privacyRequests.find(
      item => item.value === value
    )?.label || '—'
  )
}

export default function SupportSafety() {
  const { user } = useAuth()

  const emptyForm = {
    subject: '',
    message: '',
    contact_email: user.email,
    urgency: 'normal',
    privacy_request_type: '',
  }

  const [type, setType] = useState('')
  const [form, setForm] = useState(emptyForm)
  const [done, setDone] = useState(null)
  const [err, setErr] = useState(null)
  const [tickets, setTickets] = useState([])

  useEffect(() => {
    api.mySupportTickets()
      .then(setTickets)
      .catch(() => {})
  }, [])

  function choose(option) {
    setType(option.key)

    setForm({
      ...emptyForm,
      subject: option.title,
      urgency: option.urgency,
    })

    setDone(null)
    setErr(null)

    setTimeout(
      () =>
        document
          .getElementById('ticket-form')
          ?.scrollIntoView({
            behavior: 'smooth',
          }),
      50
    )
  }

  async function submit(event) {
    event.preventDefault()
    setErr(null)

    try {
      const payload = {
        ...form,
        category: type,
        privacy_request_type:
          type === 'contact' &&
          form.privacy_request_type
            ? form.privacy_request_type
            : null,
      }

      const ticket =
        await api.createSupportTicket(
          payload
        )

      setDone(ticket)

      setTickets([
        ticket,
        ...tickets,
      ])

      setType('')
      setForm(emptyForm)
    } catch (error) {
      setErr(error.message)
    }
  }

  return (
    <main className="page">
      <section className="hero-panel compact-hero">
        <div>
          <span className="eyebrow">
            SUPPORT · PRIVACY · SAFETY
          </span>

          <h1>
            Support & Safety Centre
          </h1>

          <p>
            Report a privacy concern,
            get help, flag a problem or
            contact the project team from
            one place.
          </p>
        </div>
      </section>

      <div className="critical-banner">
        <strong>
          Urgent medical issue?
        </strong>

        <span>
          This page is for software and
          support issues, not emergency
          medical care. Contact your local
          emergency service or healthcare
          provider for urgent clinical help.
        </span>
      </div>

      <section className="support-grid">
        {options.map(option => (
          <button
            className="support-card"
            key={option.key}
            onClick={() => choose(option)}
          >
            <span className="support-icon">
              {option.icon}
            </span>

            <strong>
              {option.title}
            </strong>

            <span>
              {option.desc}
            </span>

            <em>
              Open form →
            </em>
          </button>
        ))}
      </section>

      {done && (
        <div className="success panel">
          <strong>
            Report #{done.id} received.
          </strong>{' '}

          It has been recorded with
          status “{done.status}”.
        </div>
      )}

      {type && (
        <section
          className="card"
          id="ticket-form"
        >
          <span className="eyebrow">
            SECURE SUPPORT FORM
          </span>

          <h2>
            {
              options.find(
                item =>
                  item.key === type
              )?.title
            }
          </h2>

          {type === 'data_breach' && (
            <div className="warning-panel">
              <strong>
                For a suspected data breach
              </strong>

              <span>
                Do not paste passwords,
                authentication codes or
                unnecessary patient details.
                Describe what happened, what
                data may be affected and when
                you noticed it.
              </span>
            </div>
          )}

          {type === 'contact' && (
            <div className="learning-note">
              <strong>
                Privacy & data requests
              </strong>

              <span>
                These options route your
                request for review. Selecting
                one does not automatically
                change or delete a clinical
                record. Legal, safety and
                retention requirements may
                still apply.
              </span>
            </div>
          )}

          <form onSubmit={submit}>
            {type === 'contact' && (
              <>
                <label>
                  Privacy & data request
                </label>

                <select
                  value={
                    form
                      .privacy_request_type
                  }
                  onChange={event =>
                    setForm({
                      ...form,
                      privacy_request_type:
                        event.target.value,
                    })
                  }
                >
                  <option value="">
                    Select a request type
                  </option>

                  {privacyRequests.map(
                    item => (
                      <option
                        key={item.value}
                        value={item.value}
                      >
                        {item.label}
                      </option>
                    )
                  )}
                </select>

                <p className="field-note">
                  The prototype is
                  GDPR-informed and
                  HIPAA-aligned; it does not
                  claim legal compliance or
                  guarantee deletion where
                  records must lawfully be
                  retained.
                </p>
              </>
            )}

            <label>
              Subject
            </label>

            <input
              required
              value={form.subject}
              onChange={event =>
                setForm({
                  ...form,
                  subject:
                    event.target.value,
                })
              }
            />

            <label>
              Reply email
            </label>

            <input
              required
              type="email"
              value={form.contact_email}
              onChange={event =>
                setForm({
                  ...form,
                  contact_email:
                    event.target.value,
                })
              }
            />

            <label>
              Details
            </label>

            <textarea
              required
              minLength={10}
              className="tall"
              value={form.message}
              onChange={event =>
                setForm({
                  ...form,
                  message:
                    event.target.value,
                })
              }
              placeholder="Describe the request clearly without including more personal data than necessary."
            />

            <label>
              Priority
            </label>

            <select
              value={form.urgency}
              onChange={event =>
                setForm({
                  ...form,
                  urgency:
                    event.target.value,
                })
              }
            >
              <option value="normal">
                Normal
              </option>

              <option value="high">
                High
              </option>

              {type ===
                'data_breach' && (
                <option value="critical">
                  Critical privacy/security
                  concern
                </option>
              )}
            </select>

            {err && (
              <div className="error">
                {err}
              </div>
            )}

            <div className="action-line">
              <button>
                Submit report
              </button>

              <button
                type="button"
                className="ghost"
                onClick={() =>
                  setType('')
                }
              >
                Cancel
              </button>
            </div>
          </form>
        </section>
      )}

      {!!tickets.length && (
        <section className="card">
          <h2>
            My recent support reports
          </h2>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Type</th>
                  <th>
                    Privacy request
                  </th>
                  <th>Subject</th>
                  <th>Status</th>
                  <th>Created</th>
                </tr>
              </thead>

              <tbody>
                {tickets
                  .slice(0, 8)
                  .map(ticket => (
                    <tr key={ticket.id}>
                      <td>
                        #{ticket.id}
                      </td>

                      <td>
                        {ticket.category
                          .replaceAll(
                            '_',
                            ' '
                          )}
                      </td>

                      <td>
                        {privacyLabel(
                          ticket
                            .privacy_request_type
                        )}
                      </td>

                      <td>
                        {ticket.subject}
                      </td>

                      <td>
                        <span className="pill">
                          {ticket.status}
                        </span>
                      </td>

                      <td>
                        {new Date(
                          ticket.created_at
                        ).toLocaleString()}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </main>
  )
}
