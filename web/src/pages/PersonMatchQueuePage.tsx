import { useEffect, useState } from 'react';
import { api, type PersonMatchQueueItem } from '../api';

export default function PersonMatchQueuePage() {
  const [items, setItems] = useState<PersonMatchQueueItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deciding, setDeciding] = useState<number | null>(null);

  const load = () => {
    setError(null);
    api.listPendingPersonMatches().then(setItems).catch((e) => setError(e.body?.detail ?? e.message));
  };

  useEffect(load, []);

  const handleDecision = async (queueId: number, decision: 'confirmed_match' | 'confirmed_split') => {
    const verb = decision === 'confirmed_match' ? 'CONFIRM this is the same person' : 'SPLIT — this is a different person';
    const ok = window.confirm(`${verb}? This cannot be undone from this screen.`);
    if (!ok) return;
    setDeciding(queueId);
    setError(null);
    try {
      await api.decidePersonMatch(queueId, { decision, actor: 'dashboard' });
      load();
    } catch (e: any) {
      setError(e.body?.detail ?? e.message);
    } finally {
      setDeciding(null);
    }
  };

  if (error && !items) return <p style={{ color: 'var(--ek-danger)' }}>{error}</p>;

  return (
    <div>
      <p style={{ fontSize: 13, color: 'var(--ek-gray)', marginBottom: 20 }}>
        Every row below is a renter/staff intake that matched an existing person by last name + date of birth
        but didn't have an exact email/phone match — a human has to decide whether it's really the same
        person (Confirm) or a coincidental match (Split, creates a new person record). Rows belonging to
        VLS's own identity space are never shown here, by design.
      </p>
      {error && <p style={{ color: 'var(--ek-danger)' }}>{error}</p>}

      {items === null ? <p>Loading…</p> : items.length === 0 ? (
        <p style={{ color: 'var(--ek-gray)' }}>No pending matches. Queue is clear.</p>
      ) : (
        <table className="ek-table">
          <thead>
            <tr>
              <th>Queue ID</th>
              <th>Candidate Person</th>
              <th>Name Submitted</th>
              <th>DOB</th>
              <th>Email</th>
              <th>Phone</th>
              <th>Reason</th>
              <th>Source</th>
              <th>Submitted By</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {items.map((it) => (
              <tr key={it.id}>
                <td>#{it.id}</td>
                <td>#{it.candidate_person_id}</td>
                <td>{it.first_name} {it.last_name}</td>
                <td>{it.date_of_birth ?? '—'}</td>
                <td>{it.email_normalized ?? '—'}</td>
                <td>{it.phone_normalized ?? '—'}</td>
                <td>{it.match_reason}</td>
                <td>{it.source_project}</td>
                <td>{it.submitted_by}</td>
                <td style={{ display: 'flex', gap: 6 }}>
                  <button
                    className="ek-btn"
                    disabled={deciding === it.id}
                    onClick={() => handleDecision(it.id, 'confirmed_match')}
                  >
                    Confirm match
                  </button>
                  <button
                    className="ek-btn secondary"
                    disabled={deciding === it.id}
                    onClick={() => handleDecision(it.id, 'confirmed_split')}
                  >
                    Split (different person)
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
