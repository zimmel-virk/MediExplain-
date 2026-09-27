import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react'

import { api } from '../api/client'
import { useAuth } from '../api/auth'
// This component manages the patient-facing medication reminder workflow in
// MediExplain+. It loads doctor-confirmed schedules, identifies the next pending
// or snoozed medication event, groups medicines that are due at the same time,
// and alerts the patient through browser notifications, an audible alarm and
// authenticated spoken reminder audio. It also records patient actions such as
// taken, snoozed or skipped and keeps the reminder state synchronized with the
// backend without creating medication instructions on the frontend.

const REFRESH_MS = 30000

const MAX_OVERDUE_MS =
  24 * 60 * 60 * 1000

// These timings control reminder refresh, grouping and playback behaviour.
// Medicines due within the same minute are handled as one reminder session,
// while alarm and voice repetition continue until the patient responds.
const SAME_TIME_WINDOW_MS = 60000

// Repeat normal alarm until patient responds.
const ALARM_REPEAT_MS = 4000

// Pause before repeating the complete voice sequence.
const VOICE_REPEAT_DELAY_MS = 12000

// Pause between medicine 1, medicine 2, etc.
const BETWEEN_MEDICINES_MS = 1700

// Slightly slower speech for accessibility.
const VOICE_PLAYBACK_RATE = 0.96


function sleep(ms) {
  return new Promise(
    resolve => setTimeout(resolve, ms)
  )
}


