-- 014_elektrica_demand_carrier_fk.sql
-- Wires elektrica.demand's recipient identity to the real
-- platform.insurance_carrier/platform.adjuster tables (migration 013),
-- replacing the PLACEHOLDER free-text carrier_name/adjuster_name columns
-- migration 006 explicitly flagged as temporary ("no
-- insurance_carrier/adjuster tables exist yet"). This is the concrete
-- "next up" item logged at the end of BUILD_LOG.md's migration-013
-- entry and docs/BACKLOG.md's carrier-wiring note.
--
-- STAGING-ONLY, same as elektrica.demand itself (migration 006 was never
-- promoted to production -- see README.md's "Schema — staging only"
-- section) -- this migration inherits that status mechanically via its
-- FK dependency on elektrica.demand, and is itself new schema Jed has
-- not reviewed. Not touching production.
--
-- WHY A REAL COLUMN SWAP, NOT AN ADDITIVE MIGRATION: BUILD_LOG.md's own
-- migration-013 entry flagged this as "a real schema change to an
-- existing table with a CHECK constraint tying into it" needing its own
-- migration. Every existing elektrica.demand row is test-harness/
-- smoke-test data (see verify_006.sql, scripts/_smoke_repository.py,
-- test_api.py's _sample_demand()), not real customer data -- but staging
-- already has live smoke rows (e.g. carrier_name='Acme Insurance',
-- 'Role Smoke Insurance' from prior cycles' smoke runs) that would
-- violate the new NOT-NULL-equivalent carrier_id CHECK if the columns
-- were just dropped outright. Rather than silently losing/orphaning
-- those rows, this migration backfills: for each distinct existing
-- carrier_name value, find-or-create a matching platform.insurance_carrier
-- row (by exact name match -- same simple matching a migration script
-- can safely do; the app layer's real
-- find_insurance_carrier_by_name_or_alias also checks aliases, not
-- needed here since these are fresh smoke-test carrier names with no
-- alias history), then points each demand row's new carrier_id at it.
-- adjuster_name was never actually populated by any smoke run to date
-- (checked before writing this migration), so adjuster_id backfill has
-- nothing to do -- it stays NULL for existing rows, which is valid
-- (adjuster_id is nullable; only carrier_id is required when
-- recipient_type='carrier').
--
-- NEW INVARIANT NOT PRESENT BEFORE: an adjuster_id, if set, must belong
-- to the SAME carrier as the demand's own carrier_id (platform.adjuster
-- rows are carrier-scoped by migration 013's own
-- adjuster_name_unique_per_carrier constraint) -- a demand naming an
-- adjuster who works for a different carrier than the one the demand is
-- being sent to is a data-entry error, not a valid state. Enforced by
-- trigger below since a bare CHECK/FK cannot express a cross-table
-- column-equality constraint.

-- ---------------------------------------------------------------------------
-- New FK columns.
-- ---------------------------------------------------------------------------

ALTER TABLE elektrica.demand
  ADD COLUMN carrier_id BIGINT REFERENCES platform.insurance_carrier (id),
  ADD COLUMN adjuster_id BIGINT REFERENCES platform.adjuster (id);

CREATE INDEX idx_demand_carrier ON elektrica.demand (carrier_id);
CREATE INDEX idx_demand_adjuster ON elektrica.demand (adjuster_id);

-- ---------------------------------------------------------------------------
-- Backfill: create/match a platform.insurance_carrier row for every
-- distinct existing carrier_name, then point carrier_id at it. Exact
-- name match only (see header comment above for why alias matching
-- isn't needed here). created_by/updated_by = 'migration_014_backfill'
-- so these synthesized carrier rows are identifiable later as
-- migration-generated rather than hand-entered.
-- ---------------------------------------------------------------------------

INSERT INTO platform.insurance_carrier (name, created_by, updated_by)
SELECT DISTINCT d.carrier_name, 'migration_014_backfill', 'migration_014_backfill'
FROM elektrica.demand d
WHERE d.carrier_name IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM platform.insurance_carrier c WHERE c.name = d.carrier_name
  );

UPDATE elektrica.demand d
SET carrier_id = c.id
FROM platform.insurance_carrier c
WHERE d.carrier_name IS NOT NULL AND c.name = d.carrier_name;

-- ---------------------------------------------------------------------------
-- Replace the old free-text-based CHECK with the FK-based equivalent,
-- then drop the placeholder columns themselves.
-- ---------------------------------------------------------------------------

ALTER TABLE elektrica.demand
  DROP CONSTRAINT demand_carrier_name_required_for_carrier_recipient;

ALTER TABLE elektrica.demand
  ADD CONSTRAINT demand_carrier_required_for_carrier_recipient
    CHECK (recipient_type <> 'carrier' OR carrier_id IS NOT NULL);

ALTER TABLE elektrica.demand
  DROP COLUMN carrier_name,
  DROP COLUMN adjuster_name;

-- ---------------------------------------------------------------------------
-- Cross-table invariant: adjuster_id, if set, must belong to carrier_id.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elektrica.demand_check_adjuster_carrier_match()
RETURNS TRIGGER AS $$
DECLARE
  v_adjuster_carrier_id BIGINT;
BEGIN
  IF NEW.adjuster_id IS NOT NULL THEN
    SELECT carrier_id INTO v_adjuster_carrier_id
    FROM platform.adjuster WHERE id = NEW.adjuster_id;

    IF v_adjuster_carrier_id IS DISTINCT FROM NEW.carrier_id THEN
      RAISE EXCEPTION
        'demand.adjuster_id % belongs to carrier_id % but demand.carrier_id is % -- adjuster must belong to the same carrier the demand is addressed to.',
        NEW.adjuster_id, v_adjuster_carrier_id, NEW.carrier_id;
    END IF;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_demand_check_adjuster_carrier_match
  BEFORE INSERT OR UPDATE ON elektrica.demand
  FOR EACH ROW EXECUTE FUNCTION elektrica.demand_check_adjuster_carrier_match();

-- ---------------------------------------------------------------------------
-- No new grants needed: elektrica_app already has SELECT/INSERT/UPDATE on
-- elektrica.demand (migration 006) and SELECT on
-- platform.insurance_carrier/platform.adjuster (migration 013) -- FK
-- validation at INSERT/UPDATE time reads the referenced row under the
-- inserting role's own privileges, and SELECT is exactly what's needed
-- and already granted.
-- ---------------------------------------------------------------------------
