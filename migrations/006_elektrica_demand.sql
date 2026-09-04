-- 006_elektrica_demand.sql
-- elektrica.demand + elektrica.comparable_set — handoff §2.3/§2.8's demand
-- object and its frozen market-comparable snapshot. `document` (migration
-- 005) becomes a real caller here: a demand's `generated_document_id`
-- points at the document row produced for it.
--
-- FIELD PROVENANCE:
--   demand: rental_id, demand_type (primary_insurer | uim |
--   balance_to_renter — literal enum from handoff §2.3), recipient
--   (carrier+adjuster or renter), amount, generated_document_id, sent_via,
--   sent_at, status, and the shortfall-pre-fill chain ("The shortfall from
--   a resolved earlier demand pre-fills the next") are all handoff-literal.
--   `status`'s exact value set is NOT given verbatim in the handoff (it
--   only says "each has its own lifecycle") — PLACEHOLDER enum inferred
--   from the rental lifecycle's own vocabulary, marked as such below.
--   carrier_name/adjuster_name are PLACEHOLDER free text: no
--   insurance_carrier/adjuster tables exist yet (ADR build order step 8,
--   blocked on the same real-Sheet-export dependency as elektrica.vehicle
--   — see docs/OVERNIGHT_DECISIONS.md). Not inventing carrier/adjuster
--   tables tonight; recipient identity here is just enough to make demand
--   usable, corrected once those tables exist.
--
--   comparable_set: scan source, scan timestamp, vehicle class, date
--   range, each comparable (vendor, vehicle, daily rate), computed
--   average — all handoff-literal (§2.8). "Immutable once the demand is
--   generated" implemented as immutable from creation (a comparable_set is
--   created as part of generating a demand, not before).

CREATE TYPE elektrica.demand_type AS ENUM (
  'primary_insurer',
  'uim',
  'balance_to_renter'
);

CREATE TYPE elektrica.demand_recipient_type AS ENUM ('carrier', 'renter');

-- PLACEHOLDER value set — the handoff says "each has its own lifecycle"
-- but does not enumerate states. Inferred from the rental lifecycle's own
-- vocabulary (handoff §2.4) for consistency, not a literal quote. Revisit
-- once Jed describes a demand's actual states, same discipline as the
-- vehicle enums.
CREATE TYPE elektrica.demand_status AS ENUM (
  'draft',
  'sent',
  'negotiating',
  'no_offer',
  'accepted',
  'resolved'
);

-- ---------------------------------------------------------------------------
-- elektrica.demand
-- ---------------------------------------------------------------------------

CREATE TABLE elektrica.demand (
  id                      BIGSERIAL PRIMARY KEY,
  rental_id               BIGINT NOT NULL REFERENCES elektrica.rental (id),

  demand_type             elektrica.demand_type NOT NULL,
  recipient_type          elektrica.demand_recipient_type NOT NULL,

  -- PLACEHOLDER free text pending insurance_carrier/adjuster tables (ADR
  -- build order step 8). Required only when recipient_type = 'carrier';
  -- when recipient_type = 'renter' the recipient IS the rental's own
  -- renter_id, no separate field needed.
  carrier_name            TEXT,
  adjuster_name           TEXT,

  amount                  NUMERIC(12,2) NOT NULL CHECK (amount >= 0),

  generated_document_id   BIGINT REFERENCES elektrica.document (id),
  sent_via                elektrica.outbound_channel,
  sent_at                 TIMESTAMPTZ,

  status                  elektrica.demand_status NOT NULL DEFAULT 'draft',

  -- "The shortfall from a resolved earlier demand pre-fills the next" —
  -- self-referencing chain, one demand per rental can point at its
  -- predecessor. Pre-filling logic itself is application-layer; this
  -- column just records the linkage so it CAN be queried/pre-filled from.
  prior_demand_id         BIGINT REFERENCES elektrica.demand (id),

  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by              TEXT NOT NULL,
  updated_by              TEXT NOT NULL,

  CONSTRAINT demand_carrier_name_required_for_carrier_recipient
    CHECK (recipient_type <> 'carrier' OR carrier_name IS NOT NULL),

  -- Only claim: a draft demand has no send record yet. Does NOT require
  -- sent_via/sent_at once non-draft (a demand can sit in 'negotiating'
  -- etc. without re-writing those columns) — a real send-completeness
  -- rule can tighten this once the document-generation flow is wired to
  -- write demand rows, not before.
  CONSTRAINT demand_draft_has_no_send_record
    CHECK (status <> 'draft' OR (sent_via IS NULL AND sent_at IS NULL)),

  CONSTRAINT demand_prior_not_self CHECK (prior_demand_id IS NULL OR prior_demand_id <> id)
);

