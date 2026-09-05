import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, type Vehicle } from '../api';

export default function FleetListPage() {
  const [available, setAvailable] = useState<Vehicle[] | null>(null);
  const [out, setOut] = useState<Vehicle[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newVin, setNewVin] = useState('');

  const load = () => {
    setError(null);
    Promise.all([api.fleetAvailable(), api.fleetOut()])
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

      <VehicleTable title="Available" rows={available} />
      <VehicleTable title="Out" rows={out} />
    </div>
  );
}

function VehicleTable({ title, rows }: { title: string; rows: Vehicle[] }) {
  return (
    <div className="ek-section">
      <h2>{title} ({rows.length})</h2>
      {rows.length === 0 ? (
        <p style={{ color: 'var(--ek-gray)', fontSize: 13 }}>None.</p>
      ) : (
        <table className="ek-table">
          <thead>
            <tr>
              <th>VIN</th>
              <th>Status</th>
              <th>Position</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((v) => (
              <tr key={v.id}>
                <td>{v.vin}</td>
                <td><span className={`ek-badge ${v.status === 'available' ? 'ok' : 'neutral'}`}>{v.status}</span></td>
                <td>{v.current_position ? JSON.stringify(v.current_position) : '—'}</td>
                <td><Link className="ek-link" to={`/vehicles/${v.id}`}>View →</Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
