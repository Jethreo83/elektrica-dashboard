"""Test-collection-time setup, applies to test_api.py/test_models.py.

Sets ELEKTRICA_DISABLE_AUTH=1 before app/api.py's module import so the
global SSO-JWT auth middleware (see app/api.py's enforce_staff_auth())
skips verification for TestClient requests, which predate that layer
and exercise routes via app.dependency_overrides[get_cursor] with no
Authorization header. Never set outside this test process.
"""
import os

os.environ.setdefault("ELEKTRICA_DISABLE_AUTH", "1")
