-- 015_elektrica_vehicle_drop_class_tracking.sql
-- Drops elektrica.vehicle.class and elektrica.vehicle.tracking_system,
-- per Jed's direct answer (2026-09-04, relayed by hermes) to the
-- discrepancy flagged in docs/OVERNIGHT_DECISIONS.md: "they don't exist
-- as separate columns in the real data. Drop them from elektrica.vehicle's
-- schema as designed -- derive/infer them differently if the app layer
-- needs that info (e.g. computed from make/model, or a separate lookup),
-- rather than storing them as their own columns sourced from a Sheet
-- field that doesn't exist."
--
-- This CLOSES the discrepancy logged in docs/OVERNIGHT_DECISIONS.md's
-- "Real Fleet / Rental Management Sheet exports landed" entry -- Kay's
-- real export confirmed the real Fleet info tab's columns are Year,
-- Make, Model, Nickname, VIN, Plate, Miles, Toll Tag, Owner, Lender,
-- Ownership Type. No class or tracking_system column exists there.
--
-- WHY A NEW MIGRATION, NOT AN EDIT TO 002: migration 002 has never been
-- edited since its initial commit (confirmed via git log --follow before
-- writing this) -- same discipline as migration 012's fix-not-a-feature
-- pattern and migration 014's real-column-swap-with-its-own-migration
-- pattern. elektrica.vehicle was never promoted to production (confirmed:
-- production's elektrica schema has only renter and staff_user as of
-- this migration), so there is no real customer data to preserve or
-- migrate off of these columns -- any existing rows are test-harness/
-- smoke-test data from verify_002.sql and scripts/_smoke_repository.py.
--
-- SEPARATE FINDING, NOT ACTED ON HERE (flagged in docs/BUILD_LOG.md
-- instead): the real Fleet info tab also has Year, Make, Model, Nickname,
-- Plate, Miles, Toll Tag, Owner, Lender, Ownership Type columns that
-- elektrica.vehicle does NOT currently have at all. Jed's instruction was
-- specifically to drop class/tracking_system, not to add the other real
-- columns -- adding those now would be scope creep beyond what was
-- actually decided. Logged as a separate open question, not silently
-- bundled into this migration.
--
-- WHAT ABOUT elektrica.comparable_set.vehicle_class (migration 006)?
-- That column is NOT dropped or touched here. It was never sourced from
-- elektrica.vehicle.class via FK -- it's a market-rate-comparable
-- classification (handoff §2.8: "vehicle class, date range" for the
-- Kayak-style rate scan), populated directly by whatever creates the
-- comparable_set row, independent of any per-vehicle Fleet-sheet record.
-- Jed's "derive/infer differently" instruction is exactly what
-- comparable_set already does -- it never depended on vehicle.class
-- existing as a stored column in the first place. elektrica.vehicle_class
-- the ENUM TYPE stays (still used by comparable_set); only
-- elektrica.vehicle.class the COLUMN and elektrica.tracking_system the
-- TYPE (used nowhere except the dropped column) go away.

-- ---------------------------------------------------------------------------
-- Drop the columns. No backfill/data-preservation logic needed --
-- elektrica.vehicle was never promoted to production (verified above),
-- so every existing row anywhere (staging only) is test/smoke data.
-- ---------------------------------------------------------------------------

DROP INDEX IF EXISTS elektrica.idx_vehicle_class;

ALTER TABLE elektrica.vehicle
  DROP COLUMN class,
  DROP COLUMN tracking_system;

-- ---------------------------------------------------------------------------
-- elektrica.tracking_system is now unused anywhere in the schema (the
-- only column that used it was just dropped) -- drop the type too, so a
-- future migration doesn't accidentally resurrect it by reusing the name
-- for something unrelated. elektrica.vehicle_class stays: it's still in
-- active use by elektrica.comparable_set.vehicle_class.
-- ---------------------------------------------------------------------------

DROP TYPE elektrica.tracking_system;
