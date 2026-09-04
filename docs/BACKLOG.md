# Backlog — decided, not yet actionable

Items Jed has already decided but that don't need schema/code changes
right now (no dependency exists yet to hang them off of). Check this
file whenever touching the area it names — don't rediscover the decision
from scratch or, worse, do it differently by accident.

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
