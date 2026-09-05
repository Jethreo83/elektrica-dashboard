# Backlog — decided, not yet actionable

Items Jed has already decided but that don't need schema/code changes
right now (no dependency exists yet to hang them off of). Check this
file whenever touching the area it names — don't rediscover the decision
from scratch or, worse, do it differently by accident.

---

## RESOLVED 2026-09-05 (cron cycle, later) — email/phone normalization utility built

**What:** the entry directly below this one (same date, earlier cycle)
flagged that no email/phone normalization utility existed before calling
`platform.match_or_create_person()`. Closed this cycle by
`app/normalize.py` (`normalize_email()`, `normalize_phone()`), wired into
`POST /renters/intake` (`app/api.py`). See `docs/BUILD_LOG.md`'s matching
entry for the full writeup (scope decision -- kept Elektrica-local, not
extracted to `platform.*`, since Collision's inline email-only version
doesn't count as a second real consumer of the phone half; 12 new
`test_normalize.py` cases; live HTTP verification against real staging
proving a mixed-case email and a punctuated phone both correctly attach
to the same `platform.person` instead of creating a duplicate).

**Still open:** phone format is UNCONFIRMED against real data (every
`platform.person` row on staging has `phone_normalized IS NULL`) --
`normalize_phone()` strips to digits-only with NO US country-code
stripping, flagged in the module's own docstring as an assumption Jed
should confirm once real phone data exists to check it against.

---

## NEW 2026-09-05 (cron cycle) — no email/phone normalization utility exists

**What:** `platform.match_or_create_person()`'s exact-match step does a
literal string-equality comparison against `platform.person.email_normalized`/
`phone_normalized` — those columns are already normalized at rest
(lowercased email, presumably digit-only phone), but nothing in this
codebase normalizes an INCOMING value before passing it in. The new
`POST /renters/intake` route (handoff §2.2 step 1, built this cycle —
see `docs/BUILD_LOG.md`) passes JotForm-submitted email/phone straight
through unmodified.

**Why this matters:** a real JotForm submission with `Jane@Example.com`
or a phone number with dashes/parens will silently fail to match an
existing `Jane@example.com`/digit-only phone row and create a DUPLICATE
`platform.person` — the exact failure mode `match_or_create_person()`
exists to prevent, just moved one layer up to a normalization gap
instead of a matching-logic gap.

**What to do when this is next touched:** write one shared normalization
function (lowercase+strip email; strip non-digits from phone, matching
whatever format `platform.person.phone_normalized` actually uses today —
check real staging rows before guessing the format) and call it from
`POST /renters/intake` before passing values to
`repo.match_or_create_and_link_renter()`. Given convention #1/#2 in this
codebase (shared primitives live in `platform.*`, not duplicated
per-project), check whether VLS/Collision already normalize inline
before their own person-matching calls — if so, this should become a
shared `platform` helper, not an Elektrica-local one, same lesson as the
document-generator placement correction (`docs/OVERNIGHT_DECISIONS.md`,
2026-09-04).

**Not urgent — no action needed until:** a real JotForm webhook is wired
to this route (still manual/API-only today) or Jed reports a duplicate-
person symptom that traces back to this.

---

## RESOLVED 2026-09-05 (cron cycle) — elektrica.demand carrier/adjuster FK wiring

**What:** `docs/BUILD_LOG.md`'s migration-013 entry flagged
`elektrica.demand.carrier_name`/`adjuster_name` (migration 006 PLACEHOLDER
free text) as the natural next item to wire to `platform.insurance_carrier`/
`platform.adjuster` (migration 013) once those tables existed. Closed
this cycle by `migrations/014_elektrica_demand_carrier_fk.sql` — see
`docs/BUILD_LOG.md`'s matching entry for the full writeup (backfill,
new cross-carrier adjuster-match trigger, app-layer changes, 140/140
tests, live HTTP verification against real staging). Nothing further to
do here; kept as a resolved marker so a future session doesn't rediscover
this as still-open.

---

## Staff provisioning must create/link a `platform.person` row (Jed, 2026-09-04, relayed by hermes)

**Decision:** staff provisioning should create (or match-and-link) a
`platform.person` row the same way renter/client/customer provisioning
already does — convention #1 consistency ("every party table keyed by
`person_id`, staff included"). Same decision relayed to VLS and
Collision, so this is a house-wide pattern, not Elektrica-specific.

