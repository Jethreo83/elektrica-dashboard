import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, type Rental, type RentalState, type RentalBilledTo } from '../api';

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

  // Create-rental form state. This closes a real gap found 2026-09-05
  // (cron cycle): POST /rentals (app/api.py) and api.createRental()
  // (api.ts) have both existed since the earliest backend cycles, but
  // no frontend page ever called it -- FleetListPage only lets staff
  // add a vehicle, DemandsPage only lets staff create a demand for an
  // ALREADY-existing rental. There was no dashboard button to actually
  // start a rental, the very first step of the claim-generation-machine
  // flow (handoff §2.2 step 2 "vehicle goes out"). vehicle_id/renter_id
  // are plain numeric ids typed in by staff -- no renter-picker or
  // vehicle-picker exists yet (no GET /renters list route on the
  // backend to populate one; renter ids come from POST /renters/intake
  // or POST /renters, done elsewhere), so this is deliberately a
  // minimal id-entry form, not a full lookup UI.
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [vehicleId, setVehicleId] = useState('');
  const [renterId, setRenterId] = useState('');
  const [bodyShop, setBodyShop] = useState('');
  const [rentalType, setRentalType] = useState('');
  const [billedTo, setBilledTo] = useState<RentalBilledTo | ''>('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  const load = (state?: RentalState) => {
    setError(null);
    Promise.all([api.listRentals(state || undefined), api.listBlockedRentals()])
      .then(([r, b]) => { setRentals(r); setBlocked(b); })
      .catch((e) => setError(e.body?.detail ?? e.message));
  };

  useEffect(() => load(), []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!vehicleId.trim() || !renterId.trim()) return;
    setCreating(true);
    setCreateError(null);
    try {
      await api.createRental({
        vehicle_id: Number(vehicleId),
        renter_id: Number(renterId),
        actor: 'dashboard',
        body_shop: bodyShop.trim() || undefined,
        rental_type: rentalType.trim() || undefined,
        billed_to: billedTo || undefined,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
      });
      setVehicleId(''); setRenterId(''); setBodyShop(''); setRentalType('');
      setBilledTo(''); setStartDate(''); setEndDate('');
      load(filter || undefined);
    } catch (e: any) {
      setCreateError(e.body?.detail ?? e.message);
    } finally {
      setCreating(false);
    }
  };

  const blockedIds = new Set((blocked ?? []).map((b) => Number(b.id ?? b.rental_id)));

  if (error) return <p style={{ color: 'var(--ek-danger)' }}>{error}</p>;
  if (!rentals) return <p>Loading…</p>;

  return (
    <div>
      <div className="ek-cards">
        <div className="ek-card"><div className="label">Total Rentals</div><div className="value">{rentals.length}</div></div>
        <div className="ek-card"><div className="label">Blocked</div><div className={`value ${blockedIds.size > 0 ? 'danger' : 'ok'}`}>{blockedIds.size}</div></div>
      </div>

      <div className="ek-section">
        <h2>Start a Rental</h2>
        <p style={{ fontSize: 12, color: 'var(--ek-gray)', marginTop: -6, marginBottom: 14 }}>
          Vehicle and renter must already exist (add a vehicle on the Fleet page; a renter is created via
          the JotForm intake path). Enter their IDs here -- there is no picker yet since no
          list-all-renters route exists on the backend.
        </p>
        {createError && <p style={{ color: 'var(--ek-danger)', fontSize: 13 }}>{createError}</p>}
        <form onSubmit={handleCreate} className="ek-field-row" style={{ flexWrap: 'wrap' }}>
          <label>Vehicle ID</label>
          <input className="ek-input" value={vehicleId} onChange={(e) => setVehicleId(e.target.value)} style={{ width: 90 }} />
          <label>Renter ID</label>
          <input className="ek-input" value={renterId} onChange={(e) => setRenterId(e.target.value)} style={{ width: 90 }} />
          <label>Body shop</label>
          <input className="ek-input" value={bodyShop} onChange={(e) => setBodyShop(e.target.value)} style={{ width: 160 }} />
          <label>Rental type</label>
          <input className="ek-input" value={rentalType} onChange={(e) => setRentalType(e.target.value)} style={{ width: 140 }} />
          <label>Billed to</label>
          <select className="ek-select" value={billedTo} onChange={(e) => setBilledTo(e.target.value as RentalBilledTo | '')}>
            <option value="">— unset —</option>
            <option value="carrier">carrier</option>
            <option value="self">self</option>
            <option value="body_shop">body_shop</option>
          </select>
          <label>Start date</label>
          <input className="ek-input" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          <label>End date</label>
          <input className="ek-input" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
          <button className="ek-btn" type="submit" disabled={creating || !vehicleId.trim() || !renterId.trim()}>
            {creating ? 'Starting…' : 'Start rental'}
          </button>
        </form>
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
