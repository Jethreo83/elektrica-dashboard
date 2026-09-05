-- 013_platform_insurance_carrier.sql
-- platform.insurance_carrier + platform.adjuster -- handoff §1.4
-- ("Canonical carrier record: name, aliases, fax, email, phone,
-- claims-mailing conventions. Shared between VLS and Elektrica Rentals.
-- Adjuster records hang off carriers") and §2.8 ("adjuster: carrier_id,
-- name, contact, notes; outcomes roll up (settles at market / lowballs /
-- forces suit)").
--
-- WHAT THIS IS NOT: this is NOT the historical insurer-payment import
-- (handoff §2.9) -- that stays genuinely blocked on Kay's Elektrica
-- Google OAuth restoration (docs/OVERNIGHT_DECISIONS.md's open BLOCKER
-- entry, unchanged). This migration is the CARRIER/ADJUSTER SCHEMA ONLY,
-- which the handoff itself describes in full literal detail independent
-- of any Sheet export -- Jed already confirmed (ADR-001 v2 section 2)
-- that "a real insurance contact list exists (fax, phone, address,
-- email)" as the seed data for exactly this table; only the *rows* from
-- that list require export/inspection before import, not the *shape* of
-- the table that will hold them. Same distinction ADR-001 v2's own build
-- order draws between step 1 (export/inspect, blocked) and step 8
-- (insurer_payment + adjuster schema, not itself blocked by the export --
-- only the historical BACKFILL of insurer_payment is). Building the
-- carrier/adjuster shape now unblocks elektrica.demand's carrier_id/
-- adjuster_id wiring (see docs/BACKLOG.md) without waiting on the export.
--
-- PLACEMENT: platform.*, not elektrica.*, per handoff §1.4's explicit
-- "Shared between VLS and Elektrica Rentals" and SHARED_CONVENTIONS
-- convention #2's discipline (build shared infra directly in its shared
-- home from day one -- migration 009's document-generator relocation and
-- migration 010's platform.communication both already did this; no
-- reason to repeat the "build in elektrica for now" mistake a third time).
-- vls_app is NOT granted here -- same "grant when there's a real caller"
-- discipline as every other cross-schema grant in this repo (migration
-- 009/010's own header comments). VLS has no carrier-referencing table
-- yet to justify the grant.
--
-- FIELD PROVENANCE:
--   insurance_carrier: name, aliases, fax, email, phone,
--   claims_mailing_address -- all handoff-literal (§1.4's own field list,
--   "fax, email, phone, claims-mailing conventions"). `aliases` as a
--   TEXT[] directly implements handoff §2.9.2's "Carrier names collapse
--   to canonical insurance_carrier records" -- the alias list IS the
--   collapse mechanism, not a guess.
--   adjuster: carrier_id, name, contact (split into phone/email, same
--   convention as every other contact field in this repo rather than one
--   freeform "contact" column), notes -- all handoff-literal (§2.8's own
--   field list). "Outcomes roll up" is explicitly NOT a stored column
--   here -- it is a derived query over elektrica.demand/insurer_payment
--   once insurer_payment exists (handoff's own wording: outcomes "roll
--   up", i.e. computed, not entered). No outcome column invented.

CREATE TABLE platform.insurance_carrier (
  id                      BIGSERIAL PRIMARY KEY,

  name                    TEXT NOT NULL,
  aliases                 TEXT[] NOT NULL DEFAULT '{}',

  fax                     TEXT,
  email                   TEXT,
  phone                   TEXT,
  claims_mailing_address  TEXT,

  notes                   TEXT,

  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by              TEXT NOT NULL,
  updated_by              TEXT NOT NULL,

  -- Canonical name is unique -- this IS the "collapse to canonical
  -- record" mechanism handoff §2.9.2 describes; variant names go in
  -- `aliases`, not a second row.
  CONSTRAINT insurance_carrier_name_unique UNIQUE (name)
);

CREATE INDEX idx_insurance_carrier_aliases ON platform.insurance_carrier USING GIN (aliases);

CREATE TABLE platform.adjuster (
  id                BIGSERIAL PRIMARY KEY,
  carrier_id        BIGINT NOT NULL REFERENCES platform.insurance_carrier (id),

  name              TEXT NOT NULL,
  phone             TEXT,
  email             TEXT,
  notes             TEXT,

  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by        TEXT NOT NULL,
  updated_by        TEXT NOT NULL,

  -- Same adjuster name can recur at a different carrier (people move
  -- employers) but not twice at the same carrier -- that's a data-entry
  -- duplicate, not two real adjusters.
  CONSTRAINT adjuster_name_unique_per_carrier UNIQUE (carrier_id, name)
);

CREATE INDEX idx_adjuster_carrier ON platform.adjuster (carrier_id);

-- ---------------------------------------------------------------------------
-- updated_at maintenance -- same trigger shape as every other mutable
-- table in this repo (elektrica.demand, elektrica.vehicle, etc.).
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION platform.insurance_carrier_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_insurance_carrier_set_updated_at
  BEFORE UPDATE ON platform.insurance_carrier
  FOR EACH ROW EXECUTE FUNCTION platform.insurance_carrier_set_updated_at();

CREATE OR REPLACE FUNCTION platform.adjuster_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_adjuster_set_updated_at
  BEFORE UPDATE ON platform.adjuster
  FOR EACH ROW EXECUTE FUNCTION platform.adjuster_set_updated_at();

-- ---------------------------------------------------------------------------
-- Grants -- elektrica_app is the only real caller today. SELECT/INSERT/
-- UPDATE (not DELETE): carrier/adjuster records get corrected (a fax
-- number changes, an alias gets added) but are never deleted -- a wrong
-- carrier record found later is fixed in place, not removed, since
-- elektrica.demand rows may already exist referencing it once the FK
-- wiring (docs/BACKLOG.md) lands. Same DELETE-omission discipline as
-- platform.communication (migration 010).
-- ---------------------------------------------------------------------------

GRANT USAGE ON SCHEMA platform TO elektrica_app;
GRANT SELECT, INSERT, UPDATE ON platform.insurance_carrier TO elektrica_app;
GRANT SELECT, INSERT, UPDATE ON platform.adjuster TO elektrica_app;
GRANT USAGE, SELECT ON platform.insurance_carrier_id_seq TO elektrica_app;
GRANT USAGE, SELECT ON platform.adjuster_id_seq TO elektrica_app;
