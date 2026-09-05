import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api, type Vehicle } from '../api';

export default function VehicleDetailPage() {
  const { id } = useParams();
  const [vehicle, setVehicle] = useState<Vehicle | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api.getVehicle(Number(id)).then(setVehicle).catch((e) => setError(e.body?.detail ?? e.message));
  }, [id]);

  if (error) return <p style={{ color: 'var(--ek-danger)' }}>{error}</p>;
  if (!vehicle) return <p>Loading…</p>;

  return (
    <div>
      <p><Link className="ek-link" to="/">← Back to Fleet</Link></p>
      <div className="ek-section">
        <h2>Vehicle #{vehicle.id}</h2>
        <dl style={{ display: 'grid', gridTemplateColumns: '160px 1fr', rowGap: 10 }}>
          <dt style={{ color: 'var(--ek-gray)', fontSize: 12, fontWeight: 600 }}>VIN</dt>
          <dd style={{ margin: 0 }}>{vehicle.vin}</dd>
          <dt style={{ color: 'var(--ek-gray)', fontSize: 12, fontWeight: 600 }}>Status</dt>
          <dd style={{ margin: 0 }}><span className={`ek-badge ${vehicle.status === 'available' ? 'ok' : 'neutral'}`}>{vehicle.status}</span></dd>
          <dt style={{ color: 'var(--ek-gray)', fontSize: 12, fontWeight: 600 }}>Current position</dt>
          <dd style={{ margin: 0 }}>{vehicle.current_position ? JSON.stringify(vehicle.current_position) : 'No position data (bot-maintained, not yet populated for this vehicle)'}</dd>
        </dl>
      </div>
      <p style={{ fontSize: 12, color: 'var(--ek-gray)' }}>
        Note: vehicle.class / vehicle.tracking_system columns were dropped in migration 015
        (Jed confirmed the real Fleet export has no such data) — not shown here because they no longer exist.
      </p>
    </div>
  );
}
