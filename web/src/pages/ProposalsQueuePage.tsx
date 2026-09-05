import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, type Proposal } from '../api';

// Handoff §1.7: the future rental-operations bot writes rows here
// (POST /rentals/{id}/proposals, gated server-side by an X-Api-Key
// header this dashboard never sends) whenever it observes something
// that COULD change a rental -- a departure/return/date/toll
// candidate -- but never writes it to the real record itself. A
// human decides accept/reject here. No bot has been built yet
// (handoff §1.7/E-3 explicitly defers that), so this queue is
// expected to be empty until one exists; the page still needs to
// exist so the backend's own bot-write contract is reviewable end to
// end, same reasoning as PersonMatchQueuePage existing before real
// queued rows did.
export default function ProposalsQueuePage() {
  const [items, setItems] = useState<Proposal[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deciding, setDeciding] = useState<number | null>(null);

  const load = () => {
    setError(null);
    api.listPendingProposals().then(setItems).catch((e) => setError(e.body?.detail ?? e.message));
  };

  useEffect(load, []);

  const handleDecision = async (proposalId: number, status: 'accepted' | 'rejected') => {
    const verb = status === 'accepted' ? 'ACCEPT this proposed change' : 'REJECT this proposed change';
    const ok = window.confirm(`${verb}? This cannot be undone from this screen.`);
    if (!ok) return;
    setDeciding(proposalId);
    setError(null);
    try {
      await api.decideProposal(proposalId, { status, actor: 'dashboard' });
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
        Bot-proposed changes to a rental (departure/return/dates/tolls) wait here for a human
        decision — nothing a bot observes is ever written to the real rental record automatically.
        Empty today is expected: no rental-operations bot has been built yet (handoff §1.7 defers
        that build), so this queue only has rows once one exists and starts writing to it via its
        scoped API key.
      </p>
      {error && <p style={{ color: 'var(--ek-danger)' }}>{error}</p>}

      {items === null ? <p>Loading…</p> : items.length === 0 ? (
        <p style={{ color: 'var(--ek-gray)' }}>No pending proposals. Queue is clear.</p>
      ) : (
        <table className="ek-table">
          <thead>
            <tr>
              <th>Proposal ID</th>
              <th>Rental</th>
              <th>Kind</th>
              <th>Proposed Values</th>
              <th>Source</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {items.map((p) => (
              <tr key={p.id}>
                <td>#{p.id}</td>
                <td><Link className="ek-link" to={`/rentals/${p.rental_id}`}>#{p.rental_id}</Link></td>
                <td>{p.kind}</td>
                <td><code style={{ fontSize: 12 }}>{JSON.stringify(p.proposed_values)}</code></td>
                <td>{p.source_system}</td>
                <td style={{ display: 'flex', gap: 6 }}>
                  <button
                    className="ek-btn"
                    disabled={deciding === p.id}
                    onClick={() => handleDecision(p.id, 'accepted')}
                  >
                    Accept
                  </button>
                  <button
                    className="ek-btn secondary"
                    disabled={deciding === p.id}
                    onClick={() => handleDecision(p.id, 'rejected')}
                  >
                    Reject
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
