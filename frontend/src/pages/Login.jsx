import {
  useState,
} from 'react'

import {
  Link,
  useNavigate,
} from 'react-router-dom'

import {
  useAuth,
} from '../api/auth'


/**
 * This file provides the MediExplain+ sign-in interface and handles the complete
 * frontend authentication flow. It accepts email and password credentials, supports
 * both first-time authenticator setup and normal MFA verification, limits the
 * one-time code to six digits, and routes each authenticated user to the correct
 * workspace according to their role. It also provides quick access to the seeded
 * demo accounts used for testing doctor, assistant, patient and cross-check roles,
 * while keeping patient registration available separately and showing the system's
 * academic research and clinician-review safety notice.
 */


const DEMOS = [
  [
    'Doctor',
    'doctor@demo.com',
  ],
  [
    'Assistant',
    'assistant@demo.com',
  ],
  [
    'English patient',
    'patient.en@demo.com',
  ],
  [
    'Urdu patient',
    'patient.ur@demo.com',
  ],
  [
    'Punjabi patient',
    'patient.pa@demo.com',
  ],
  [
    'Cross-check doctor',
    'reviewer@demo.com',
  ],
]


function routeFor(
  user,
  nav,
) {
  if (
    user.role === 'assistant'
  ) {
    nav('/assistant')
  } else if (
    user.role ===
    'cross_check_doctor'
  ) {
    nav('/cross-check')
  } else {
    nav('/')
  }
}


export default function Login() {
  const {
    login,
    completeMfa,
  } = useAuth()

  const nav =
    useNavigate()

  const [
    email,
    setEmail,
  ] = useState(
    'doctor@demo.com'
  )

  const [
    password,
    setPassword,
  ] = useState(
    'demo1234'
  )

  const [
    challenge,
    setChallenge,
  ] = useState(null)

  const [
    code,
    setCode,
  ] = useState('')

  const [
    err,
    setErr,
  ] = useState(null)

  const [
    loading,
    setLoading,
  ] = useState(false)


  async function submit(
    event,
  ) {
    event.preventDefault()

    setErr(null)
    setLoading(true)

    try {
      const response =
        await login(
          email,
          password,
        )

      if (
        response.status ===
        'mfa_setup_required'
      ) {
        setChallenge({
          mode: 'setup',
          token:
            response.mfa_token,
          secret:
            response
              .setup_secret,
        })

        return
      }

      if (
        response.status ===
        'mfa_required'
      ) {
        setChallenge({
          mode: 'login',
          token:
            response.mfa_token,
        })

        return
      }

      if (
        response.user
      ) {
        routeFor(
          response.user,
          nav,
        )
      }
    } catch (error) {
      setErr(
        error.message
      )
    } finally {
      setLoading(false)
    }
  }


  async function submitMfa(
    event,
  ) {
    event.preventDefault()

    setErr(null)
    setLoading(true)

    try {
      const user =
        await completeMfa(
          challenge.token,
          code,
          challenge.mode
            === 'setup',
        )

      routeFor(
        user,
        nav,
      )
    } catch (error) {
      setErr(
        error.message
      )
    } finally {
      setLoading(false)
    }
  }


  function useDemo(
    address,
  ) {
    setEmail(address)
    setPassword(
      'demo1234'
    )
    setChallenge(null)
    setCode('')
    setErr(null)
  }


  return (
    <div className="auth-shell">
      <div className="auth-card professional-auth-card">
        <div className="brand-auth">
          <div className="brand-mark">
            M+
          </div>

          <div>
            <h1>
              MediExplain+
            </h1>

            <p>
              Secure multilingual patient communication
            </p>
          </div>
        </div>

        <div className="auth-intro">
          <span className="eyebrow">
            REVIEW-FIRST CLINICAL COMMUNICATION
          </span>

          <h2>
            {challenge
              ? 'Two-factor authentication'
              : 'Welcome back'}
          </h2>

          <p>
            {challenge
              ? 'Complete the second authentication step before access is granted.'
              : 'Sign in to the workspace for your authorised role.'}
          </p>
        </div>

        {!challenge && (
          <form
            onSubmit={
              submit
            }
          >
            <label>
              Email
            </label>

            <input
              value={email}
              onChange={
                event =>
                  setEmail(
                    event
                      .target
                      .value
                  )
              }
              type="email"
              autoComplete="username"
              required
            />

            <label>
              Password
            </label>

            <input
              value={
                password
              }
              onChange={
                event =>
                  setPassword(
                    event
                      .target
                      .value
                  )
              }
              type="password"
              autoComplete="current-password"
              required
            />

            {err && (
              <div className="error">
                {err}
              </div>
            )}

            <button
              style={{
                width: '100%',
                marginTop: 20,
              }}
              disabled={
                loading
              }
            >
              {loading
                ? 'Checking credentials…'
                : 'Continue securely'}
            </button>
          </form>
        )}

        {challenge && (
          <form
            onSubmit={
              submitMfa
            }
          >
            {challenge.mode
              === 'setup' && (
                <>
                  <div className="warning-panel">
                    <strong>
                      Set up your authenticator app
                    </strong>

                    <span>
                      Add a new time-based account in Google Authenticator,
                      Microsoft Authenticator, Authy or another compatible
                      authenticator. Enter the setup key below manually.
                    </span>
                  </div>

                  <label>
                    Authenticator setup key
                  </label>

                  <div
                    className="panel"
                    style={{
                      overflowWrap:
                        'anywhere',
                      fontFamily:
                        'monospace',
                    }}
                  >
                    {
                      challenge.secret
                    }
                  </div>
                </>
              )}

            <label>
              6-digit authentication code
            </label>

            <input
              value={code}
              onChange={
                event =>
                  setCode(
                    event
                      .target
                      .value
                      .replace(
                        /\D/g,
                        ''
                      )
                      .slice(
                        0,
                        6
                      )
                  )
              }
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="000000"
              required
            />

            {err && (
              <div className="error">
                {err}
              </div>
            )}

            <button
              style={{
                width: '100%',
                marginTop: 20,
              }}
              disabled={
                loading
              }
            >
              {loading
                ? 'Verifying…'
                : challenge.mode ===
                  'setup'
                ? 'Enable 2FA and sign in'
                : 'Verify and sign in'}
            </button>

            <button
              type="button"
              className="ghost"
              style={{
                width: '100%',
                marginTop: 10,
              }}
              onClick={() => {
                setChallenge(
                  null
                )
                setCode('')
                setErr(null)
              }}
            >
              Back to sign in
            </button>
          </form>
        )}

        {!challenge && (
          <>
            <div className="auth-switch">
              Patient without an account?{' '}
              <Link to="/register">
                Create a patient account
              </Link>
            </div>

            <div className="demo-login-box">
              <strong>
                Demo workspaces
              </strong>

              <span>
                Seeded demo accounts use password{' '}
                <code>
                  demo1234
                </code>{' '}
                and require authenticator setup on first 2FA login.
              </span>

              <div className="demo-login-grid">
                {DEMOS.map(
                  ([
                    label,
                    address,
                  ]) => (
                    <button
                      key={
                        address
                      }
                      type="button"
                      className="demo-account"
                      onClick={() =>
                        useDemo(
                          address
                        )
                      }
                    >
                      <span>
                        {label}
                      </span>

                      <small>
                        {address}
                      </small>
                    </button>
                  )
                )}
              </div>
            </div>
          </>
        )}

        <div className="disclaimer">
          Academic research prototype. MediExplain+ supports clinician-reviewed communication and does not diagnose or prescribe.
        </div>
      </div>
    </div>
  )
}
