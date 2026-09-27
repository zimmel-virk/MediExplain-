import {
  createContext,
  useContext,
  useEffect,
  useState,
} from 'react'

import {
  api,
  clearToken,
  setToken,
} from './client'

// This context keeps authentication state available across the MediExplain+
// frontend. It restores an existing signed-in session when the application loads,
// handles normal login and MFA completion, stores the returned access token, and
// clears both the token and user state when the session is no longer valid.

const AuthCtx =
  createContext(null)

export function AuthProvider({
  children,
}) {
  const [user, setUser] =
    useState(null)

  const [loading, setLoading] =
    useState(true)

      // When the application first loads, check whether the stored access token still
  // represents a valid session. Invalid or expired credentials are cleared rather
  // than leaving the frontend in an authenticated state.
  useEffect(() => {
    api.me()
      .then(setUser)
      .catch(() => clearToken())
      .finally(
        () => setLoading(false)
      )
  }, [])

    // Perform the initial sign-in request. A normal completed login returns both an
  // access token and user details, while MFA-enabled accounts can continue through
  // the separate verification step before a session is stored.
  async function login(
    email,
    password,
  ) {
    const response =
      await api.login(
        email,
        password,
      )

    if (
      response.access_token
      && response.user
    ) {
      setToken(
        response.access_token
      )

      setUser(
        response.user
      )
    }

    return response
  }

    // Complete either an existing MFA challenge or the initial MFA setup flow.
  // The authenticated session is only stored after the backend successfully
  // verifies the submitted one-time code.

  async function completeMfa(
    mfaToken,
    code,
    setup = false,
  ) {
    const response = setup
      ? await api.verifyMfaSetup(
          mfaToken,
          code,
        )
      : await api.verifyMfa(
          mfaToken,
          code,
        )

    setToken(
      response.access_token
    )

    setUser(
      response.user
    )

    return response.user
  }

    // Remove the locally stored access token and clear the active user from the
  // authentication context so protected frontend views return to a signed-out state.

  function logout() {
    clearToken()
    setUser(null)
  }
// Components use this hook to access the current authentication state and actions
// without passing login information through each level of the component tree.
  return (
    <AuthCtx.Provider
      value={{
        user,
        loading,
        login,
        completeMfa,
        logout,
        setUser,
      }}
    >
      {children}
    </AuthCtx.Provider>
  )
}

export const useAuth =
  () => useContext(AuthCtx)