**Current state:** `elektrica.staff_user.person_id` is already `NOT NULL
REFERENCES platform.person (id)` (migration 011) — the schema already
requires a valid person link, so this isn't a structural gap. What's not
yet decided/built is the *provisioning workflow* itself: no backend/API
exists yet (data layer first, per this build's standing discipline), so
there is no actual "create a staff member" code path today for this
decision to change.

**UPDATE 2026-09-04, later:** the mechanism to use is now real and
verified, not a future design intent — `platform.match_or_create_person()`
(vls-dashboard migration 008, tag `vls-migration-008-person-match`),
live on both staging and production. Read directly (VLS schema, clearance
already established): implements the match-phone/email-first,
then-name+DOB rule exactly (`vls-domain-rules` §10) — exact match
attaches, close match (same last_name + non-null matching DOB) queues to
`platform.person_match_queue` for a human confirm-or-split, no match
creates new. Returns `(person_id, match_status, queue_id)` where
`match_status` is `attached` | `queued` | `created`. Callable only via
`platform_identity_service` (`SECURITY DEFINER`, `REVOKE ALL ... GRANT
EXECUTE ... TO platform_identity_service` — `elektrica_app` has no direct
grant, by design, same split as everywhere else in this schema).

**What to do when staff provisioning is actually built:** call
`platform.match_or_create_person()` through `platform_identity_service` —
do NOT write custom matching logic in Elektrica's own backend, even
something that looks simpler. This is now explicitly the same kind of
shared primitive as the document generator (convention #2) — writing a
project-local version of it would repeat that exact mistake. If
`match_status = 'queued'`, the caller must NOT treat the returned
`person_id` as linked yet — staff provisioning should surface the queue
row for human resolution, not silently attach.

**Not urgent — no action needed until:** a staff-provisioning
API/admin-action is actually being built. Then read this entry first.

---

## `platform.match_or_create_person()` applies to renter provisioning too, not just staff

**What:** Jed/hermes's note about the new shared identity-match primitive
(`platform.match_or_create_person()`, vls-dashboard migration 008) was
delivered in the context of the staff-provisioning backlog item above,
but the function is convention #1 shared infrastructure for EVERY party
table, not staff-specific — this applies equally to `elektrica.renter`
provisioning (handoff §2.2's JotForm intake flow).

**Current state:** no renter-provisioning backend/API exists yet either
(same "data layer first" reason as staff provisioning) — nothing to
retrofit today. But when the JotForm intake handler is eventually built
(handoff §2.2 step 1: "Renter completes a JotForm ... Auto-creates a
Drive folder"), it must call `platform.match_or_create_person()` through
`platform_identity_service` for the renter's identity, not write its own
matching logic or blindly INSERT into `platform.person`.

**Not urgent — no action needed until:** the JotForm intake handler or
any other renter-creation code path is actually being built. Then read
this entry (and the staff one above) first.

**UPDATE 2026-09-04:** the first app-layer code landed (`app/repository.py`,
migration-agnostic session) already anticipated this correctly —
`create_renter_for_existing_person()` and
`provision_staff_user_for_existing_person()` both take an already-resolved
`person_id` as input rather than doing any matching themselves, with
their own docstrings pointing back to this file. Identity resolution
(i.e. the actual `platform.match_or_create_person()` call) is deferred to
whatever calls these functions — correctly not baked into either one.
Nothing to fix; just noting the pattern held before this entry was even
fully written.

---

## RESOLVED 2026-09-04 (cron cycle) — Staff-provisioning HTTP route gap closed

**What:** the staff-provisioning backlog item above (and BUILD_LOG.md's
"not done / explicitly deferred" list from the previous cycle) both
flagged that `provision_staff_user_for_existing_person()` /
`get_staff_user_by_google_email()` existed in `app/repository.py` but had
no HTTP route. Closed this cycle, mirroring Complete Collision's
identical route family exactly (same repo convention):

- `app/repository.py`: added `set_staff_user_active()` (the third
  function Collision's equivalent route family needed; Elektrica had no
  counterpart until now). No `get_staff_capability()` equivalent added —
  Elektrica's role set is a flat `owner`/`staff` split, CONFIRMED FINAL
  by Jed with no further granularity (migration 011), so there is no
  capability-lookup function to expose; this is a real scope difference
  from Collision, not a gap.
- `app/api.py`: `POST /staff`, `GET /staff/{google_email}`,
  `POST /staff/{google_email}/active`. Deliberately does NOT expose a
  route that creates a new `platform.person` row — per this file's own
  entries above, that must go through `platform.match_or_create_person()`
  via `platform_identity_service`, not a bespoke INSERT here.
- Tests: 6 new mocked `test_api.py` cases (36/36 total now), including a
  domain-rejection case confirming `StaffUser.__post_init__`'s ValueError
  surfaces as 400, not 500.
- Live-verified against real staging (`neondb_owner` connection, per the
  documented `elektrica_app` SELECT-only role gap on `staff_user`): ran
  uvicorn, provisioned a real staff_user (person_id=11,
  `smoke.staff@elektricarentals.com`), read it back, deactivated it,
  confirmed a 404 for an unknown email, a 400 for a bad role enum value,
  and a 400 (not 500) for a wrong-domain email. Process killed after.
  Staging residue left intentionally (same append-only-adjacent
  reasoning as every other smoke run in this repo): `staff_user` id=1,
  `platform.person` id=11.

**Still open, not touched this cycle:** the route family has no
auth/session layer (same standing gap as every other route in
`app/api.py`, flagged in that file's own module docstring) — provisioning
a real staff member through this route today requires the same
privileged, non-`elektrica_app` connection every other admin-only
function in this repo needs, and that gate is a human-operated deploy
decision, not something this cycle resolves.
