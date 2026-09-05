import { useState } from 'react';
import { api, type Toll } from '../api';

export default function TollsPage() {
  const [rentalId, setRentalId] = useState('');
  const [tolls, setTolls] = useState<Toll[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [recordId, setRecordId] = useState('');
  const [amount, setAmount] = useState('');
  const [tollDate, setTollDate] = useState('');
  const [confirming, setConfirming] = useState<number | null>(null);

  const load = () => {
    if (!rentalId.trim()) return;
    setError(null);
    api.getRentalTolls(Number(rentalId)).then(setTolls).catch((e) => setError(e.body?.detail ?? e.message));
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rentalId.trim() || !recordId.trim() || !amount.trim() || !tollDate.trim()) return;
    setCreating(true);
    setError(null);
    try {
      await api.createToll(Number(rentalId), {
        tolloptics_record_id: recordId.trim(),
        amount: amount.trim(),
        toll_date: tollDate,
        actor: 'dashboard',
      });
      setRecordId(''); setAmount(''); setTollDate('');
      load();
    } catch (e: any) {
      setError(e.body?.detail ?? e.message);
    } finally {
      setCreating(false);
    }
  };

  const handleConfirm = async (tollId: number) => {
    setConfirming(tollId);
    try {
      await api.confirmToll(tollId);
      load();
    } catch (e: any) {
      setError(e.body?.detail ?? e.message);
    } finally {
      setConfirming(null);
    }
  };

  return (
    <div>
      {error && <p style={{ color: 'var(--ek-danger)' }}>{error}</p>}
      <div className="ek-section">
        <h2>Tolls for a Rental</h2>
        <div className="ek-field-row">
          <label>Rental ID</label>
          <input className="ek-input" value={rentalId} onChange={(e) => setRentalId(e.target.value)} style={{ width: 100 }} />
          <button className="ek-btn secondary" onClick={load} disabled={!rentalId.trim()}>Load tolls</button>
        </div>

        <form onSubmit={handleCreate} className="ek-field-row" style={{ marginTop: 12 }}>
          <label>TollOptics record ID</label>
          <input className="ek-input" value={recordId} onChange={(e) => setRecordId(e.target.value)} style={{ width: 180 }} />
          <label>Amount</label>
          <input className="ek-input" value={amount} onChange={(e) => setAmount(e.target.value)} style={{ width: 90 }} placeholder="0.00" />
          <label>Date</label>
          <input className="ek-input" type="date" value={tollDate} onChange={(e) => setTollDate(e.target.value)} />
          <button className="ek-btn" type="submit" disabled={creating || !rentalId.trim()}>
            {creating ? 'Adding…' : 'Add toll'}
          </button>
        </form>
      </div>

      {tolls && (
        <div className="ek-section">
          <h2>Tolls for Rental #{rentalId}</h2>
          {tolls.length === 0 ? (
            <p style={{ color: 'var(--ek-gray)', fontSize: 13 }}>None.</p>
          ) : (
            <table className="ek-table">
              <thead><tr><th>Record ID</th><th>Date</th><th>Amount</th><th>Confirmed</th><th /></tr></thead>
              <tbody>
                {tolls.map((t) => (
                  <tr key={t.id}>
                    <td>{t.tolloptics_record_id}</td>
                    <td>{t.toll_date}</td>
                    <td>${t.amount}</td>
                    <td><span className={`ek-badge ${t.confirmed ? 'ok' : 'neutral'}`}>{t.confirmed ? 'Confirmed' : 'Unconfirmed'}</span></td>
                    <td>
                      {!t.confirmed && (
                        <button className="ek-btn secondary" onClick={() => handleConfirm(t.id)} disabled={confirming === t.id}>
                          {confirming === t.id ? 'Confirming…' : 'Confirm'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
