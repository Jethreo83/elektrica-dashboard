import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, type Rental, type RentalState } from '../api';

const STATE_LABEL: Record<string, string> = {
  active: 'Active', finished: 'Finished', needs_demand: 'Needs Demand',
  needs_more_information: 'Needs More Info', demand_sent: 'Demand Sent',
  negotiating: 'Negotiating', no_offer: 'No Offer', needs_lawsuit: 'Needs Lawsuit',
  needs_served: 'Needs Served', in_litigation: 'In Litigation', resolved: 'Resolved',
};

function badgeClass(state: RentalState): string {
  if (['active'].includes(state)) return 'ok';
  if (['no_offer', 'needs_lawsuit', 'needs_served', 'in_litigation'].includes(state)) return 'danger';
  if (['needs_demand', 'needs_more_information'].includes(state)) return 'warn';
  return 'neutral';
}

export default function RentalListPage() {
  const [rentals, setRentals] = useState<Rental[] | null>(null);
  const [blocked, setBlocked] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<RentalState | ''>('');

  const load = (state?: RentalState) => {
    setError(null);
    Promise.all([api.listRentals(state || undefined), api.listBlockedRentals()])
      .then(([r, b]) => { setRentals(r); setBlocked(b); })
      .catch((e) => setError(e.body?.detail ?? e.message));
  };

  useEffect(() => load(), []);

  const blockedIds = new Set((blocked ?? []).map((b) => Number(b.id ?? b.rental_id)));

  if (error) return <p style={{ color: 'var(--ek-danger)' }}>{error}</p>;
  if (!rentals) return <p>Loading…</p>;

  return (
    <div>
      <div className="ek-cards">
        <div className="ek-card"><div className="label">Total Rentals</div><div className="value">{rentals.length}</div></div>
        <div className="ek-card"><div className="label">Blocked</div><div className={`value ${blockedIds.size > 0 ? 'danger' : 'ok'}`}>{blockedIds.size}</div></div>
      </div>

      <div className="ek-field-row" style={{ marginBottom: 16 }}>
        <label>Filter by state</label>
        <select
          className="ek-select"
          value={filter}
          onChange={(e) => {
            const v = e.target.value as RentalState | '';
            setFilter(v);
            load(v || undefined);
          }}
        >
          <option value="">All states</option>
          {Object.entries(STATE_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>

      <table className="ek-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Vehicle</th>
            <th>Renter</th>
            <th>Body Shop</th>
            <th>State</th>
            <th>Billed To</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rentals.map((r) => (
            <tr key={r.id}>
              <td>#{r.id}</td>
              <td>{r.vehicle_id}</td>
              <td>{r.renter_id}</td>
              <td>{r.body_shop ?? '—'}</td>
              <td>
                <span className={`ek-badge ${badgeClass(r.current_state)}`}>{STATE_LABEL[r.current_state] ?? r.current_state}</span>
                {blockedIds.has(r.id) && <span className="ek-badge danger" style={{ marginLeft: 6 }}>Blocked</span>}
              </td>
              <td>{r.billed_to ?? '—'}</td>
              <td><Link className="ek-link" to={`/rentals/${r.id}`}>View →</Link></td>
            </tr>
          ))}
        </tbody>
      </table>
      {rentals.length === 0 && <p style={{ color: 'var(--ek-gray)', fontSize: 13, marginTop: 12 }}>No rentals match this filter.</p>}
    </div>
  );
}