export default function MedicationAlarmManager() {
  const { user } = useAuth()

  const [alarmEnabled, setAlarmEnabled] =
    useState(false)

  const [voiceEnabled, setVoiceEnabled] =
    useState(false)

  const [schedules, setSchedules] =
    useState([])

  /*
    active = {
      reminders: [
        {
          schedule,
          event,
          dueAt,
          dueMs
        }
      ],
      dueAt
    }
  */
  const [active, setActive] =
    useState(null)

  const [error, setError] =
    useState(null)

  const [busy, setBusy] =
    useState(false)

  const [reminderPanelPosition, setReminderPanelPosition] =
    useState({ x: 0, y: 0 })

  const [reminderPanelDragging, setReminderPanelDragging] =
    useState(false)

  const reminderPanelDragRef =
    useRef(null)



  const audioContextRef =
    useRef(null)

  const timerRef =
    useRef(null)

  const alarmLoopRef =
    useRef(null)

  const voiceSourceRef =
    useRef(null)

  const voiceRepeatTimerRef =
    useRef(null)

  const voiceSequenceTokenRef =
    useRef(0)

  const voiceBufferCacheRef =
    useRef(new Map())

// Remember each event together with its current due time so the same reminder
// cannot fire repeatedly during schedule refreshes. A snoozed event receives a
// new due time and can therefore correctly trigger again later.
  const firedRef =
    useRef(new Set())


  const isPatient =
    user?.role === 'patient'

  const remindersEnabled =
    alarmEnabled ||
    voiceEnabled


  // =======================================================
  // LOAD PATIENT SCHEDULES
  // =======================================================
// Load the signed-in patient's current medication schedules from the backend.
// Reminder decisions are always based on these stored schedule and event records.
  const loadSchedules =
    useCallback(
      async () => {
        if (!isPatient) {
          return []
        }

        try {
          const data =
            await api.mySchedules()

          const safeData =
            data || []

          setSchedules(
            safeData
          )

          setError(null)

          return safeData

        } catch (e) {
          setError(
            e.message
          )

          return []
        }
      },
      [isPatient]
    )


  // =======================================================
  // WEB AUDIO
  // =======================================================
// Browser audio is created lazily because browsers normally require a user
// interaction before alarm or spoken reminder playback can begin.
  function getAudioContext() {
    const AudioContextClass =
      window.AudioContext ||
      window.webkitAudioContext

    if (!AudioContextClass) {
      throw new Error(
        'Browser audio is not supported.'
      )
    }

    if (!audioContextRef.current) {
      audioContextRef.current =
        new AudioContextClass()
    }

    return audioContextRef.current
  }


  async function unlockAudio() {
    const ctx =
      getAudioContext()

    if (
      ctx.state ===
      'suspended'
    ) {
      await ctx.resume()
    }

    return ctx
  }

// Ask for browser-notification permission when reminders are enabled so a due
// medication can still be surfaced outside the active page content.
  async function prepareNotifications() {
    if (
      'Notification' in window &&
      Notification.permission ===
        'default'
    ) {
      try {
        await Notification
          .requestPermission()
      } catch {}
    }
  }


  // =======================================================
  // NORMAL ALARM
  // =======================================================

  async function playAlarmBurst() {
    const ctx =
      await unlockAudio()

    const tones = [
      {
        delay: 0.00,
        frequency: 659.25,
      },
      {
        delay: 0.30,
        frequency: 880,
      },
      {
        delay: 0.60,
        frequency: 659.25,
      },
      {
        delay: 0.90,
        frequency: 880,
      },
    ]

    tones.forEach(
      ({
        delay,
        frequency,
      }) => {
        const oscillator =
          ctx.createOscillator()

        const gain =
          ctx.createGain()

        oscillator.type =
          'triangle'

        oscillator.frequency.value =
          frequency

        const start =
          ctx.currentTime +
          delay

        const end =
          start + 0.32

        gain.gain.setValueAtTime(
          0.0001,
          start
        )

        gain.gain
          .exponentialRampToValueAtTime(
            0.32,
            start + 0.02
          )

        gain.gain
          .exponentialRampToValueAtTime(
            0.0001,
            end
          )

        oscillator.connect(
          gain
        )

        gain.connect(
          ctx.destination
        )

        oscillator.start(
          start
        )

        oscillator.stop(
          end
        )
      }
    )
  }


  function stopAlarmLoop() {
    if (
      alarmLoopRef.current
    ) {
      clearInterval(
        alarmLoopRef.current
      )

      alarmLoopRef.current =
        null
    }
  }


  async function startAlarmLoop() {
    stopAlarmLoop()

    try {
      await playAlarmBurst()

    } catch (e) {
      console.warn(
        'Alarm error:',
        e
      )
    }

    alarmLoopRef.current =
      setInterval(
        async () => {
          try {
            await playAlarmBurst()

          } catch (e) {
            console.warn(
              'Alarm repeat error:',
              e
            )
          }
        },
        ALARM_REPEAT_MS
      )
  }


  // =======================================================
  // VOICE AUDIO
  // =======================================================

  function stopVoice() {
    if (
      voiceSourceRef.current
    ) {
      try {
        voiceSourceRef.current.stop()
      } catch {}

      voiceSourceRef.current =
        null
    }
  }


  function stopVoiceLoop() {
    voiceSequenceTokenRef.current += 1

    if (
      voiceRepeatTimerRef.current
    ) {
      clearTimeout(
        voiceRepeatTimerRef.current
      )

      voiceRepeatTimerRef.current =
        null
    }

    stopVoice()
  }

// Spoken medication reminders are fetched from the protected backend endpoint
// using the patient's JWT. Decoded audio is cached by event ID so repeated voice
// reminders do not need to download and decode the same audio each time.

  async function loadVoiceBuffer(
    eventId
  ) {
    if (
      voiceBufferCacheRef
        .current
        .has(eventId)
    ) {
      return (
        voiceBufferCacheRef
          .current
          .get(eventId)
      )
    }

    const ctx =
      await unlockAudio()

    const token =
      localStorage.getItem(
        'mxp_token'
      )

    const response =
      await fetch(
        api.medicationEventAudioUrl(
          eventId
        ),
        {
          headers: {
            Authorization:
              `Bearer ${token}`,
          },
        }
      )

    if (!response.ok) {
      let detail = ''

      try {
        const body =
          await response.json()

        detail =
          body.detail ||
          ''

      } catch {}

      throw new Error(
        detail ||
        (
          'Spoken reminder ' +
          `unavailable (${response.status})`
        )
      )
    }

    const arrayBuffer =
      await response.arrayBuffer()

    const audioBuffer =
      await ctx.decodeAudioData(
        arrayBuffer
      )

    voiceBufferCacheRef
      .current
      .set(
        eventId,
        audioBuffer
      )

    return audioBuffer
  }


  async function preloadVoice(
    eventId
  ) {
    if (!voiceEnabled) {
      return
    }

    try {
      await loadVoiceBuffer(
        eventId
      )

    } catch (e) {
      console.warn(
        'Voice preload failed:',
        e
      )
    }
  }


  async function playVoice(
    eventId
  ) {
    const ctx =
      await unlockAudio()

    stopVoice()

    const audioBuffer =
      await loadVoiceBuffer(
        eventId
      )

    return new Promise(
      resolve => {
        const source =
          ctx.createBufferSource()

        source.buffer =
          audioBuffer

        source.playbackRate.value =
          VOICE_PLAYBACK_RATE

        source.connect(
          ctx.destination
        )

        source.onended =
          () => {
            if (
              voiceSourceRef.current ===
              source
            ) {
              voiceSourceRef.current =
                null
            }

            resolve()
          }

        voiceSourceRef.current =
          source

        source.start()
      }
    )
  }
// Play medicines due in the same reminder session one at a time, leaving a short
// pause between them so separate medication instructions remain understandable.

  async function playVoiceSequence(
    reminders,
    token
  ) {
    for (
      let i = 0;
      i < reminders.length;
      i += 1
    ) {
      if (
        token !==
          voiceSequenceTokenRef.current ||
        !voiceEnabled
      ) {
        return
      }

      try {
        await playVoice(
          reminders[i].event.id
        )

      } catch (e) {
        console.warn(
          'Voice reminder error:',
          e
        )
      }

      if (
        i <
        reminders.length - 1
      ) {
        await sleep(
          BETWEEN_MEDICINES_MS
        )
      }
    }
  }


  function startVoiceLoop(
    reminders
  ) {
    stopVoiceLoop()

    const token =
      voiceSequenceTokenRef.current

    const firstDelay =
      alarmEnabled
        ? 1200
        : 200

    async function runSequence() {
      if (
        token !==
          voiceSequenceTokenRef.current ||
        !voiceEnabled
      ) {
        return
      }

      await playVoiceSequence(
        reminders,
        token
      )

      if (
        token !==
          voiceSequenceTokenRef.current ||
        !voiceEnabled
      ) {
        return
      }

      voiceRepeatTimerRef.current =
        setTimeout(
          runSequence,
          VOICE_REPEAT_DELAY_MS
        )
    }

    voiceRepeatTimerRef.current =
      setTimeout(
        runSequence,
        firstDelay
      )
  }


  // =======================================================
  // DATE / TIME
  // =======================================================
// A snoozed reminder uses its revised due time; otherwise the original scheduled
// time remains authoritative.
  function effectiveDue(
    event
  ) {
    if (
      event.status ===
        'snoozed' &&
      event.snoozed_until
    ) {
      return event.snoozed_until
    }

    return event.scheduled_at
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
        weekday: 'long',
        day: 'numeric',
        month: 'long',
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


  function reminderDescription(
    reminder
  ) {
    const {
      schedule,
      dueAt,
    } = reminder

    const parts = [
      schedule.medication_name
        ? (
            `Medicine: ` +
            schedule.medication_name
          )
        : null,

      schedule.dose
        ? (
            `Dose: ` +
            schedule.dose
          )
        : null,

      dueAt
        ? (
            `${formatDate(dueAt)} at ` +
            `${formatTime(dueAt)}`
          )
        : null,

      schedule.frequency
        ? (
            `Frequency: ` +
            schedule.frequency
          )
        : null,

      schedule.timing
        ? (
            `Timing: ` +
            schedule.timing
          )
        : null,

      schedule.food_instruction
        ? (
            `Food: ` +
            schedule.food_instruction
          )
        : null,

      schedule.duration
        ? (
            `Duration: ` +
            schedule.duration
          )
        : null,
    ]

    return parts
      .filter(Boolean)
      .join(' · ')
  }


  // =======================================================
  // GROUP RING
  // =======================================================
// Start one reminder session for the medicines currently due together. Events
// that have already fired at the same due time are ignored, then the remaining
// medicines are shown to the patient and can trigger notification, alarm and
// voice output according to the patient's enabled settings.
  async function ringGroup(
    reminders
  ) {
    if (
      !reminders ||
      !reminders.length
    ) {
      return
    }

    const unfired =
      reminders.filter(
        reminder => {
          const key =
            (
              `${reminder.event.id}|` +
              `${reminder.dueAt}`
            )

          return !firedRef.current
            .has(key)
        }
      )

    if (!unfired.length) {
      return
    }

    for (
      const reminder
      of unfired
    ) {
      const key =
        (
          `${reminder.event.id}|` +
          `${reminder.dueAt}`
        )

      firedRef.current.add(
        key
      )
    }

    const first =
      unfired[0]

    setActive({
      reminders:
        unfired,

      dueAt:
        first.dueAt,
    })


    // -----------------------------------------------------
    // OS / BROWSER NOTIFICATION
    // -----------------------------------------------------

    if (
      'Notification' in window &&
      Notification.permission ===
        'granted'
    ) {
      try {
        const body =
          unfired.length === 1
            ? reminderDescription(
                unfired[0]
              )
            : (
                `${unfired.length} medicines are due: ` +
                unfired
                  .map(
                    item =>
                      item.schedule
                        .medication_name
                  )
                  .filter(Boolean)
                  .join(', ')
              )

        new Notification(
          '💊 Medication reminder',
          {
            body,

            tag:
              (
                'mediexplain-' +
                first.event.id
              ),

            requireInteraction:
              true,
          }
        )

      } catch {}
    }


    // Normal alarm is independent of voice.
    if (alarmEnabled) {
      await startAlarmLoop()
    }

    // Voice is independent of normal alarm.
    if (voiceEnabled) {
      startVoiceLoop(
        unfired
      )
    }
  }


  // =======================================================
  // FIND NEXT EVENT
  // =======================================================
// Find the next usable pending or snoozed medication event and schedule its
// reminder. Old, invalid, inactive or already-fired events are ignored, while
// medicines due within the same time window are grouped into one reminder session.
  function scheduleNextAlarm(
    data = schedules
  ) {
    if (
      timerRef.current
    ) {
      clearTimeout(
        timerRef.current
      )

      timerRef.current =
        null
    }

    if (
      !remindersEnabled ||
      active
    ) {
      return
    }

    const now =
      Date.now()

    const candidates =
      []

    for (
      const schedule
      of data || []
    ) {
      if (
        schedule.active ===
        false
      ) {
        continue
      }

      for (
        const event
        of schedule.events || []
      ) {
        if (
          event.status !==
            'pending' &&
          event.status !==
            'snoozed'
        ) {
          continue
        }

        const dueAt =
          effectiveDue(
            event
          )

        const dueMs =
          new Date(
            dueAt
          ).getTime()

        if (
          !Number.isFinite(
            dueMs
          )
        ) {
          continue
        }

        if (
          now - dueMs >
          MAX_OVERDUE_MS
        ) {
          continue
        }

        const key =
          `${event.id}|${dueAt}`

        if (
          firedRef.current
            .has(key)
        ) {
          continue
        }

        candidates.push({
          schedule,
          event,
          dueAt,
          dueMs,
        })
      }
    }

    if (
      !candidates.length
    ) {
      return
    }

    candidates.sort(
      (a, b) =>
        a.dueMs -
        b.dueMs
    )

    const first =
      candidates[0]

    const sameTime =
      candidates.filter(
        item =>
          Math.abs(
            item.dueMs -
            first.dueMs
          ) <
          SAME_TIME_WINDOW_MS
      )


  // Preload the spoken audio for the upcoming group when voice reminders are
// enabled, reducing delay when the reminder actually becomes due.
    if (voiceEnabled) {
      sameTime.forEach(
        item => {
          preloadVoice(
            item.event.id
          )
        }
      )
    }


    const delay =
      Math.max(
        0,
        first.dueMs -
          Date.now()
      )


    timerRef.current =
      setTimeout(
        () => {
          ringGroup(
            sameTime
          )
        },
        delay
      )
  }


  // =======================================================
  // REFRESH
  // =======================================================
// Refresh schedules periodically and whenever the browser regains focus so the
// frontend stays aligned with medication actions or schedule changes recorded
// by the backend.
  useEffect(() => {
    if (
      !isPatient ||
      !remindersEnabled
    ) {
      return
    }

    let alive = true

    async function refresh() {
      const data =
        await loadSchedules()

      if (!alive) {
        return
      }

      scheduleNextAlarm(
        data
      )
    }

    refresh()

    const refreshTimer =
      setInterval(
        refresh,
        REFRESH_MS
      )

    const onFocus =
      () => refresh()

    window.addEventListener(
      'focus',
      onFocus
    )

    return () => {
      alive = false

      clearInterval(
        refreshTimer
      )

      if (
        timerRef.current
      ) {
        clearTimeout(
          timerRef.current
        )
      }

      window.removeEventListener(
        'focus',
        onFocus
      )
    }
  }, [
    isPatient,
    remindersEnabled,
    loadSchedules,
    alarmEnabled,
    voiceEnabled,
  ])


  useEffect(() => {
    if (
      remindersEnabled &&
      !active
    ) {
      scheduleNextAlarm()
    }

  }, [
    schedules,
    remindersEnabled,
    active,
    alarmEnabled,
    voiceEnabled,
  ])


  // =======================================================
  // ENABLE / DISABLE
  // =======================================================
// Enabling the alarm also unlocks browser audio, requests notification permission
// and plays a short confirmation so the patient knows audible reminders can work.
  async function enableAlarm() {
    setError(null)

    try {
      await unlockAudio()

      await prepareNotifications()

      // Audible confirmation of browser audio.
      await playAlarmBurst()

      setAlarmEnabled(
        true
      )

      await loadSchedules()

    } catch (e) {
      setError(
        e.message
      )
    }
  }


  function disableAlarm() {
    setAlarmEnabled(
      false
    )

    stopAlarmLoop()
  }

// Enabling voice reminders prepares browser audio and attempts to preload the
// next available spoken medication reminder before it becomes due.

  async function enableVoice() {
    setError(null)

    try {
      await unlockAudio()

      await prepareNotifications()

      setVoiceEnabled(
        true
      )

      const data =
        await loadSchedules()

      const next =
        (data || [])
          .flatMap(
            schedule =>
              (
                schedule.events ||
                []
              ).map(
                event => ({
                  schedule,
                  event,
                })
              )
          )
          .find(
            item =>
              (
                item.event.status ===
                  'pending' ||
                item.event.status ===
                  'snoozed'
              )
          )

      if (next) {
        try {
          await loadVoiceBuffer(
            next.event.id
          )
        } catch (e) {
          console.warn(
            'Voice preload failed:',
            e
          )
        }
      }

    } catch (e) {
      setError(
        e.message
      )
    }
  }


  function disableVoice() {
    setVoiceEnabled(
      false
    )

    stopVoiceLoop()
  }


  // =======================================================
  // TEST BUTTONS
  // =======================================================

  async function testAlarm() {
    setError(null)

    try {
      await playAlarmBurst()

    } catch (e) {
      setError(
        e.message
      )
    }
  }


  async function playIndependentLanguageTest() {
    const ctx =
      await unlockAudio()

    stopVoice()

    const token =
      localStorage.getItem(
        'mxp_token'
      )

    if (!token) {
      throw new Error(
        'Authentication token missing'
      )
    }

    const response =
      await fetch(
        '/api/schedules/voice-test',
        {
          headers: {
            Authorization:
              `Bearer ${token}`,
          },
        }
      )

    if (!response.ok) {
      let detail = ''

      try {
        const body =
          await response.json()

        detail =
          body.detail || ''
      } catch {}

      throw new Error(
        detail
        || `Voice test failed (${response.status})`
      )
    }

    const arrayBuffer =
      await response.arrayBuffer()

    const audioBuffer =
      await ctx.decodeAudioData(
        arrayBuffer
      )

    const source =
      ctx.createBufferSource()

    source.buffer =
      audioBuffer

    source.playbackRate.value =
      0.92

    source.connect(
      ctx.destination
    )

    source.onended =
      () => {
        if (
          voiceSourceRef.current
          === source
        ) {
          voiceSourceRef.current =
            null
        }
      }

    voiceSourceRef.current =
      source

    source.start()
  }

// Test the configured patient-language reminder voice. Languages with their own
// dedicated reminder route use the independent voice-test endpoint, while other
// languages can reuse an existing medication event for the playback check.
  async function testVoice() {
    if (
      ['ar', 'ps', 'sd'].includes(
        user?.preferred_language
      )
    ) {
      setError(null)

      try {
        await playIndependentLanguageTest()
      } catch (e) {
        setError(
          `Voice reminder failed: ${e.message}`
        )
      }

      return
    }

    setError(null)

    const schedule =
      schedules.find(
        item =>
          (
            item.events || []
          ).length
      )

    const event =
      schedule?.events?.find(
        item =>
          (
            item.status ===
              'pending' ||
            item.status ===
              'snoozed'
          )
      ) ||
      schedule?.events?.[0]

    if (!event) {
      setError(
        'No medication reminder is available to test.'
      )

      return
    }

    try {
      await playVoice(
        event.id
      )

    } catch (e) {
      setError(
        `Voice reminder failed: ${e.message}`
      )
    }
  }


  // =======================================================
  // EVENT ACTION HELPERS
  // =======================================================
// Record the patient's response to a medication event through the backend.
// Snooze uses the interface's ten-minute delay; taken and skipped are submitted
// as their corresponding event actions.

  async function sendAction(
    eventId,
    actionName
  ) {
    if (
      actionName ===
      'snooze'
    ) {
      return api.medicationEventAction(
        eventId,
        'snooze',
        10
      )
    }

    return api.medicationEventAction(
      eventId,
      actionName
    )
  }

// Handle one medicine from a grouped reminder. After its action is recorded,
// any medicines still awaiting a response remain active and their voice sequence
// is restarted without repeating the completed medicine.
  async function actionOne(
    reminder,
    actionName
  ) {
    if (
      !active ||
      busy
    ) {
      return
    }

    setBusy(true)
    setError(null)

    try {
      await sendAction(
        reminder.event.id,
        actionName
      )

      const remaining =
        active.reminders.filter(
          item =>
            item.event.id !==
            reminder.event.id
        )

      stopVoiceLoop()

      if (
        remaining.length
      ) {
        setActive({
          reminders:
            remaining,

          dueAt:
            active.dueAt,
        })

        if (voiceEnabled) {
          startVoiceLoop(
            remaining
          )
        }

      } else {
        stopAlarmLoop()

        setActive(
          null
        )
      }

      await loadSchedules()

    } catch (e) {
      setError(
        e.message
      )

    } finally {
      setBusy(false)
    }
  }

// Apply the selected response to every medicine in the current reminder group,
// then close the active reminder and reload the schedules from the backend.
  async function actionAll(
    actionName
  ) {
    if (
      !active ||
      busy
    ) {
      return
    }

    setBusy(true)
    setError(null)

    stopAlarmLoop()
    stopVoiceLoop()

    try {
      for (
        const reminder
        of active.reminders
      ) {
        await sendAction(
          reminder.event.id,
          actionName
        )
      }

      setActive(
        null
      )

      await loadSchedules()

    } catch (e) {
      setError(
        e.message
      )

    } finally {
      setBusy(false)
    }
  }


  async function repeatAllVoice() {
    if (
      !active ||
      !voiceEnabled
    ) {
      return
    }

    stopVoiceLoop()

    const token =
      voiceSequenceTokenRef.current

    await playVoiceSequence(
      active.reminders,
      token
    )
  }


  // =======================================================
  // CLEANUP
  // =======================================================

  useEffect(
    () => {
      return () => {
        stopAlarmLoop()
        stopVoiceLoop()

        if (
          timerRef.current
        ) {
          clearTimeout(
            timerRef.current
          )
        }
      }
    },
    []
  )

  // =======================================================
  // DRAGGABLE REMINDER PANEL
  // =======================================================

  function startReminderPanelDrag(e) {
    if (
      e.target.closest(
        'button, a, input, select, textarea, summary'
      )
    ) {
      return
    }

    if (
      e.button !== undefined &&
      e.button !== 0
    ) {
      return
    }

    const rect =
      e.currentTarget.getBoundingClientRect()

    reminderPanelDragRef.current = {
      pointerId: e.pointerId,

      startX: e.clientX,
      startY: e.clientY,

      offsetX:
        reminderPanelPosition.x,

      offsetY:
        reminderPanelPosition.y,

      left: rect.left,
      top: rect.top,

      width: rect.width,
      height: rect.height,
    }

    try {
      e.currentTarget.setPointerCapture(
        e.pointerId
      )
    } catch {}

    setReminderPanelDragging(true)
  }


  function moveReminderPanel(e) {
    const drag =
      reminderPanelDragRef.current

    if (
      !drag ||
      drag.pointerId !== e.pointerId
    ) {
      return
    }

    const dx =
      e.clientX - drag.startX

    const dy =
      e.clientY - drag.startY

    let nextLeft =
      drag.left + dx

    let nextTop =
      drag.top + dy

    nextLeft = Math.max(
      8,
      Math.min(
        nextLeft,
        window.innerWidth -
          drag.width -
          8
      )
    )

    nextTop = Math.max(
      70,
      Math.min(
        nextTop,
        window.innerHeight -
          drag.height -
          8
      )
    )

    setReminderPanelPosition({
      x:
        drag.offsetX +
        nextLeft -
        drag.left,

      y:
        drag.offsetY +
        nextTop -
        drag.top,
    })
  }


  function stopReminderPanelDrag(e) {
    const drag =
      reminderPanelDragRef.current

    if (
      !drag ||
      drag.pointerId !== e.pointerId
    ) {
      return
    }

    try {
      e.currentTarget.releasePointerCapture(
        e.pointerId
      )
    } catch {}

    reminderPanelDragRef.current = null
    setReminderPanelDragging(false)
  }



  if (!isPatient) {
    return null
  }


  // =======================================================
  // UI
  // =======================================================

  return (
    <>
      {/* CONTROL PANEL */}

      <div
        data-reminder-floating-panel="true"
        onPointerDown={startReminderPanelDrag}
        onPointerMove={moveReminderPanel}
        onPointerUp={stopReminderPanelDrag}
        onPointerCancel={stopReminderPanelDrag}
        style={{
          position: 'fixed',
          right: 18,
          bottom: 18,
          zIndex: 5000,
          width:
            'min(410px, calc(100vw - 36px))',
        
          transform:
            `translate(${reminderPanelPosition.x}px, ${reminderPanelPosition.y}px)`,

          cursor:
            reminderPanelDragging
              ? 'grabbing'
              : 'grab',

          userSelect:
            reminderPanelDragging
              ? 'none'
              : 'auto',

          touchAction: 'none',
}}
      >
        <div
          className="card"
          style={{
            padding: 14,
            boxShadow:
              '0 8px 28px rgba(0,0,0,.18)',
          }}
        >
          <strong
            style={{
              fontSize: 17,
            }}
          >
            💊 Medication reminders
          </strong>

          <div
            className="muted"
            style={{
              margin:
                '6px 0 12px',
            }}
          >
            Alarm and voice can be
            switched on or off independently.
          </div>


          {/* ALARM */}

          <div
            style={{
              display: 'flex',
              justifyContent:
                'space-between',
              alignItems: 'center',
              gap: 10,
              marginBottom: 10,
            }}
          >
            <div>
              <strong>
                🔔 Alarm
              </strong>

              <div className="muted">
                Repeats until the
                reminder is handled.
              </div>
            </div>

            {alarmEnabled ? (
              <button
                className="secondary"
                onClick={
                  disableAlarm
                }
              >
                ON ✓
              </button>
            ) : (
              <button
                onClick={
                  enableAlarm
                }
              >
                Enable
              </button>
            )}
          </div>


          {/* VOICE */}

          <div
            style={{
              display: 'flex',
              justifyContent:
                'space-between',
              alignItems: 'center',
              gap: 10,
            }}
          >
            <div>
              <strong>
                🗣️ Voice
              </strong>

              <div className="muted">
                Speaks each due medicine
                slowly and separately.
              </div>
            </div>

            {voiceEnabled ? (
              <button
                className="secondary"
                onClick={
                  disableVoice
                }
              >
                ON ✓
              </button>
            ) : (
              <button
                onClick={
                  enableVoice
                }
              >
                Enable
              </button>
            )}
          </div>


          {(alarmEnabled ||
            voiceEnabled) ? (
            <div
              className="quality-notice"
              style={{
                marginTop: 12,
              }}
            >
              Reminders active.
              {' '}

              {alarmEnabled
                ? 'Alarm ON. '
                : 'Alarm OFF. '}

              {voiceEnabled
                ? 'Voice ON.'
                : 'Voice OFF.'}
            </div>
          ) : null}


          <div
            style={{
              display: 'flex',
              gap: 6,
              marginTop: 10,
              flexWrap: 'wrap',
            }}
          >
            <button
              className="secondary"
              onClick={
                testAlarm
              }
            >
              🔔 Test alarm
            </button>

            <button
              className="secondary"
              onClick={
                testVoice
              }
              disabled={
                !voiceEnabled
              }
            >
              🗣️ Test voice
            </button>
          </div>


          {error ? (
            <div
              className="error"
              style={{
                marginTop: 8,
              }}
            >
              {error}
            </div>
          ) : null}
        </div>
      </div>


      {/* ===================================================
          FULL SCREEN REMINDER
         =================================================== */}

      {active ? (
        <div
          role="alertdialog"
          aria-modal="true"
          aria-live="assertive"
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 9999,
            background:
              'rgba(0,0,0,.68)',
            display: 'flex',
            alignItems: 'center',
            justifyContent:
              'center',
            padding: 20,
            overflowY: 'auto',
          }}
        >
          <div
            className="card"
            style={{
              width:
                'min(720px, 96vw)',
              padding: 28,
              textAlign: 'center',
              maxHeight: '94vh',
              overflowY: 'auto',
            }}
          >
            <div
              style={{
                fontSize: 58,
              }}
            >
              💊
            </div>

            <h2>
              Medication Reminder
            </h2>

            <div
              style={{
                fontSize: 19,
                marginBottom: 18,
              }}
            >
              <strong>
                Date:
              </strong>{' '}
              {formatDate(
                active.dueAt
              )}

              {' · '}

              <strong>
                Time:
              </strong>{' '}

              {formatTime(
                active.dueAt
              )}
            </div>


            {active.reminders.length > 1 ? (
              <div
                className="quality-notice"
                style={{
                  marginBottom: 18,
                }}
              >
                {
                  active.reminders
                    .length
                } medicines are due
                now. They are shown and
                spoken one at a time.
              </div>
            ) : null}


            {/* MEDICINES */}

            <div
              style={{
                display: 'grid',
                gap: 14,
                textAlign: 'left',
              }}
            >
              {active.reminders.map(
                (
                  reminder,
                  index
                ) => {
                  const schedule =
                    reminder.schedule

                  return (
                    <div
                      key={
                        reminder.event.id
                      }
                      className="card"
                      style={{
                        padding: 18,
                        border:
                          '1px solid rgba(0,0,0,.12)',
                      }}
                    >
                      <h3
                        style={{
                          marginTop: 0,
                        }}
                      >
                        {active.reminders
                          .length > 1
                          ? (
                              `Medicine ${
                                index + 1
                              }: `
                            )
                          : ''}

                        {
                          schedule
                            .medication_name
                        }
                      </h3>


                      <div
                        style={{
                          fontSize: 17,
                          lineHeight: 1.7,
                        }}
                      >
                        <div>
                          <strong>
                            Medicine:
                          </strong>{' '}
                          {
                            schedule
                              .medication_name
                          }
                        </div>

                        <div>
                          <strong>
                            Dose / quantity:
                          </strong>{' '}
                          {
                            schedule.dose ||
                            schedule.strength ||
                            '—'
                          }
                        </div>

                        {schedule.frequency ? (
                          <div>
                            <strong>
                              Frequency:
                            </strong>{' '}
                            {
                              schedule
                                .frequency
                            }
                          </div>
                        ) : null}

                        {schedule.timing ? (
                          <div>
                            <strong>
                              Timing:
                            </strong>{' '}
                            {
                              schedule
                                .timing
                            }
                          </div>
                        ) : null}

                        {schedule.food_instruction ? (
                          <div>
                            <strong>
                              Food:
                            </strong>{' '}
                            {
                              schedule
                                .food_instruction
                            }
                          </div>
                        ) : null}

                        {schedule.duration ? (
                          <div>
                            <strong>
                              Duration:
                            </strong>{' '}
                            {
                              schedule
                                .duration
                            }
                          </div>
                        ) : null}

                        {schedule.route ? (
                          <div>
                            <strong>
                              Route:
                            </strong>{' '}
                            {
                              schedule
                                .route
                            }
                          </div>
                        ) : null}

                        <div>
                          <strong>
                            Reminder time:
                          </strong>{' '}
                          {formatTime(
                            reminder.dueAt
                          )}
                        </div>
                      </div>


                      {/* INDIVIDUAL ACTIONS */}

                      <div
                        style={{
                          display: 'flex',
                          gap: 8,
                          flexWrap: 'wrap',
                          marginTop: 14,
                        }}
                      >
                        <button
                          disabled={busy}
                          onClick={() =>
                            actionOne(
                              reminder,
                              'taken'
                            )
                          }
                        >
                          ✓ Taken
                        </button>

                        <button
                          className="secondary"
                          disabled={busy}
                          onClick={() =>
                            actionOne(
                              reminder,
                              'snooze'
                            )
                          }
                        >
                          ⏰ Snooze 10 min
                        </button>

                        <button
                          className="secondary"
                          disabled={busy}
                          onClick={() =>
                            actionOne(
                              reminder,
                              'skip'
                            )
                          }
                        >
                          Skip
                        </button>

                        {voiceEnabled ? (
                          <button
                            className="secondary"
                            disabled={busy}
                            onClick={() =>
                              playVoice(
                                reminder
                                  .event.id
                              )
                            }
                          >
                            🗣️ Repeat this medicine
                          </button>
                        ) : null}
                      </div>
                    </div>
                  )
                }
              )}
            </div>


            {/* GROUP ACTIONS */}

            {active.reminders.length > 1 ? (
              <>
                <hr
                  style={{
                    margin:
                      '22px 0 16px',
                  }}
                />

                <strong>
                  Actions for all due medicines
                </strong>

                <div
                  style={{
                    display: 'flex',
                    justifyContent:
                      'center',
                    flexWrap: 'wrap',
                    gap: 10,
                    marginTop: 12,
                  }}
                >
                  <button
                    disabled={busy}
                    onClick={() =>
                      actionAll(
                        'taken'
                      )
                    }
                  >
                    ✓ Taken all
                  </button>

                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() =>
                      actionAll(
                        'snooze'
                      )
                    }
                  >
                    ⏰ Snooze all 10 min
                  </button>

                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() =>
                      actionAll(
                        'skip'
                      )
                    }
                  >
                    Skip all
                  </button>
                </div>
              </>
            ) : null}


            {voiceEnabled ? (
              <button
                className="secondary"
                disabled={busy}
                onClick={
                  repeatAllVoice
                }
                style={{
                  marginTop: 16,
                }}
              >
                🗣️ Repeat all medicines
              </button>
            ) : null}


            <div
              className="muted"
              style={{
                marginTop: 16,
              }}
            >
              Snooze stops that medicine's
              current reminder and schedules
              it again for 10 minutes later.
            </div>
          </div>
        </div>
      ) : null}
    </>
  )
}