-- 011_elektrica_staff_user.sql
-- elektrica.staff_user — staff/role table, per hermes's relay of
-- shell-dashboard's ADR: the shell's launcher needs this to exist before
-- it can show an Elektrica door, matching the same shape VLS
-- (vls.staff_user, migration 005) and Collision (collision.staff_user,
-- migration 004) already use: id, person_id, google_email, role enum,
-- active flag.
--
-- FIELD PROVENANCE — read this before promoting:
--   - Table SHAPE (id, person_id, google_email, role, active,
--     provisioned_by, audit columns) is directly modeled on
--     vls.staff_user (read directly, VLS migration 005 — I have Jed's
--     standing clearance to read VLS schema/SQL) and
--     collision.staff_user (migration 004, same repo family, same
--     pattern). Confirmed-safe by precedent, not a guess.
--   - google_email DOMAIN restriction: elektricarentals.com. Sourced from
--     a real filename in ~/Downloads
--     ("certification-Texas-Dealer-Pre-License-Training-Course-
--     jed@elektricarentals.com.pdf") — an actual email address Jed uses,
--     not invented. Weaker evidence than VLS's domain (which came from a
--     direct source I have no record of, presumably a doc or Jed's own
--     statement) but real, not guessed — flagging the distinction rather
--     than overstating confidence.
--   - ROLE ENUM VALUES: PLACEHOLDER. No source document (ADR v2,
--     ELEKTRICA_HANDOFF, original-bot-plan.md) names Elektrica staff
--     roles the way Collision's ADR-001 named "owner/manager/
--     receptionist." The original bot's own open question #5
--     ("Single-user (Jed only) or will other staff need dashboard
--     access/logins in v1?") was never answered. Picking the minimal
--     two-value set (`owner`, `staff`) as a placeholder wide enough to
--     cover "Jed only" (one `owner` row) without assuming any particular
--     additional role names — corrected once Jed answers, per the same
--     discipline Collision's bot used for its own receptionist-permission
--     question (built the safe subset, deferred the real answer, logged
--     it as PENDING rather than guessed).
--
-- WHAT THIS MIGRATION DELIBERATELY DOES NOT DO (mirrors Collision
-- migration 004's own explicit scope limit):
--   - No RLS or route-guard logic scoped by role on elektrica.rental/
--     vehicle/demand/etc. — no backend exists yet to enforce it against.
--   - No decision about what each role can read/write — that's exactly
--     the open question logged as PENDING below.
--   - No provisioning of any real staff_user rows — this is schema only.

CREATE TYPE elektrica.staff_role AS ENUM (
  'owner',
  'staff'
);

CREATE TABLE elektrica.staff_user (
  id                BIGSERIAL PRIMARY KEY,
  person_id         BIGINT NOT NULL REFERENCES platform.person (id),

  role              elektrica.staff_role NOT NULL,

  -- Domain-restricted per the sourced evidence above. Application-layer
  -- Google Sign-In verification is the real enforcement point (same note
  -- as vls.staff_user's own comment); this CHECK is a defense-in-depth
  -- backstop, not the primary mechanism.
  google_email      TEXT NOT NULL UNIQUE,

  active            BOOLEAN NOT NULL DEFAULT true,

  -- Admin-provisioned, no self-signup, mirroring collision.staff_user's
  -- pattern exactly. Nullable to allow the bootstrap case (the very first
  -- row has no prior staff_user to reference).
  provisioned_by_staff_user_id BIGINT REFERENCES elektrica.staff_user (id),

  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by        TEXT NOT NULL,
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_by        TEXT NOT NULL,

  CONSTRAINT staff_user_one_row_per_person UNIQUE (person_id),

  CONSTRAINT staff_user_email_domain
    CHECK (google_email LIKE '%@elektricarentals.com')
);

CREATE INDEX idx_staff_user_person ON elektrica.staff_user (person_id);
CREATE INDEX idx_staff_user_role ON elektrica.staff_user (role);
CREATE INDEX idx_staff_user_active ON elektrica.staff_user (active) WHERE active;
CREATE INDEX idx_staff_user_email ON elektrica.staff_user (google_email) WHERE active = true;

CREATE OR REPLACE FUNCTION elektrica.staff_user_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_staff_user_set_updated_at
  BEFORE UPDATE ON elektrica.staff_user
  FOR EACH ROW EXECUTE FUNCTION elektrica.staff_user_set_updated_at();

-- elektrica_app reads this table to authorize requests (login lookup) but
-- provisioning (creating new staff rows) is an admin action outside
-- elektrica_app's normal request-handling privilege — same split VLS uses
-- (vls_app gets SELECT only on vls.staff_user). Collision's own
-- staff_user grant is broader (SELECT/INSERT/UPDATE to collision_app)
-- because Collision hadn't decided the provisioning boundary yet at that
-- point; matching VLS's tighter, already-decided pattern here since
-- nothing suggests Elektrica needs the looser one.
GRANT SELECT ON elektrica.staff_user TO elektrica_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA elektrica TO elektrica_app;