CREATE INDEX idx_demand_rental ON elektrica.demand (rental_id);
CREATE INDEX idx_demand_status ON elektrica.demand (status);
CREATE INDEX idx_demand_prior ON elektrica.demand (prior_demand_id);

GRANT SELECT, INSERT, UPDATE ON elektrica.demand TO elektrica_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA elektrica TO elektrica_app;

CREATE OR REPLACE FUNCTION elektrica.demand_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_demand_set_updated_at
  BEFORE UPDATE ON elektrica.demand
  FOR EACH ROW EXECUTE FUNCTION elektrica.demand_set_updated_at();

-- ---------------------------------------------------------------------------
-- elektrica.comparable_set — frozen per demand, immutable from creation.
-- ---------------------------------------------------------------------------

CREATE TABLE elektrica.comparable_set (
  id                BIGSERIAL PRIMARY KEY,
  demand_id         BIGINT NOT NULL REFERENCES elektrica.demand (id),

  scan_source       TEXT NOT NULL,           -- e.g. 'kayak' — bot-side scraper per E-3, free text since the scanner itself is future work
  scan_timestamp    TIMESTAMPTZ NOT NULL,

  -- Reuses elektrica.vehicle_class (migration 002) — inherits that enum's
  -- own placeholder status. Nullable: a comparable set can predate a
  -- vehicle-class-aware scan.
  vehicle_class     elektrica.vehicle_class,

  date_range_start  DATE NOT NULL,
  date_range_end    DATE NOT NULL,

  -- Each comparable: {vendor, vehicle, daily_rate}. Array shape kept as
  -- JSONB rather than a child table — a comparable_set is generated and
  -- frozen atomically, never queried/joined comparable-by-comparable.
  comparables       JSONB NOT NULL,
  computed_average  NUMERIC(10,2) NOT NULL CHECK (computed_average >= 0),

  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by        TEXT NOT NULL,

  CONSTRAINT comparable_set_date_range_valid CHECK (date_range_end >= date_range_start)
);

CREATE INDEX idx_comparable_set_demand ON elektrica.comparable_set (demand_id);

GRANT SELECT, INSERT ON elektrica.comparable_set TO elektrica_app;

-- Immutable once created — "frozen per demand" per handoff §2.8, same
-- append-only philosophy as elektrica.document.
REVOKE DELETE, UPDATE ON elektrica.comparable_set FROM PUBLIC;

CREATE OR REPLACE FUNCTION elektrica.comparable_set_forbid_mutation()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'elektrica.comparable_set is frozen once created: % is not permitted (id=%)', TG_OP, OLD.id;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_comparable_set_forbid_delete
  BEFORE DELETE ON elektrica.comparable_set
  FOR EACH ROW EXECUTE FUNCTION elektrica.comparable_set_forbid_mutation();

CREATE TRIGGER trg_comparable_set_forbid_update
  BEFORE UPDATE ON elektrica.comparable_set
  FOR EACH ROW EXECUTE FUNCTION elektrica.comparable_set_forbid_mutation();

-- ---------------------------------------------------------------------------
-- Aging surface — "a demand at 45 days with no offer" per handoff §2.4:
-- "Aging surfaces itself ... Silence is the signal." Implemented as a
-- query, same philosophy as vls.blocked_cases / elektrica.blocked_rentals.
-- ---------------------------------------------------------------------------

CREATE VIEW elektrica.aging_demands AS
SELECT id, rental_id, demand_type, status, sent_at,
       EXTRACT(DAY FROM now() - sent_at)::INTEGER AS days_since_sent
FROM elektrica.demand
WHERE status IN ('sent', 'negotiating', 'no_offer')
  AND sent_at IS NOT NULL
  AND now() - sent_at > INTERVAL '45 days';

GRANT SELECT ON elektrica.aging_demands TO elektrica_app;
