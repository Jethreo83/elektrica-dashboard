-- 016_elektrica_insurer_payment.sql
-- elektrica.insurer_payment -- handoff §2.8's "strategic asset": the
-- carrier market-rate exhibit ("this same carrier paid market rate on N
-- prior claims"). Closes the last unbuilt item in ADR-001 v2/handoff §6
-- build order step 3 ("vehicle/rental/assignment -> proposals + bot API
-- -> demand + frozen comps -> outbound log -> comms -> payments ->
-- insurer_payment + adjuster"); adjuster (migration 013) was already
-- built, insurer_payment itself was not.
--
-- WHAT THIS IS NOT: this is NOT the historical insurer-payment import
-- (handoff §2.9) -- that stays genuinely blocked on Kay's Elektrica
-- Google OAuth restoration / the real payment-history Sheet export (see
-- docs/OVERNIGHT_DECISIONS.md's open item). This migration builds the
-- table SHAPE and the "populates automatically from every resolved
-- demand" mechanism (handoff §2.8: "Populates automatically ... Grows
-- without effort") using data this codebase already has -- carrier/
-- adjuster (migration 013/014), rental (migration 003), comparable_set
-- (migration 006), payment (migration 008). No historical/legacy rows
-- are inserted by this migration. `source = 'legacy_import'` exists in
-- the enum for when that future work lands, but nothing populates it yet.
--
-- FIELD PROVENANCE (handoff §2.8's own literal field list): "carrier_id,
-- adjuster_id (nullable), claim ref, vehicle class, rental dates, market
-- rate at the time, amount demanded, amount paid, days, resolved_at,
-- source (system | legacy_import), source_ref, frozen flag." All fields
-- below map 1:1 to that sentence:
--   - claim_ref: handoff doesn't say where this comes from and no claim-
--     number field exists anywhere else in this schema yet (rental has
--     no claim_ref column) -- PLACEHOLDER free text, nullable, populated
--     as NULL by the automatic trigger below. Flagging this rather than
--     inventing a source: if a real claim number ever needs to live
--     somewhere, it likely belongs on elektrica.rental itself, not here.
--   - vehicle_class / market_rate_at_time: pulled from the demand's own
--     elektrica.comparable_set row (vehicle_class, computed_average) --
--     the comparable_set IS the "market rate at the time" per handoff
--     §2.8 read together with §2.3's comparable_set/demand relationship.
--   - amount_demanded: demand.amount (the ask).
--   - amount_paid: SUM of elektrica.payment.amount rows linked to this
--     demand_id -- "amount paid" is real money received, not the demand
--     amount; 0 if no payment rows exist yet at resolution time (e.g. a
--     demand resolved as a write-off).
--   - days: PLACEHOLDER interpretation -- handoff doesn't define "days"
--     precisely (days to resolve? rental duration?). Implemented as
--     days_to_resolve = now() - demand.sent_at, since that is the
--     concrete duration this exhibit is actually used for per handoff's
--     own framing ("this same carrier paid market rate on N prior
--     claims" is about negotiation outcomes, not rental length -- rental
--     length is already captured separately via rental_start_date/
--     rental_end_date). NULL if the demand was never actually sent
--     (sent_at IS NULL) -- should not happen in practice since a demand
--     must be sent to reach the carrier/adjuster it's being resolved
--     against, but not assumed.
--
-- AUTOMATIC POPULATION: an AFTER UPDATE trigger on elektrica.demand
-- fires exactly once per demand, the moment demand.status transitions
-- INTO 'resolved' (any prior status -> resolved), and ONLY for
-- recipient_type = 'carrier' demands with a real carrier_id -- a
-- 'balance_to_renter' demand resolving is not an insurer payment at all
-- (handoff §2.8 is explicitly about carriers/adjusters). One row per
-- demand (UNIQUE constraint + ON CONFLICT DO NOTHING guards against a
-- demand somehow re-triggering, e.g. a future correction flow that
-- moves status away from and back to 'resolved').
--
-- APPEND-ONLY / FROZEN: same pattern as elektrica.payment (migration
-- 008) and elektrica.comparable_set (migration 006) -- "Freeze.
-- Verified historical rows become read-only" (handoff §2.9.6) applies
-- to this table's purpose generally, not just the future legacy import.
-- REVOKE UPDATE/DELETE FROM PUBLIC entirely -- no partial-unfreeze
-- workflow exists or is being invented here; a correction is a new
-- row (matching every other append-only table's philosophy in this repo).

-- ---------------------------------------------------------------------------
-- Enum
-- ---------------------------------------------------------------------------

CREATE TYPE elektrica.insurer_payment_source AS ENUM ('system', 'legacy_import');

-- ---------------------------------------------------------------------------
-- elektrica.insurer_payment
-- ---------------------------------------------------------------------------

CREATE TABLE elektrica.insurer_payment (
  id                    BIGSERIAL PRIMARY KEY,

  demand_id             BIGINT NOT NULL REFERENCES elektrica.demand (id),
  rental_id             BIGINT NOT NULL REFERENCES elektrica.rental (id),

  carrier_id            BIGINT NOT NULL REFERENCES platform.insurance_carrier (id),
  adjuster_id           BIGINT REFERENCES platform.adjuster (id),

  claim_ref             TEXT,  -- PLACEHOLDER, see header note -- no source exists for this yet

  vehicle_class         elektrica.vehicle_class,  -- from the demand's comparable_set, nullable
  rental_start_date     DATE,
  rental_end_date       DATE,

  market_rate_at_time   NUMERIC(10,2),   -- comparable_set.computed_average at resolution
  amount_demanded       NUMERIC(12,2) NOT NULL CHECK (amount_demanded >= 0),
  amount_paid           NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (amount_paid >= 0),
  days_to_resolve       INTEGER,         -- see header note; NULL if demand.sent_at was NULL

  resolved_at           TIMESTAMPTZ NOT NULL,

  source                elektrica.insurer_payment_source NOT NULL DEFAULT 'system',
  source_ref            TEXT,
  frozen                BOOLEAN NOT NULL DEFAULT true,

  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by            TEXT NOT NULL,

  CONSTRAINT insurer_payment_one_per_demand UNIQUE (demand_id),

  CONSTRAINT insurer_payment_source_ref_required_for_legacy
    CHECK (source <> 'legacy_import' OR source_ref IS NOT NULL)
);

CREATE INDEX idx_insurer_payment_carrier ON elektrica.insurer_payment (carrier_id);
CREATE INDEX idx_insurer_payment_adjuster ON elektrica.insurer_payment (adjuster_id);
CREATE INDEX idx_insurer_payment_vehicle_class ON elektrica.insurer_payment (vehicle_class);
CREATE INDEX idx_insurer_payment_resolved_at ON elektrica.insurer_payment (resolved_at);

GRANT SELECT, INSERT ON elektrica.insurer_payment TO elektrica_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA elektrica TO elektrica_app;

REVOKE UPDATE, DELETE ON elektrica.insurer_payment FROM PUBLIC;

CREATE OR REPLACE FUNCTION elektrica.insurer_payment_forbid_mutation()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'elektrica.insurer_payment is append-only/frozen: % is not permitted (id=%)', TG_OP, OLD.id;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_insurer_payment_forbid_update
  BEFORE UPDATE ON elektrica.insurer_payment
  FOR EACH ROW EXECUTE FUNCTION elektrica.insurer_payment_forbid_mutation();

CREATE TRIGGER trg_insurer_payment_forbid_delete
  BEFORE DELETE ON elektrica.insurer_payment
  FOR EACH ROW EXECUTE FUNCTION elektrica.insurer_payment_forbid_mutation();

-- ---------------------------------------------------------------------------
-- Automatic population: fires when a carrier-recipient demand resolves.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elektrica.demand_create_insurer_payment_on_resolve()
RETURNS TRIGGER AS $$
DECLARE
  v_amount_paid     NUMERIC(12,2);
  v_vehicle_class   elektrica.vehicle_class;
  v_market_rate     NUMERIC(10,2);
  v_rental_start    DATE;
  v_rental_end      DATE;
  v_days            INTEGER;
BEGIN
  IF NEW.status = 'resolved'
     AND OLD.status IS DISTINCT FROM 'resolved'
     AND NEW.recipient_type = 'carrier'
     AND NEW.carrier_id IS NOT NULL
  THEN
    SELECT COALESCE(SUM(amount), 0) INTO v_amount_paid
    FROM elektrica.payment WHERE demand_id = NEW.id;

    SELECT vehicle_class, computed_average INTO v_vehicle_class, v_market_rate
    FROM elektrica.comparable_set WHERE demand_id = NEW.id
    ORDER BY created_at DESC LIMIT 1;

    SELECT start_date, end_date INTO v_rental_start, v_rental_end
    FROM elektrica.rental WHERE id = NEW.rental_id;

    IF NEW.sent_at IS NOT NULL THEN
      v_days := EXTRACT(DAY FROM now() - NEW.sent_at)::INTEGER;
    END IF;

    INSERT INTO elektrica.insurer_payment (
      demand_id, rental_id, carrier_id, adjuster_id,
      vehicle_class, rental_start_date, rental_end_date,
      market_rate_at_time, amount_demanded, amount_paid,
      days_to_resolve, resolved_at, source, created_by
    ) VALUES (
      NEW.id, NEW.rental_id, NEW.carrier_id, NEW.adjuster_id,
      v_vehicle_class, v_rental_start, v_rental_end,
      v_market_rate, NEW.amount, v_amount_paid,
      v_days, now(), 'system', NEW.updated_by
    )
    ON CONFLICT (demand_id) DO NOTHING;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_demand_create_insurer_payment_on_resolve
  AFTER UPDATE ON elektrica.demand
  FOR EACH ROW EXECUTE FUNCTION elektrica.demand_create_insurer_payment_on_resolve();

-- ---------------------------------------------------------------------------
-- Exhibit view -- handoff §2.8: "filter by carrier, date range, vehicle
-- class -> exportable table for a demand or a JP filing." The filtering
-- itself is app-layer (repository.list_insurer_payments); this view just
-- pre-joins the carrier/adjuster names so a raw SQL export doesn't need
-- to repeat that join.
-- ---------------------------------------------------------------------------

CREATE VIEW elektrica.insurer_payment_exhibit AS
SELECT
  ip.id, ip.demand_id, ip.rental_id,
  ip.carrier_id, c.name AS carrier_name,
  ip.adjuster_id, a.name AS adjuster_name,
  ip.claim_ref, ip.vehicle_class,
  ip.rental_start_date, ip.rental_end_date,
  ip.market_rate_at_time, ip.amount_demanded, ip.amount_paid,
  ip.days_to_resolve, ip.resolved_at, ip.source, ip.frozen
FROM elektrica.insurer_payment ip
JOIN platform.insurance_carrier c ON c.id = ip.carrier_id
LEFT JOIN platform.adjuster a ON a.id = ip.adjuster_id;

GRANT SELECT ON elektrica.insurer_payment_exhibit TO elektrica_app;
