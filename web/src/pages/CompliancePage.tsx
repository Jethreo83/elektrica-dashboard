import { useEffect, useState } from 'react';
import { api, type ComplianceItemType, type ComplianceItemStatus } from '../api';

export default function CompliancePage() {
  const [expiring, setExpiring] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [itemType, setItemType] = useState<ComplianceItemType>('dealer_license');
  const [description, setDescription] = useState('');
  const [expirationDate, setExpirationDate] = useState('');
  const [vehicleId, setVehicleId] = useState('');

  const load = () => {
    api.complianceExpiringSoon().then(setExpiring).catch((e) => setError(e.body?.detail ?? e.message));
  };

  useEffect(load, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!description.trim() || !expirationDate) return;
    setCreating(true);
    setError(null);
    try {
      await api.createComplianceItem({
        item_type: itemType,
        description: description.trim(),
        expiration_date: expirationDate,
        actor: 'dashboard',
        vehicle_id: vehicleId ? Number(vehicleId) : undefined,
      });
      setDescription(''); setExpirationDate(''); setVehicleId('');
      load();
    } catch (e: any) {
      setError(e.body?.detail ?? e.message);
    } finally {
      setCreating(false);
    }
  };

  const handleRenew = async (id: number) => {
    try {
      await api.updateComplianceItemStatus(id, { status: 'renewed', actor: 'dashboard' });
      load();
    } catch (e: any) {
      setError(e.body?.detail ?? e.message);
    }
  };

  return (
    <div>
      {error && <p style={{ color: 'var(--ek-danger)' }}>{error}</p>}

      <div className="ek-section">
        <h2>Add Compliance Item</h2>
        <form onSubmit={handleCreate} className="ek-field-row">
          <label>Type</label>
          <select className="ek-select" value={itemType} onChange={(e) => setItemType(e.target.value as ComplianceItemType)}>
            <option value="dealer_license">dealer_license</option>
            <option value="registration">registration</option>
            <option value="insurance">insurance</option>
            <option value="other">other</option>
          </select>
          <label>Description</label>
          <input className="ek-input" value={description} onChange={(e) => setDescription(e.target.value)} style={{ minWidth: 200 }} />
          <label>Expires</label>
          <input className="ek-input" type="date" value={expirationDate} onChange={(e) => setExpirationDate(e.target.value)} />
          <label>Vehicle ID (optional)</label>
          <input className="ek-input" value={vehicleId} onChange={(e) => setVehicleId(e.target.value)} style={{ width: 90 }} />
          <button className="ek-btn" type="submit" disabled={creating || !description.trim() || !expirationDate}>
            {creating ? 'Adding…' : 'Add item'}
          </button>
        </form>
      </div>

      <div className="ek-section">
        <h2>Expiring Soon (within 30 days)</h2>
        {expiring === null ? <p>Loading…</p> : expiring.length === 0 ? (
          <p style={{ color: 'var(--ek-gray)', fontSize: 13 }}>Nothing expiring soon. Good.</p>
        ) : (
          <table className="ek-table">
            <thead>
              <tr>
                {Object.keys(expiring[0]).map((k) => <th key={k}>{k}</th>)}
                <th />
              </tr>
            </thead>
            <tbody>
              {expiring.map((row, i) => (
                <tr key={i}>
                  {Object.values(row).map((v, j) => <td key={j}>{String(v)}</td>)}
                  <td>
                    {row.id && (
                      <button className="ek-btn secondary" onClick={() => handleRenew(Number(row.id))}>Mark renewed</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
