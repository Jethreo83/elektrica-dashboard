import { useState } from 'react';
import { api, type Payment, type PaymentSource } from '../api';

export default function PaymentsPage() {
  const [rentalId, setRentalId] = useState('');
  const [payments, setPayments] = useState<Payment[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [source, setSource] = useState<PaymentSource>('authorize_net');
  const [amount, setAmount] = useState('');
  const [demandId, setDemandId] = useState('');
  const [externalTxnId, setExternalTxnId] = useState('');

  const load = () => {
    if (!rentalId.trim()) return;
    setError(null);
    api.getRentalPayments(Number(rentalId)).then(setPayments).catch((e) => setError(e.body?.detail ?? e.message));
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rentalId.trim() || !amount.trim()) return;
    setCreating(true);
    setError(null);
    try {
      await api.createPayment(Number(rentalId), {
        source,
        amount: amount.trim(),
        actor: 'dashboard',
        demand_id: demandId ? Number(demandId) : undefined,
        external_transaction_id: externalTxnId || undefined,
      });
      setAmount(''); setDemandId(''); setExternalTxnId('');
      load();
    } catch (e: any) {
      setError(e.body?.detail ?? e.message);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div>
      {error && <p style={{ color: 'var(--ek-danger)' }}>{error}</p>}
      <div className="ek-section">
        <h2>Payments for a Rental</h2>
        <div className="ek-field-row">
          <label>Rental ID</label>
          <input className="ek-input" value={rentalId} onChange={(e) => setRentalId(e.target.value)} style={{ width: 100 }} />
          <button className="ek-btn secondary" onClick={load} disabled={!rentalId.trim()}>Load payments</button>
        </div>

        <form onSubmit={handleCreate} className="ek-field-row" style={{ marginTop: 12 }}>
          <label>Source</label>
          <select className="ek-select" value={source} onChange={(e) => setSource(e.target.value as PaymentSource)}>
            <option value="authorize_net">authorize_net</option>
            <option value="check">check</option>
            <option value="insurer_eft">insurer_eft</option>
            <option value="manual">manual</option>
          </select>
          <label>Amount</label>
          <input className="ek-input" value={amount} onChange={(e) => setAmount(e.target.value)} style={{ width: 90 }} placeholder="0.00" />
          <label>Demand ID (optional)</label>
          <input className="ek-input" value={demandId} onChange={(e) => setDemandId(e.target.value)} style={{ width: 90 }} />
          <label>External txn ID (optional)</label>
          <input className="ek-input" value={externalTxnId} onChange={(e) => setExternalTxnId(e.target.value)} style={{ width: 150 }} />
          <button className="ek-btn" type="submit" disabled={creating || !rentalId.trim() || !amount.trim()}>
            {creating ? 'Recording…' : 'Record payment'}
          </button>
        </form>
      </div>

      {payments && (
        <div className="ek-section">
          <h2>Payments for Rental #{rentalId}</h2>
          {payments.length === 0 ? (
            <p style={{ color: 'var(--ek-gray)', fontSize: 13 }}>None.</p>
          ) : (
            <table className="ek-table">
              <thead><tr><th>Source</th><th>Amount</th><th>Demand</th></tr></thead>
              <tbody>
                {payments.map((p) => (
                  <tr key={p.id}>
                    <td>{p.source}</td>
                    <td>${p.amount}</td>
                    <td>{p.demand_id ?? '—'}</td>
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
