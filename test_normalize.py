"""Tests for app/normalize.py -- pure logic, no DB dependency.
Run with: python test_normalize.py
"""
from app.normalize import normalize_email, normalize_phone

FAILED = []


def check(name: str, condition: bool, detail: str = ""):
    if condition:
        print(f"PASS: {name}")
    else:
        print(f"FAIL: {name} {detail}")
        FAILED.append(name)


def test_normalize_email_lowercases():
    check("test_normalize_email_lowercases", normalize_email("Jane@Example.com") == "jane@example.com")


def test_normalize_email_strips_whitespace():
    check("test_normalize_email_strips_whitespace", normalize_email("  jane@example.com  ") == "jane@example.com")


def test_normalize_email_none_stays_none():
    check("test_normalize_email_none_stays_none", normalize_email(None) is None)


def test_normalize_email_blank_becomes_none():
    check("test_normalize_email_blank_becomes_none", normalize_email("   ") is None)


def test_normalize_email_already_normalized_unchanged():
    check("test_normalize_email_already_normalized_unchanged", normalize_email("jane@example.com") == "jane@example.com")


def test_normalize_phone_strips_punctuation():
    check("test_normalize_phone_strips_punctuation", normalize_phone("(512) 555-1234") == "5125551234")


def test_normalize_phone_strips_letters_and_spaces():
    check("test_normalize_phone_strips_letters_and_spaces", normalize_phone("ext 555 1234") == "5551234")


def test_normalize_phone_none_stays_none():
    check("test_normalize_phone_none_stays_none", normalize_phone(None) is None)


def test_normalize_phone_blank_becomes_none():
    check("test_normalize_phone_blank_becomes_none", normalize_phone("   ") is None)


def test_normalize_phone_no_digits_becomes_none():
    check("test_normalize_phone_no_digits_becomes_none", normalize_phone("n/a") is None)


def test_normalize_phone_already_digits_unchanged():
    check("test_normalize_phone_already_digits_unchanged", normalize_phone("5125551234") == "5125551234")


def test_normalize_phone_leading_country_code_not_stripped():
    # Documented gap (see app/normalize.py module docstring): this module
    # does NOT strip a leading US country-code '1' -- unconfirmed against
    # real data (every platform.person row on staging has phone_normalized
    # IS NULL as of this test's writing). Asserting the CURRENT documented
    # behavior so a future change to this is a deliberate, visible diff,
    # not a silent regression.
    check(
        "test_normalize_phone_leading_country_code_not_stripped",
        normalize_phone("1-512-555-1234") == "15125551234",
    )


if __name__ == "__main__":
    tests = [
        test_normalize_email_lowercases,
        test_normalize_email_strips_whitespace,
        test_normalize_email_none_stays_none,
        test_normalize_email_blank_becomes_none,
        test_normalize_email_already_normalized_unchanged,
        test_normalize_phone_strips_punctuation,
        test_normalize_phone_strips_letters_and_spaces,
        test_normalize_phone_none_stays_none,
        test_normalize_phone_blank_becomes_none,
        test_normalize_phone_no_digits_becomes_none,
        test_normalize_phone_already_digits_unchanged,
        test_normalize_phone_leading_country_code_not_stripped,
    ]
    for t in tests:
        t()
    total = len(tests)
    passed = total - len(FAILED)
    print(f"\n{passed}/{total} tests passed")
    if FAILED:
        raise SystemExit(1)
