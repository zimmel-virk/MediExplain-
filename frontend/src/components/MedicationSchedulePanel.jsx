import {
  useEffect,
  useState,
} from 'react'

import { api } from '../api/client'

// This panel shows the medication timetable created from the consultation's
// doctor-approved instructions. It loads the saved schedules and reminder events,
// displays the medication details and upcoming alert times, and lets the patient
// record reminder actions such as taken, snoozed or skipped. These actions update
// the existing backend schedule rather than creating or changing medication advice.

export default function MedicationSchedulePanel({
  consultationId,
}) {
  const [items, setItems] =
    useState([])

  const [err, setErr] =
    useState(null)

  const [busy, setBusy] =
    useState(null)

  // Load the medication schedules and reminder events already stored for this
  // consultation so the panel reflects the current backend state.

  async function load() {
    try {
      setErr(null)

      const data =
        await api.schedulesForConsultation(
          consultationId
        )

      setItems(data)

    } catch (e) {
      setErr(e.message)
    }
  }


  useEffect(() => {
    load()
  }, [consultationId])

    // Record the patient's response to a reminder event. Snooze uses the fixed
  // ten-minute delay provided by this interface, while taken and skipped are
  // submitted directly before the schedule is refreshed.


  async function action(
    id,
    act
  ) {
    setBusy(
      `${id}-${act}`
    )

    setErr(null)

    try {
      if (act === 'snooze') {
        await api.medicationEventAction(
          id,
          act,
          10
        )

      } else {
        await api.medicationEventAction(
          id,
          act
        )
      }

      await load()

    } catch (e) {
      setErr(e.message)

    } finally {
      setBusy(null)
    }
  }


  function formatDate(
    value
  ) {
    if (!value) {
      return '—'
    }

    return new Date(
      value
    ).toLocaleDateString(
      undefined,
      {
        weekday: 'short',
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      }
    )
  }


  function formatTime(
    value
  ) {
    if (!value) {
      return '—'
    }

    return new Date(
      value
    ).toLocaleTimeString(
      undefined,
      {
        hour: 'numeric',
        minute: '2-digit',
      }
    )
  }

  // Convert the stored reminder-event status into the short label shown in the
  // medication timetable.
  
  function statusText(
    status
  ) {
    if (
      status === 'taken'
    ) {
      return '✓ Taken'
    }

    if (
      status === 'snoozed'
    ) {
      return '⏰ Snoozed'
    }

    if (
      status === 'skipped'
    ) {
      return 'Skipped'
    }

    return 'Pending'
  }


  if (err) {
    return (
      <div className="error">
        {err}
      </div>
    )
  }


  if (!items.length) {
    return (
      <div className="muted">
        No automatic medication
        timetable was created.
      </div>
    )
  }


  return (
    <div>
      <div
        className="quality-notice"
        style={{
          marginBottom: 12,
        }}
      >
        <strong>
          Medication reminder schedule
        </strong>

        <div
          style={{
            marginTop: 4,
          }}
        >
          The alarm system uses the exact
          doctor-approved medication
          instructions shown below.
        </div>
      </div>


      {items.map(
        schedule => (
          <div
            key={schedule.id}
            className="card"
            style={{
              marginTop: 14,
              padding: 16,
            }}
          >
            <h3
              style={{
                marginTop: 0,
                marginBottom: 12,
              }}
            >
              💊 {
                schedule.medication_name
              }
            </h3>


            <div
              style={{
                display: 'grid',
                gridTemplateColumns:
                  'repeat(auto-fit, minmax(180px, 1fr))',
                gap: 10,
                marginBottom: 14,
              }}
            >
              <div>
                <strong>
                  Medicine
                </strong>

                <div>
                  {
                    schedule.medication_name
                  }
                </div>
              </div>


              <div>
                <strong>
                  Dose / quantity
                </strong>

                <div>
                  {
                    schedule.dose ||
                    '—'
                  }
                </div>
              </div>


              <div>
                <strong>
                  Dosage form
                </strong>

                <div>
                  {
                    schedule
                      .dosage_form ||
                    '—'
                  }
                </div>
              </div>


              <div>
                <strong>
                  Frequency
                </strong>

                <div>
                  {
                    schedule.frequency ||
                    '—'
                  }
                </div>
              </div>


              <div>
                <strong>
                  Timing
                </strong>

                <div>
                  {
                    schedule.timing ||
                    '—'
                  }
                </div>
              </div>


              <div>
                <strong>
                  Food instruction
                </strong>

                <div>
                  {
                    schedule
                      .food_instruction ||
                    '—'
                  }
                </div>
              </div>


              <div>
                <strong>
                  Duration
                </strong>

                <div>
                  {
                    schedule.duration ||
                    '—'
                  }
                </div>
              </div>


              <div>
                <strong>
                  Start date
                </strong>

                <div>
                  {
                    schedule.start_date ||
                    '—'
                  }
                </div>
              </div>


              <div>
                <strong>
                  End date
                </strong>

                <div>
                  {
                    schedule.end_date ||
                    '—'
                  }
                </div>
              </div>
            </div>


            {schedule.instructions ? (
              <div
                className="muted"
                style={{
                  marginBottom: 14,
                }}
              >
                <strong>
                  Doctor-approved
                  instructions:
                </strong>{' '}
                {
                  schedule.instructions
                }
              </div>
            ) : null}


            <h4>
              Reminder dates and times
            </h4>


            <div
              style={{
                overflowX: 'auto',
              }}
            >
              <table
                style={{
                  width: '100%',
                }}
              >
                <thead>
                  <tr>
                    <th>
                      Date
                    </th>

                    <th>
                      Time
                    </th>

                    <th>
                      Status
                    </th>

                    <th>
                      Next alert
                    </th>

                    <th>
                      Actions
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {schedule.events.map(
                    event => {
                      const effective =
                        (
                          event.status ===
                            'snoozed' &&
                          event
                            .snoozed_until
                        )
                          ? event
                              .snoozed_until
                          : event
                              .scheduled_at

                      return (
                        <tr
                          key={event.id}
                        >
                          <td>
                            {formatDate(
                              event
                                .scheduled_at
                            )}
                          </td>

                          <td>
                            {formatTime(
                              event
                                .scheduled_at
                            )}
                          </td>

                          <td>
                            <span
                              className="badge"
                            >
                              {statusText(
                                event.status
                              )}
                            </span>
                          </td>

                          <td>
                            {(
                              event.status ===
                                'pending' ||
                              event.status ===
                                'snoozed'
                            )
                              ? (
                                <>
                                  {formatDate(
                                    effective
                                  )}
                                  <br />
                                  <strong>
                                    {formatTime(
                                      effective
                                    )}
                                  </strong>
                                </>
                              )
                              : '—'}
                          </td>

                          <td>
                            {(
                              event.status ===
                                'pending' ||
                              event.status ===
                                'snoozed'
                            ) ? (
                              <div
                                style={{
                                  display:
                                    'flex',
                                  gap: 6,
                                  flexWrap:
                                    'wrap',
                                }}
                              >
                                <button
                                  type="button"
                                  className="secondary"
                                  disabled={
                                    busy ===
                                    `${event.id}-taken`
                                  }
                                  onClick={() =>
                                    action(
                                      event.id,
                                      'taken'
                                    )
                                  }
                                >
                                  ✓ Taken
                                </button>

                                <button
                                  type="button"
                                  className="secondary"
                                  disabled={
                                    busy ===
                                    `${event.id}-snooze`
                                  }
                                  onClick={() =>
                                    action(
                                      event.id,
                                      'snooze'
                                    )
                                  }
                                >
                                  Snooze
                                  10 min
                                </button>

                                <button
                                  type="button"
                                  className="secondary"
                                  disabled={
                                    busy ===
                                    `${event.id}-skip`
                                  }
                                  onClick={() =>
                                    action(
                                      event.id,
                                      'skip'
                                    )
                                  }
                                >
                                  Skip
                                </button>
                              </div>
                            ) : '—'}
                          </td>
                        </tr>
                      )
                    }
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )
      )}
    </div>
  )
}