import { useEffect, useState } from 'react';
import { api, type InsuranceCarrier, type Adjuster, type InsurerPayment, type CarrierMarketRateExhibit } from '../api';

// Handoff §2.8: "Jed has years of data on what carriers actually paid at
// market rate. When an adjuster offers $35-40/day, the exhibit is: this
// same carrier paid market rate on N prior claims." This page is that
// exhibit, plus the carrier/adjuster admin DemandsPage's dropdowns already
// read from but never had a create form for.
export default function CarriersPage() {
  const [carriers, setCarriers] = useState<InsuranceCarrier[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedCarrierId, setSelectedCarrierId] = useState<number | null>(null);
  const [adjusters, setAdjusters] = useState<Adjuster[]>([]);
  const [payments, setPayments] = useState<InsurerPayment[] | null>(null);
  const [exhibit, setExhibit] = useState<CarrierMarketRateExhibit | null>(null);

  const [newCarrierName, setNewCarrierName] = useState('');
  const [newCarrierFax, setNewCarrierFax] = useState('');
  const [newCarrierPhone, setNewCarrierPhone] = useState('');
  const [creatingCarrier, setCreatingCarrier] = useState(false);

  const [newAdjusterName, setNewAdjusterName] = useState('');
  const [creatingAdjuster, setCreatingAdjuster] = useState(false);

  const loadCarriers = () => {
    api.listInsuranceCarriers().then(setCarriers).catch((e) => setError(e.body?.detail ?? e.message));
  };

  useEffect(() => { loadCarriers(); }, []);

  useEffect(() => {
    if (selectedCarrierId == null) { setAdjusters([]); setPayments(null); setExhibit(null); return; }
    api.listAdjustersForCarrier(selectedCarrierId).then(setAdjusters).catch(() => setAdjusters([]));
    api.getCarrierInsurerPayments(selectedCarrierId).then(setPayments).catch(() => setPayments([]));
    api.getCarrierMarketRateExhibit(selectedCarrierId).then(setExhibit).catch(() => setExhibit(null));
  }, [selectedCarrierId]);

  const handleCreateCarrier = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCarrierName.trim()) return;
    setCreatingCarrier(true);
    setError(null);
    try {
      const created = await api.createInsuranceCarrier({
        name: newCarrierName.trim(),
        fax: newCarrierFax.trim() || undefined,
        phone: newCarrierPhone.trim() || undefined,
        actor: 'dashboard',
      });
      setNewCarrierName('');
      setNewCarrierFax('');
      setNewCarrierPhone('');
      loadCarriers();
      setSelectedCarrierId(created.id);
    } catch (e: any) {
      setError(e.body?.detail ?? e.message);
    } finally {
      setCreatingCarrier(false);
    }
  };

  const handleCreateAdjuster = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedCarrierId || !newAdjusterName.trim()) return;
    setCreatingAdjuster(true);
    setError(null);
    try {
      await api.createAdjuster(selectedCarrierId, { name: newAdjusterName.trim(), actor: 'dashboard' });
      setNewAdjusterName('');
      api.listAdjustersForCarrier(selectedCarrierId).then(setAdjusters);
    } catch (e: any) {
      setError(e.body?.detail ?? e.message);
    } finally {
      setCreatingAdjuster(false);
    }
  };

  return (
    <div>
      {error && <p style={{ color: 'var(--ek-danger)' }}>{error}</p>}

      <div className="ek-section">
        <h2>Insurance Carriers</h2>
        <table className="ek-table">
          <thead><tr><th>Name</th><th>Fax</th><th>Phone</th><th /></tr></thead>
          <tbody>
            {carriers.map((c) => (
              <tr key={c.id}>
                <td>{c.name}</td>
                <td>{c.fax ?? '—'}</td>
                <td>{c.phone ?? '—'}</td>
                <td>
                  <button className="ek-btn secondary" onClick={() => setSelectedCarrierId(c.id)}>
                    {selectedCarrierId === c.id ? 'Selected' : 'View exhibit'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <form onSubmit={handleCreateCarrier} className="ek-field-row" style={{ marginTop: 12 }}>
          <label>New carrier</label>
          <input className="ek-input" value={newCarrierName} onChange={(e) => setNewCarrierName(e.target.value)} placeholder="Name" />
          <input className="ek-input" value={newCarrierFax} onChange={(e) => setNewCarrierFax(e.target.value)} placeholder="Fax" style={{ width: 130 }} />
          <input className="ek-input" value={newCarrierPhone} onChange={(e) => setNewCarrierPhone(e.target.value)} placeholder="Phone" style={{ width: 130 }} />
          <button className="ek-btn" type="submit" disabled={creatingCarrier || !newCarrierName.trim()}>
            {creatingCarrier ? 'Creating…' : 'Create carrier'}
          </button>
        </form>
      </div>

      {selectedCarrierId != null && (
        <>
          <div className="ek-section">
            <h2>Market-Rate Exhibit — Carrier #{selectedCarrierId}</h2>
            <p style={{ fontSize: 12, color: 'var(--ek-gray)', marginTop: -6, marginBottom: 14 }}>
              "This same carrier paid market rate on N prior claims" — the exhibit for a lowball offer.
            </p>
            {exhibit === null ? <p>Loading…</p> : (
              <table className="ek-table">
                <thead><tr><th>Claim Count</th><th>Avg Demanded</th><th>Avg Paid</th><th>Avg Market Rate</th></tr></thead>
                <tbody>
                  <tr>
                    <td>{exhibit.claim_count}</td>
                    <td>{exhibit.avg_amount_demanded ? `$${exhibit.avg_amount_demanded}` : '—'}</td>
                    <td>{exhibit.avg_amount_paid ? `$${exhibit.avg_amount_paid}` : '—'}</td>
                    <td>{exhibit.avg_market_rate ? `$${exhibit.avg_market_rate}` : '—'}</td>
                  </tr>
                </tbody>
              </table>
            )}
          </div>

          <div className="ek-section">
            <h2>Resolved Claims History</h2>
            {payments === null ? <p>Loading…</p> : payments.length === 0 ? (
              <p style={{ color: 'var(--ek-gray)', fontSize: 13 }}>No resolved demands against this carrier yet.</p>
            ) : (
              <table className="ek-table">
                <thead><tr><th>Demand</th><th>Rental</th><th>Vehicle Class</th><th>Demanded</th><th>Paid</th><th>Days to Resolve</th><th>Resolved</th></tr></thead>
                <tbody>
                  {payments.map((p) => (
                    <tr key={p.id}>
                      <td>#{p.demand_id}</td>
                      <td>#{p.rental_id}</td>
                      <td>{p.vehicle_class ?? '—'}</td>
                      <td>${p.amount_demanded}</td>
                      <td>${p.amount_paid}</td>
                      <td>{p.days_to_resolve ?? '—'}</td>
                      <td>{new Date(p.resolved_at).toLocaleDateString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="ek-section">
            <h2>Adjusters at Carrier #{selectedCarrierId}</h2>
            <table className="ek-table">
              <thead><tr><th>Name</th><th>Phone</th><th>Email</th></tr></thead>
              <tbody>
                {adjusters.map((a) => (
                  <tr key={a.id}><td>{a.name}</td><td>{a.phone ?? '—'}</td><td>{a.email ?? '—'}</td></tr>
                ))}
              </tbody>
            </table>
            <form onSubmit={handleCreateAdjuster} className="ek-field-row" style={{ marginTop: 12 }}>
              <label>New adjuster</label>
              <input className="ek-input" value={newAdjusterName} onChange={(e) => setNewAdjusterName(e.target.value)} placeholder="Name" />
              <button className="ek-btn" type="submit" disabled={creatingAdjuster || !newAdjusterName.trim()}>
                {creatingAdjuster ? 'Creating…' : 'Add adjuster'}
              </button>
            </form>
          </div>
        </>
      )}
    </div>
  );
}
