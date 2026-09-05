import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, type FleetBoardOutRow, type FleetBoardAvailableRow } from '../api';

// Handoff §2.5 literal Fleet-board spec: Out rows show body shop / rental
// type / renter name beside each vehicle; Available rows are "grouped by
// class" in the original spec text, but migration 015 (Jed-confirmed)
// dropped vehicle.class entirely -- there is currently nothing to group
// by, so this renders a single flat list (see api.ts's
// FleetBoardAvailableRow comment / docs/BACKLOG.md for the open
// grouping-key decision).
export default function FleetListPage() {
  const [available, setAvailable] = useState<FleetBoardAvailableRow[] | null>(null);
  const [out, setOut] = useState<FleetBoardOutRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newVin, setNewVin] = useState('');

  const load = () => {
    setError(null);
    Promise.all([api.fleetBoardAvailable(), api.fleetBoardOut()])
      .then(([a, o]) => {
        setAvailable(a);
        setOut(o);
      })
      .catch((e) => setError(e.message));
  };

  useEffect(load, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newVin.trim()) return;
    setCreating(true);
    setError(null);
    try {
      await api.createVehicle({ vin: newVin.trim().toUpperCase(), actor: 'dashboard' });
      setNewVin('');
      load();
    } catch (e: any) {
      setError(e.body?.detail ?? e.message);
    } finally {
      setCreating(false);
    }
  };

  if (error) return <p style={{ color: 'var(--ek-danger)' }}>{error}</p>;
  if (!available || !out) return <p>Loading…</p>;

  return (
    <div>
      <div className="ek-cards">
        <div className="ek-card"><div className="label">Available</div><div className="value ok">{available.length}</div></div>
        <div className="ek-card"><div className="label">Out</div><div className="value">{out.length}</div></div>
        <div className="ek-card"><div className="label">Total Fleet</div><div className="value">{available.length + out.length}</div></div>
      </div>

      <div className="ek-section">
        <h2>Add Vehicle</h2>
        <form onSubmit={handleCreate} className="ek-field-row">
          <input
            className="ek-input"
            placeholder="VIN"
            value={newVin}
            onChange={(e) => setNewVin(e.target.value)}
            style={{ minWidth: 240 }}
          />
          <button className="ek-btn" type="submit" disabled={creating || !newVin.trim()}>
            {creating ? 'Adding…' : 'Add to fleet'}
          </button>
        </form>
      </div>

      <OutTable rows={out} />
      <AvailableTable rows={available} />
    </div>
  );
}

function OutTable({ rows }: { rows: FleetBoardOutRow[] }) {
  return (
    <div className="ek-section">
      <h2>Out ({rows.length})</h2>
      {rows.length === 0 ? (
        <p style={{ color: 'var(--ek-gray)', fontSize: 13 }}>None.</p>
      ) : (
        <table className="ek-table">
          <thead>
            <tr>
              <th>VIN</th>
              <th>Body Shop</th>
              <th>Rental Type</th>
              <th>Renter</th>
              <th>Rental State</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((v) => (
              <tr key={v.vehicle_id}>
                <td>{v.vin}</td>
                <td>{v.body_shop ?? '—'}</td>
                <td>{v.rental_type ?? '—'}</td>
                <td>{v.first_name || v.last_name ? `${v.first_name ?? ''} ${v.last_name ?? ''}`.trim() : '—'}</td>
                <td>{v.current_state ?? '—'}</td>
                <td>
                  <Link className="ek-link" to={`/vehicles/${v.vehicle_id}`}>View →</Link>
                  {v.rental_id != null && (
                    <>
                      {' '}
                      <Link className="ek-link" to={`/rentals/${v.rental_id}`}>Rental →</Link>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function AvailableTable({ rows }: { rows: FleetBoardAvailableRow[] }) {
  return (
    <div className="ek-section">
      <h2>Available ({rows.length})</h2>
      {rows.length === 0 ? (
        <p style={{ color: 'var(--ek-gray)', fontSize: 13 }}>None.</p>
      ) : (
        <table className="ek-table">
          <thead>
            <tr>
              <th>VIN</th>
              <th>Notes</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((v) => (
              <tr key={v.vehicle_id}>
                <td>{v.vin}</td>
                <td>{v.notes ?? '—'}</td>
                <td><Link className="ek-link" to={`/vehicles/${v.vehicle_id}`}>View →</Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
