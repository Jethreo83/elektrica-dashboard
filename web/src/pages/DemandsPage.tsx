import { useEffect, useState } from 'react';
import { api, type Demand, type DemandType, type DemandRecipientType, type InsuranceCarrier, type Adjuster } from '../api';

export default function DemandsPage() {
  const [aging, setAging] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rentalId, setRentalId] = useState('');
  const [demands, setDemands] = useState<Demand[] | null>(null);
  const [carriers, setCarriers] = useState<InsuranceCarrier[]>([]);
  const [adjusters, setAdjusters] = useState<Adjuster[]>([]);
  const [creating, setCreating] = useState(false);
  const [demandType, setDemandType] = useState<DemandType>('primary_insurer');
  const [recipientType, setRecipientType] = useState<DemandRecipientType>('carrier');
  const [amount, setAmount] = useState('');
  const [carrierId, setCarrierId] = useState('');
  const [adjusterId, setAdjusterId] = useState('');
  const [markingSent, setMarkingSent] = useState<number | null>(null);

  useEffect(() => {
    api.agingDemands().then(setAging).catch((e) => setError(e.body?.detail ?? e.message));
    api.listInsuranceCarriers().then(setCarriers).catch(() => {});
  }, []);

  useEffect(() => {
    if (carrierId) api.listAdjustersForCarrier(Number(carrierId)).then(setAdjusters).catch(() => setAdjusters([]));
    else setAdjusters([]);
  }, [carrierId]);

  const loadDemands = () => {
    if (!rentalId.trim()) return;
    setError(null);
    api.getRentalDemands(Number(rentalId)).then(setDemands).catch((e) => setError(e.body?.detail ?? e.message));
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rentalId.trim() || !amount.trim()) return;
    setCreating(true);
    setError(null);
    try {
      await api.createDemand(Number(rentalId), {
        demand_type: demandType,
        recipient_type: recipientType,
        amount: amount.trim(),
        actor: 'dashboard',
        carrier_id: carrierId ? Number(carrierId) : undefined,
        adjuster_id: adjusterId ? Number(adjusterId) : undefined,
      });
      setAmount('');
      loadDemands();
    } catch (e: any) {
      setError(e.body?.detail ?? e.message);
    } finally {
      setCreating(false);
    }
  };

  const handleMarkSent = async (demandId: number) => {
    const via = window.prompt('Sent via (e.g. email, fax, mail):', 'email');
    if (!via) return;
    setMarkingSent(demandId);
    try {
      await api.markDemandSent(demandId, { sent_via: via, actor: 'dashboard' });
      loadDemands();
    } catch (e: any) {
      setError(e.body?.detail ?? e.message);
    } finally {
      setMarkingSent(null);
    }
  };

  return (
    <div>
      {error && <p style={{ color: 'var(--ek-danger)' }}>{error}</p>}

      <div className="ek-section">
        <h2>Aging Demands — 45+ Days, No Offer</h2>
        <p style={{ fontSize: 12, color: 'var(--ek-gray)', marginTop: -6, marginBottom: 14 }}>
          "Silence is the signal" — a demand sitting here with no response needs a human follow-up call.
        </p>
        {aging === null ? <p>Loading…</p> : aging.length === 0 ? (
          <p style={{ color: 'var(--ek-gray)', fontSize: 13 }}>None currently aging. Good.</p>
        ) : (
          <table className="ek-table">
            <thead><tr>{Object.keys(aging[0]).map((k) => <th key={k}>{k}</th>)}</tr></thead>
            <tbody>
              {aging.map((row, i) => (
                <tr key={i}>{Object.values(row).map((v, j) => <td key={j}>{String(v)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="ek-section">
        <h2>Look Up / Create Demand for a Rental</h2>
        <div className="ek-field-row">
          <label>Rental ID</label>
          <input className="ek-input" value={rentalId} onChange={(e) => setRentalId(e.target.value)} style={{ width: 100 }} />
          <button className="ek-btn secondary" onClick={loadDemands} disabled={!rentalId.trim()}>Load demands</button>
        </div>

        <form onSubmit={handleCreate} className="ek-field-row" style={{ marginTop: 12 }}>
          <label>Type</label>
          <select className="ek-select" value={demandType} onChange={(e) => setDemandType(e.target.value as DemandType)}>
            <option value="primary_insurer">primary_insurer</option>
            <option value="uim">uim</option>
            <option value="balance_to_renter">balance_to_renter</option>
          </select>
          <label>Recipient</label>
          <select className="ek-select" value={recipientType} onChange={(e) => setRecipientType(e.target.value as DemandRecipientType)}>
            <option value="carrier">carrier</option>
            <option value="renter">renter</option>
          </select>
          <label>Amount</label>
          <input className="ek-input" value={amount} onChange={(e) => setAmount(e.target.value)} style={{ width: 100 }} placeholder="0.00" />
          {recipientType === 'carrier' && (
            <>
              <label>Carrier</label>
              <select className="ek-select" value={carrierId} onChange={(e) => { setCarrierId(e.target.value); setAdjusterId(''); }}>
                <option value="">— none —</option>
                {carriers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <label>Adjuster</label>
              <select className="ek-select" value={adjusterId} onChange={(e) => setAdjusterId(e.target.value)} disabled={!carrierId}>
                <option value="">— none —</option>
                {adjusters.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </>
          )}
          <button className="ek-btn" type="submit" disabled={creating || !rentalId.trim() || !amount.trim()}>
            {creating ? 'Creating…' : 'Create demand'}
          </button>
        </form>
      </div>

      {demands && (
        <div className="ek-section">
          <h2>Demands for Rental #{rentalId}</h2>
          {demands.length === 0 ? (
            <p style={{ color: 'var(--ek-gray)', fontSize: 13 }}>None.</p>
          ) : (
            <table className="ek-table">
              <thead><tr><th>ID</th><th>Type</th><th>Recipient</th><th>Amount</th><th>Status</th><th>Sent Via</th><th /></tr></thead>
              <tbody>
                {demands.map((d) => (
                  <tr key={d.id}>
                    <td>#{d.id}</td>
                    <td>{d.demand_type}</td>
                    <td>{d.recipient_type}</td>
                    <td>${d.amount}</td>
                    <td><span className={`ek-badge ${d.status === 'sent' ? 'ok' : 'neutral'}`}>{d.status}</span></td>
                    <td>{d.sent_via ?? '—'}</td>
                    <td>
                      {d.status === 'draft' && (
                        <button className="ek-btn secondary" onClick={() => handleMarkSent(d.id)} disabled={markingSent === d.id}>
                          {markingSent === d.id ? 'Marking…' : 'Mark sent'}
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
