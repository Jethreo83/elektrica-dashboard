-- 002_elektrica_vehicle.sql
--
-- ***************************************************************************
-- DO NOT PROMOTE TO PRODUCTION.
-- This migration contains PLACEHOLDER enum value sets pending the real Fleet
-- sheet export (blocked on Elektrica Google OAuth restoration — see
-- docs/BUILD_LOG.md). Apply and verify on staging only, per hermes/Jocasta's
-- 2026-09-03 instruction: make real progress on shape/wiring without
-- permanently committing to guessed column names. Re-derive this file once
-- the export lands and the real class / status / tracking_system values are
-- confirmed, THEN promote.
-- ***************************************************************************
--
-- CONFIRMED BY JED (2026-09-03): vehicle.class and vehicle.tracking_system
-- are real columns on the Fleet sheet tabs — their EXISTENCE is confirmed,
-- not a front-end-computed guess. Their exact enum value sets below are
-- NOT confirmed — placeholder, taken from handoff prose only.

CREATE TYPE elektrica.vehicle_class AS ENUM (
  'ev',
  'gas',
  'suv',
  'truck',
  'sedan',
  'van',
  'other'
);

CREATE TYPE elektrica.vehicle_status AS ENUM (
  'available',
  'out',
  'maintenance',
  'retired'
);

-- PLACEHOLDER value set, taken verbatim from handoff §2.3's parenthetical
-- ("bouncie | standard_fleet | geofence_email | none").
CREATE TYPE elektrica.tracking_system AS ENUM (
  'bouncie',
  'standard_fleet',
  'geofence_email',
  'none'
);

CREATE TABLE elektrica.vehicle (
  id                BIGSERIAL PRIMARY KEY,

  vin               TEXT NOT NULL UNIQUE,

  -- CONFIRMED real column — enum values PLACEHOLDER, see banner above.
  class             elektrica.vehicle_class,
  status            elektrica.vehicle_status NOT NULL DEFAULT 'available',

  -- CONFIRMED real column — enum values PLACEHOLDER. Nullable: not every
  -- vehicle has tracking installed; whether the real sheet encodes "no
  -- tracking" as 'none' or a blank cell needs the export to settle.
  tracking_system   elektrica.tracking_system,

  -- Bot-maintained, non-legal per handoff §2.3 ("current known position").
  -- Written only by the future rental-operations bot's proposal flow
  -- (§1.7), never a source of legal truth.
  current_position    JSONB,
  position_updated_at TIMESTAMPTZ,

  notes             TEXT,

  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by        TEXT NOT NULL,
  updated_by        TEXT NOT NULL
);

CREATE INDEX idx_vehicle_status ON elektrica.vehicle (status);
CREATE INDEX idx_vehicle_class ON elektrica.vehicle (class);

-- elektrica_app already has SELECT/INSERT/UPDATE ON ALL TABLES IN SCHEMA
-- elektrica from migration 001's blanket grant, which covers this new table
-- retroactively (Postgres re-evaluates ALL TABLES grants dynamically —
-- actually: ALL TABLES IN SCHEMA is a snapshot at GRANT time in Postgres,
-- NOT dynamic. Re-granting explicitly here to be correct rather than assume).
GRANT SELECT, INSERT, UPDATE ON elektrica.vehicle TO elektrica_app;
