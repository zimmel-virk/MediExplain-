import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useAuth } from '../api/auth'

/**
 * This file provides the patient Learning Centre for MediExplain+. It loads
 * multilingual learning content from the backend, lets the patient switch between
 * supported learning languages, and presents simple guidance for using the patient
 * portal safely. The page combines step-by-step guides, short demonstration videos,
 * frequently asked questions and a final safety reminder so patients can understand
 * how to access summaries, medication information, reminders, audio, PDFs and
 * language features without treating the educational material as medical advice.
 */

const learningLanguages = [
  'en',
  'ur',
  'pa_shah',
  'ps',
  'sd',
  'ar',
]

const videos = [
  {
    src: '/videos/patient-portal-demo.mp4',
    key: 'portal',
  },
  {
    src: '/videos/reminders-demo.mp4',
    key: 'reminders',
  },
  {
    src: '/videos/language-demo.mp4',
    key: 'language',
  },
]

const videoText = {
  en: {
    portal: [
      'Using your patient portal',
      'See where to find your released summary, audio, PDF and medication information.',
    ],
    reminders: [
      'Using alarms and reminders',
      'See how Taken, Snooze and Skip work without changing doctor-confirmed instructions.',
    ],
    language: [
      'Reading in your language',
      'See how supported patient-facing language versions are presented.',
    ],
  },

  ur: {
    portal: [
      'مریض پورٹل استعمال کرنا',
      'اپنا جاری شدہ خلاصہ، آڈیو، PDF اور دوا کی معلومات دیکھنے کا طریقہ۔',
    ],
    reminders: [
      'الارم اور ریمائنڈر استعمال کرنا',
      'Taken، Snooze اور Skip کنٹرول استعمال کرنے کا طریقہ۔',
    ],
    language: [
      'اپنی زبان میں پڑھنا',
      'اپنی patient-facing زبان میں معلومات دیکھنے کی رہنمائی۔',
    ],
  },

  pa_shah: {
    portal: [
      'مریض پورٹل ورتنا',
      'Released summary، audio، PDF تے دوا دی معلومات لبھن دا طریقہ۔',
    ],
    reminders: [
      'Alarm تے reminder ورتنا',
      'Taken، Snooze تے Skip controls ورتن دا طریقہ۔',
    ],
    language: [
      'اپنی زبان وچ پڑھنا',
      'اپنی patient-facing زبان وچ معلومات ویکھن دی رہنمائی۔',
    ],
  },

  ps: {
    portal: [
      'د ناروغ پورټل کارول',
      'خپور شوی لنډیز، غږ، PDF او د درملو معلومات وګورئ.',
    ],
    reminders: [
      'د یادونو کارول',
      'د Taken، Snooze او Skip کنټرولونو کارول زده کړئ.',
    ],
    language: [
      'په خپله ژبه لوستل',
      'د ناروغ لپاره په ملاتړ شوې ژبه معلومات وګورئ.',
    ],
  },

  sd: {
    portal: [
      'مريض پورٽل استعمال ڪرڻ',
      'جاري ٿيل خلاصو، آڊيو، PDF ۽ دوائن جي معلومات ڏسو.',
    ],
    reminders: [
      'ياد ڏيارڻيون استعمال ڪرڻ',
      'Taken، Snooze ۽ Skip ڪنٽرول استعمال ڪرڻ سکو.',
    ],
    language: [
      'پنهنجي ٻولي ۾ پڙهڻ',
      'مريض لاءِ سپورٽ ٿيل ٻولي ۾ معلومات ڏسو.',
    ],
  },

  ar: {
    portal: [
      'استخدام بوابة المريض',
      'اعرف أين تجد الملخص الصادر والصوت وPDF ومعلومات الأدوية.',
    ],
    reminders: [
      'استخدام التنبيهات والتذكيرات',
      'تعرّف على استخدام Taken وSnooze وSkip.',
    ],
    language: [
      'القراءة بلغتك',
      'اعرض المعلومات باللغة المدعومة الخاصة بالمريض.',
    ],
  },
}

export default function LearningCentre() {
  const { user } = useAuth()

  const [langs, setLangs] = useState([])
  const [lang, setLang] = useState(
    learningLanguages.includes(
      user.preferred_language
    )
      ? user.preferred_language
      : 'en'
  )
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    api.languages()
      .then(setLangs)
      .catch(() => {})
  }, [])

  useEffect(() => {
    setErr(null)

    api.learning(lang)
      .then(setData)
      .catch(e => setErr(e.message))
  }, [lang])

  const copy =
    videoText[lang]
    || videoText.en

  return (
    <main className="page">
      <section className="hero-panel learning-hero">
        <div>
          <span className="eyebrow">
            PATIENT EDUCATION · SOFTWARE GUIDANCE
          </span>

          <h1>
            {data?.title || 'Patient Learning Centre'}
          </h1>

          <p>
            {data?.subtitle ||
              'Simple guidance for using MediExplain+.'}
          </p>
        </div>

        <label className="hero-select">
          Learning language

          <select
            value={lang}
            onChange={e => setLang(e.target.value)}
          >
            {langs
              .filter(l =>
                learningLanguages.includes(l.code)
              )
              .map(l => (
                <option
                  key={l.code}
                  value={l.code}
                >
                  {l.name}
                </option>
              ))}
          </select>
        </label>
      </section>

      {err && (
        <div className="error panel">
          {err}
        </div>
      )}

      <section className="card">
        <div className="section-head">
          <div>
            <span className="eyebrow">
              QUICK GUIDES
            </span>

            <h2>
              How to use the patient portal safely
            </h2>
          </div>
        </div>

        <div className="guide-grid">
          {data?.guides?.map((g, i) => (
            <div
              className="guide-card"
              key={g.title}
            >
              <span className="guide-number">
                {String(i + 1).padStart(2, '0')}
              </span>

              <h3>{g.title}</h3>
              <p>{g.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="card">
        <span className="eyebrow">
          SHORT DEMOS
        </span>

        <h2>Watch how the portal works</h2>

        <p className="muted">
          These short demonstrations show software
          controls only. They do not give medical
          instructions.
        </p>

        <div className="video-grid">
          {videos.map(v => {
            const txt =
              copy[v.key]
              || videoText.en[v.key]

            return (
              <article
                className="video-card"
                key={v.src}
              >
                <video
                  controls
                  preload="metadata"
                >
                  <source
                    src={v.src}
                    type="video/mp4"
                  />
                </video>

                <div>
                  <h3>{txt[0]}</h3>
                  <p>{txt[1]}</p>
                </div>
              </article>
            )
          })}
        </div>
      </section>

      <section className="card">
        <span className="eyebrow">
          FAQ
        </span>

        <h2>Frequently asked questions</h2>

        <div className="faq-list">
          {data?.faqs?.map(f => (
            <details key={f.q}>
              <summary>{f.q}</summary>
              <p>{f.a}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="learning-note">
        <strong>Remember</strong>

        <span>
          MediExplain+ helps you revisit
          doctor-released information. It is not an
          emergency service and does not independently
          diagnose, prescribe or change treatment.
        </span>
      </section>
    </main>
  )
}
