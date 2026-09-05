import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api, type Rental, type RentalEvent, type RentalState, type Demand, type Toll, type Payment } from '../api';

const ALL_STATES: RentalState[] = [
  'active', 'finished', 'needs_demand', 'needs_more_information', 'demand_sent',
  'negotiating', 'no_offer', 'needs_lawsuit', 'needs_served', 'in_litigation', 'resolved',
];

export default function RentalDetailPage() {
  const { id } = useParams();
  const rentalId = Number(id);
  const [rental, setRental] = useState<Rental | null>(null);
  const [events, setEvents] = useState<RentalEvent[] | null>(null);
  const [demands, setDemands] = useState<Demand[] | null>(null);
  const [tolls, setTolls] = useState<Toll[] | null>(null);
  const [payments, setPayments] = useState<Payment[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [transitioning, setTransitioning] = useState(false);
  const [targetState, setTargetState] = useState<RentalState>('finished');
  const [notes, setNotes] = useState('');

  const load = () => {
    setError(null);
    Promise.all([
      api.getRental(rentalId),
      api.getRentalEvents(rentalId),
      api.getRentalDemands(rentalId),
      api.getRentalTolls(rentalId),
      api.getRentalPayments(rentalId),
    ])
      .then(([r, e, d, t, p]) => { setRental(r); setEvents(e); setDemands(d); setTolls(t); setPayments(p); })
      .catch((e) => setError(e.body?.detail ?? e.message));
  };

  useEffect(load, [rentalId]);

  const handleTransition = async (e: React.FormEvent) => {
    e.preventDefault();
    setTransitioning(true);
    setError(null);
    try {
      await api.transitionRental(rentalId, { target_state: targetState, actor: 'dashboard', source: 'manual', notes: notes || undefined });
      setNotes('');
      load();
    } catch (e: any) {
      setError(e.body?.detail ?? e.message);
    } finally {
      setTransitioning(false);
    }
  };

  if (error && !rental) return <p style={{ color: 'var(--ek-danger)' }}>{error}</p>;
  if (!rental) return <p>Loading…</p>;

  return (
    <div>
      <p><Link className="ek-link" to="/rentals">← Back to Rentals</Link></p>

      <div className="ek-section">
        <h2>Rental #{rental.id}</h2>
        <dl style={{ display: 'grid', gridTemplateColumns: '180px 1fr', rowGap: 10 }}>
          <dt style={{ color: 'var(--ek-gray)', fontSize: 12, fontWeight: 600 }}>Vehicle</dt>
          <dd style={{ margin: 0 }}><Link className="ek-link" to={`/vehicles/${rental.vehicle_id}`}>#{rental.vehicle_id}</Link></dd>
          <dt style={{ color: 'var(--ek-gray)', fontSize: 12, fontWeight: 600 }}>Renter</dt>
          <dd style={{ margin: 0 }}>#{rental.renter_id}</dd>
          <dt style={{ color: 'var(--ek-gray)', fontSize: 12, fontWeight: 600 }}>Body shop</dt>
          <dd style={{ margin: 0 }}>{rental.body_shop ?? '—'}</dd>
          <dt style={{ color: 'var(--ek-gray)', fontSize: 12, fontWeight: 600 }}>Billed to</dt>
          <dd style={{ margin: 0 }}>{rental.billed_to ?? '—'}</dd>
          <dt style={{ color: 'var(--ek-gray)', fontSize: 12, fontWeight: 600 }}>Current state</dt>
          <dd style={{ margin: 0 }}><span className="ek-badge ok">{rental.current_state}</span></dd>
          <dt style={{ color: 'var(--ek-gray)', fontSize: 12, fontWeight: 600 }}>VLS case</dt>
          <dd style={{ margin: 0 }}>{rental.vls_case_id ?? 'Not linked'}</dd>
        </dl>
      </div>

      <div className="ek-section">
        <h2>Advance State</h2>
        <p style={{ fontSize: 12, color: 'var(--ek-gray)', marginTop: -6, marginBottom: 14 }}>
          The database's state-machine trigger is the source of truth for which transitions are legal from
          the current state ({rental.current_state}) — an illegal jump will be rejected with a clear error, not silently accepted.
        </p>
        {error && <p style={{ color: 'var(--ek-danger)', fontSize: 13 }}>{error}</p>}
        <form onSubmit={handleTransition} className="ek-field-row">
          <label>Target state</label>
          <select className="ek-select" value={targetState} onChange={(e) => setTargetState(e.target.value as RentalState)}>
            {ALL_STATES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <input
            className="ek-input"
            placeholder="Notes (optional)"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            style={{ minWidth: 220 }}
          />
          <button className="ek-btn" type="submit" disabled={transitioning}>
            {transitioning ? 'Transitioning…' : 'Transition'}
          </button>
        </form>
      </div>

      <div className="ek-section">
        <h2>Event History</h2>
        {!events || events.length === 0 ? (
          <p style={{ color: 'var(--ek-gray)', fontSize: 13 }}>No events yet.</p>
        ) : (
          <table className="ek-table">
            <thead><tr><th>Event</th><th>Source</th><th>Confirmed</th></tr></thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id}>
                  <td>{e.event_type}</td>
                  <td>{e.source}</td>
                  <td>{e.confirmed ? 'Yes' : 'No'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="ek-section">
        <h2>Demands ({demands?.length ?? 0})</h2>
        {!demands || demands.length === 0 ? (
          <p style={{ color: 'var(--ek-gray)', fontSize: 13 }}>None yet. <Link className="ek-link" to="/demands">Create one on the Demands page →</Link></p>
        ) : (
          <table className="ek-table">
            <thead><tr><th>Type</th><th>Recipient</th><th>Amount</th><th>Status</th></tr></thead>
            <tbody>
              {demands.map((d) => (
                <tr key={d.id}>
                  <td>{d.demand_type}</td>
                  <td>{d.recipient_type}</td>
                  <td>${d.amount}</td>
                  <td><span className={`ek-badge ${d.status === 'sent' ? 'ok' : 'neutral'}`}>{d.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="ek-section">
        <h2>Tolls ({tolls?.length ?? 0})</h2>
        {!tolls || tolls.length === 0 ? (
          <p style={{ color: 'var(--ek-gray)', fontSize: 13 }}>None yet.</p>
        ) : (
          <table className="ek-table">
            <thead><tr><th>Date</th><th>Amount</th><th>Confirmed</th></tr></thead>
            <tbody>
              {tolls.map((t) => (
                <tr key={t.id}>
                  <td>{t.toll_date}</td>
                  <td>${t.amount}</td>
                  <td>{t.confirmed ? 'Yes' : 'No'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="ek-section">
        <h2>Payments ({payments?.length ?? 0})</h2>
        {!payments || payments.length === 0 ? (
          <p style={{ color: 'var(--ek-gray)', fontSize: 13 }}>None yet.</p>
        ) : (
          <table className="ek-table">
            <thead><tr><th>Source</th><th>Amount</th></tr></thead>
            <tbody>
              {payments.map((p) => (
                <tr key={p.id}>
                  <td>{p.source}</td>
                  <td>${p.amount}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
