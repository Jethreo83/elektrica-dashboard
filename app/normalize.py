"""Email/phone normalization for platform.person matching.

Closes the gap flagged in docs/BACKLOG.md ("no email/phone normalization
utility exists" -- 2026-09-05 cron cycle). `platform.match_or_create_person()`'s
exact-match step does a literal string-equality comparison against
`platform.person.email_normalized`/`phone_normalized`, which are already
normalized AT REST -- but nothing upstream of that call normalized an
INCOMING value before this module existed. Without it, `Jane@Example.com`
or a phone with dashes/parens would silently fail to match an existing
`jane@example.com`/digits-only row and create a duplicate `platform.person`.

Scope decision (deliberate, not an oversight): kept LOCAL to Elektrica's
app layer (`app/normalize.py`), not extracted to a shared `platform.*`
module yet. Checked both other consumers before deciding:
  - Complete Collision (`app/repository.py`, `create_customer_and_link()`)
    inlines `email.strip().lower()` for email and does NOT normalize phone
    at all -- it still does a bespoke raw INSERT into platform.person
    rather than calling platform.match_or_create_person() (flagged in its
    own docstring as a known gap, not yet closed).
  - VLS's equivalent call site was not read (out of scope -- no VLS
    access from this profile).
Per ADR-001's own extraction rule ("_shared is extracted only when a
second consumer exists"), Elektrica is effectively the FIRST real
consumer of a phone-normalizing function -- Collision's inline email-only
version doesn't count as a second consumer of the phone half. Building
here first, matching this repo's convention of "extract on the second
real consumer, not preemptively" (same reasoning ADR-001 §1 documents for
_shared generally). If/when Collision's `create_customer_and_link()` is
ever wired to `platform.match_or_create_person()` too, THAT is the moment
to promote this to a shared `platform` helper -- flag it then, don't
duplicate silently.

IMPORTANT -- phone format is UNCONFIRMED against real data, flagged not
guessed-and-hidden: as of this module's creation, every `platform.person`
row on staging has `phone_normalized IS NULL` (checked directly: 0 of 14
rows have a non-null phone_normalized). There is no real row to infer the
canonical format from. This module normalizes phone to DIGITS ONLY (strip
everything but 0-9), with NO US country-code stripping (a bare 11-digit
leading '1' is left as-is) since that is an assumption this module cannot
verify from data. If Jed's actual convention differs (e.g. always-10-digit
US numbers with a leading country code stripped), this function is the
one place to fix it -- flagged here for Jed's review, not silently
assumed correct.
"""
from __future__ import annotations

import re
from typing import Optional


def normalize_email(email: Optional[str]) -> Optional[str]:
    """Lowercase + strip whitespace. Returns None for falsy/blank input
    (never an empty string) so callers can pass the result straight to
    platform.match_or_create_person()'s nullable p_email_normalized
    argument without an extra falsy check."""
    if email is None:
        return None
    cleaned = email.strip().lower()
    return cleaned or None


def normalize_phone(phone: Optional[str]) -> Optional[str]:
    """Strip everything but digits. Returns None for falsy/blank input or
    input with no digits at all. Does NOT strip a US country code -- see
    module docstring for why (unconfirmed against real data)."""
    if phone is None:
        return None
    digits = re.sub(r"\D", "", phone)
    return digits or None
