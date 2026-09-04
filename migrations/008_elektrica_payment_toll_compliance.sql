-- 008_elektrica_payment_toll_compliance.sql
-- elektrica.payment + elektrica.toll (handoff §1.6, §2.3 — literal spec,
-- no placeholders) and elektrica.compliance_item (bot's original v1 scope,
-- retained per ADR-001 v2 §3: "Bot's original v1 items retained as part
-- of this scope, not dropped: Lease/Customer management, Compliance
-- (dealer license, renewal reminders), lightweight Financials view").
--
-- No export dependency for any of these three tables — proceeding while
-- the document-generator placement question sits with Jed (low urgency,
-- logged in docs/OVERNIGHT_DECISIONS.md) and the real Sheet exports
-- remain blocked (docs/OVERNIGHT_DECISIONS.md, separate entry).

-- ---------------------------------------------------------------------------
-- elektrica.payment — handoff §1.6 literal spec: "payment table with
-- source (authorize_net | check | insurer_eft | manual), external
-- transaction id, amount, timestamp, and a nullable accounting_sync_ref
-- reserved for QuickBooks. Authorize.net integration is a shared adapter;
-- Rentals uses one-off charges." Polymorphic source_table/source_id
-- (rental or demand) rather than a hard rental_id FK — a payment can be
-- against a rental directly (self-pay) or settling a specific demand.
-- ---------------------------------------------------------------------------

CREATE TYPE elektrica.payment_source AS ENUM ('authorize_net', 'check', 'insurer_eft', 'manual');

CREATE TABLE elektrica.payment (
  id                    BIGSERIAL PRIMARY KEY,

  rental_id             BIGINT NOT NULL REFERENCES elektrica.rental (id),
  demand_id             BIGINT REFERENCES elektrica.demand (id),  -- nullable: a self-pay rental charge has no demand

  source                elektrica.payment_source NOT NULL,
  external_transaction_id TEXT,  -- Authorize.net txn id, check number, insurer EFT ref

  amount                NUMERIC(12,2) NOT NULL CHECK (amount > 0),
  received_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- Reserved per handoff §1.6, nullable, additive: "Elektrica is the book
  -- of record for payments for now. Design the payment table so a
  -- QuickBooks sync can be added additively later" (E-7).
  accounting_sync_ref   TEXT,

  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by            TEXT NOT NULL,

  CONSTRAINT payment_external_txn_id_required_for_authorize_net
    CHECK (source <> 'authorize_net' OR external_transaction_id IS NOT NULL)
);

CREATE INDEX idx_payment_rental ON elektrica.payment (rental_id);
CREATE INDEX idx_payment_demand ON elektrica.payment (demand_id);

GRANT SELECT, INSERT ON elektrica.payment TO elektrica_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA elektrica TO elektrica_app;

-- Payments are a financial record — append-only, same philosophy as
-- elektrica.document / vls.case_event. A correction is a new row
-- (e.g. a reversal), never an edit to history.
REVOKE DELETE, UPDATE ON elektrica.payment FROM PUBLIC;

CREATE OR REPLACE FUNCTION elektrica.payment_forbid_mutation()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'elektrica.payment is an append-only financial record: % is not permitted (id=%)', TG_OP, OLD.id;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_payment_forbid_delete
  BEFORE DELETE ON elektrica.payment
  FOR EACH ROW EXECUTE FUNCTION elektrica.payment_forbid_mutation();

CREATE TRIGGER trg_payment_forbid_update
  BEFORE UPDATE ON elektrica.payment
  FOR EACH ROW EXECUTE FUNCTION elektrica.payment_forbid_mutation();

-- ---------------------------------------------------------------------------
-- elektrica.toll — handoff §2.3 literal spec: "per rental, TollOptics
-- record id, amount, date, confirmed flag."
-- ---------------------------------------------------------------------------

CREATE TABLE elektrica.toll (
  id                    BIGSERIAL PRIMARY KEY,
  rental_id             BIGINT NOT NULL REFERENCES elektrica.rental (id),

  tolloptics_record_id  TEXT NOT NULL,
  amount                NUMERIC(10,2) NOT NULL CHECK (amount >= 0),
  toll_date             DATE NOT NULL,
  confirmed             BOOLEAN NOT NULL DEFAULT false,

  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by            TEXT NOT NULL,

  CONSTRAINT toll_one_row_per_tolloptics_record UNIQUE (tolloptics_record_id)
);

CREATE INDEX idx_toll_rental ON elektrica.toll (rental_id);
CREATE INDEX idx_toll_unconfirmed ON elektrica.toll (rental_id) WHERE confirmed = false;

GRANT SELECT, INSERT, UPDATE ON elektrica.toll TO elektrica_app;

-- Only the confirmed flag may flip after creation (mirrors the
-- confirmed/confirmed_by pattern used elsewhere, simplified since toll
-- has no separate confirmed_by column in the handoff's literal spec —
-- adding one would be inventing a field, not implementing the given one).
CREATE OR REPLACE FUNCTION elektrica.toll_restrict_update()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.rental_id            IS DISTINCT FROM OLD.rental_id
     OR NEW.tolloptics_record_id IS DISTINCT FROM OLD.tolloptics_record_id
     OR NEW.amount             IS DISTINCT FROM OLD.amount
     OR NEW.toll_date          IS DISTINCT FROM OLD.toll_date
     OR NEW.created_at         IS DISTINCT FROM OLD.created_at
     OR NEW.created_by         IS DISTINCT FROM OLD.created_by
  THEN
    RAISE EXCEPTION 'elektrica.toll is immutable except its confirmed flag (id=%)', OLD.id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_toll_restrict_update
  BEFORE UPDATE ON elektrica.toll
  FOR EACH ROW EXECUTE FUNCTION elektrica.toll_restrict_update();

REVOKE DELETE ON elektrica.toll FROM PUBLIC;

CREATE OR REPLACE FUNCTION elektrica.toll_forbid_delete()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'elektrica.toll is append-only: DELETE is not permitted (id=%)', OLD.id;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_toll_forbid_delete
  BEFORE DELETE ON elektrica.toll
  FOR EACH ROW EXECUTE FUNCTION elektrica.toll_forbid_delete();

-- ---------------------------------------------------------------------------
-- elektrica.compliance_item — bot's original v1 scope, retained per
-- ADR-001 v2 §3. Field shape from docs/original-bot-plan.md section 4
-- ("ComplianceItem: id, type (dealer_license/registration/insurance/other),
-- description, expiration_date, status, related_doc_path"), adapted to
-- this schema's conventions (document_id FK instead of a raw path, now
-- that elektrica.document exists; vehicle_id nullable since compliance
-- items like the dealer license apply to the business, not any one
-- vehicle, while registration/insurance are per-vehicle).
-- ---------------------------------------------------------------------------

CREATE TYPE elektrica.compliance_item_type AS ENUM (
  'dealer_license',
  'registration',
  'insurance',
  'other'
);

CREATE TYPE elektrica.compliance_item_status AS ENUM ('active', 'expiring_soon', 'expired', 'renewed');

CREATE TABLE elektrica.compliance_item (
  id                BIGSERIAL PRIMARY KEY,

  item_type         elektrica.compliance_item_type NOT NULL,
  description       TEXT NOT NULL,

  -- Nullable: dealer_license applies to the business as a whole;
  -- registration/insurance are typically per-vehicle.
  vehicle_id        BIGINT REFERENCES elektrica.vehicle (id),

  expiration_date   DATE NOT NULL,
  status            elektrica.compliance_item_status NOT NULL DEFAULT 'active',

  related_document_id BIGINT REFERENCES elektrica.document (id),

  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by        TEXT NOT NULL,
  updated_by        TEXT NOT NULL
);

CREATE INDEX idx_compliance_item_vehicle ON elektrica.compliance_item (vehicle_id);
CREATE INDEX idx_compliance_item_expiration ON elektrica.compliance_item (expiration_date);

GRANT SELECT, INSERT, UPDATE ON elektrica.compliance_item TO elektrica_app;

CREATE OR REPLACE FUNCTION elektrica.compliance_item_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_compliance_item_set_updated_at
  BEFORE UPDATE ON elektrica.compliance_item
  FOR EACH ROW EXECUTE FUNCTION elektrica.compliance_item_set_updated_at();

-- Renewal reminders (original plan §2: "Surface upcoming ... renewal
-- reminders") implemented as a query, same philosophy as every other
-- aging/blocked view in this schema. 30-day window matches the original
-- plan's reporting-view wording ("expiring soon").
CREATE VIEW elektrica.compliance_items_expiring_soon AS
SELECT id, item_type, description, vehicle_id, expiration_date, status,
       (expiration_date - CURRENT_DATE) AS days_until_expiration
FROM elektrica.compliance_item
WHERE status IN ('active', 'expiring_soon')
  AND expiration_date <= CURRENT_DATE + INTERVAL '30 days';

GRANT SELECT ON elektrica.compliance_items_expiring_soon TO elektrica_app;

-- ---------------------------------------------------------------------------
-- Lightweight Financials view — original plan §2: "Basic revenue/
-- utilization view (vehicles earning vs. idle)." Implemented as a query
-- joining vehicle status against confirmed payment totals, matching the
-- original plan's exact wording rather than inventing new fields.
-- ---------------------------------------------------------------------------

CREATE VIEW elektrica.vehicle_revenue_summary AS
SELECT
  v.id AS vehicle_id,
  v.vin,
  v.status AS vehicle_status,
  COALESCE(SUM(p.amount), 0) AS total_revenue,
  count(DISTINCT r.id) AS total_rentals
FROM elektrica.vehicle v
LEFT JOIN elektrica.rental r ON r.vehicle_id = v.id
LEFT JOIN elektrica.payment p ON p.rental_id = r.id
GROUP BY v.id, v.vin, v.status;

GRANT SELECT ON elektrica.vehicle_revenue_summary TO elektrica_app;
