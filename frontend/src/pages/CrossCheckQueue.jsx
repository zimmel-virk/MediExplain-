import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'

/**
 * This page provides the cross-check work queue for authorised reviewers in
 * MediExplain+. It loads the consultation reviews currently assigned to the
 * signed-in reviewer, shows when each review was requested, and provides a direct
 * link to open the corresponding consultation for independent clinical review.
 * If there are no outstanding assignments, the page simply shows that nothing is
 * currently pending.
 */

export default function CrossCheckQueue() {
  const [items, setItems] = useState([])
  const [err, setErr] = useState(null)
  useEffect(() => {
    api.pendingCrossChecks().then(setItems).catch(e => setErr(e.message))
  }, [])
  return (
    <div className="container">
      <div className="card">
        <h2>Cases assigned to you for cross-check</h2>
        {err && <div className="error">{err}</div>}
        {items.length === 0 && <div className="muted">Nothing pending.</div>}
        {items.length > 0 && (
          <table>
            <thead><tr><th>Consultation</th><th>Requested</th><th></th></tr></thead>
            <tbody>
              {items.map(c => (
                <tr key={c.id}>
                  <td>#{c.consultation_id}</td>
                  <td>{new Date(c.created_at).toLocaleString()}</td>
                  <td><Link to={`/consultation/${c.consultation_id}`}>Review →</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
