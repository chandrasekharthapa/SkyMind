"""Ownership comes from the bearer token, never from the request body.

`POST /booking/create` used to accept `user_id` in its JSON body and write it
straight into `bookings.user_id`. The endpoint has no auth dependency — guest
checkout is a deliberate product decision — so an unauthenticated caller could file
a booking, complete with passenger names, passport and Aadhaar numbers, against any
account id they cared to type. Worse, the ownership checks on the other four booking
endpoints (`GET /{id}`, `POST /{id}/cancel`, `GET /{id}/download`) compare the
session against that column, so a forged value made those checks pass for the forger.

`POST /alerts/subscribe` had the same field with the opposite symptom. It *does*
require a token, and a mismatched body value was rejected, so the forgery route was
closed — but `user_id` was written only when the body supplied it, and nothing in
this repo ever supplies it. Every alert a signed-in user created was therefore stored
with a NULL owner while the token proving who they were sat unread in the request,
which made all three alert endpoints useless as a set: the list filters on `user_id`,
and delete refuses a row it does not own.

Both request models have dropped the field. These tests pin the rule in both
directions — a token's subject is stored, a body's claim is not — and pin the two
`get_current_user` behaviours the fix depends on. They call the handler coroutines
directly rather than through a TestClient, so no app instance or live database is
needed.
"""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from fastapi import HTTPException

from backend.routers import auth as auth_module
from backend.routers import booking as booking_module
from backend.routers import alerts as alerts_module
from backend.routers.auth import get_current_user, get_current_user_optional
from backend.routers.booking import CreateBookingRequest, create_booking
from backend.routers.alerts import AlertRequest, subscribe_alert

TOKEN_SUBJECT = "11111111-1111-1111-1111-111111111111"
FORGED_SUBJECT = "22222222-2222-2222-2222-222222222222"


# ── Test doubles ──────────────────────────────────────────────────────
# Enough of the supabase-py fluent chain to record what a handler tried to write.

class _Table:
    def __init__(self, recorder, name):
        self._recorder = recorder
        self._name = name
        self._filters = {}

    def insert(self, payload):
        self._recorder.inserts.append((self._name, payload))
        return self

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, key, value):
        self._filters[key] = value
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        if self._filters:
            self._recorder.queries.append((self._name, dict(self._filters)))
            # No pre-existing row, so the duplicate branch falls through to insert.
            return SimpleNamespace(data=[])
        return SimpleNamespace(data=[{"id": "row-1"}])


class _Recorder:
    def __init__(self, token_subject=None, returns_no_user=False):
        self.inserts = []
        self.queries = []
        self.auth = SimpleNamespace(get_user=self._get_user)
        self._token_subject = token_subject
        self._returns_no_user = returns_no_user

    def table(self, name):
        return _Table(self, name)

    def _get_user(self, _token):
        if self._returns_no_user:
            # Supabase answered, and said the token maps to nobody. Distinct from a
            # transport failure, and it is the branch that raises the explicit 401.
            return SimpleNamespace(user=None)
        if self._token_subject is None:
            raise RuntimeError("invalid JWT")
        return SimpleNamespace(user=SimpleNamespace(id=self._token_subject))

    def payload_for(self, table):
        for name, payload in self.inserts:
            if name == table:
                return payload
        raise AssertionError(f"nothing was inserted into {table!r}: {self.inserts!r}")


def _install(monkeypatch, recorder):
    """Point every module that touches the DB at one recorder.

    `booking_module.db`, `auth_module.db` and `alerts_module.db` are the same
    `Database()` singleton, but setting the attribute on each name keeps the test
    honest if that ever stops being true.
    """
    for module in (auth_module, booking_module, alerts_module):
        monkeypatch.setattr(module.db, "supabase", recorder, raising=False)
    # Confirmation mail is best-effort in the handler; keep SMTP out of the test.
    monkeypatch.setattr(
        booking_module.dispatcher.email, "send_booking_confirmation",
        lambda *_a, **_k: True, raising=False,
    )


def _booking_request(**extra):
    body = {
        "flight_offer_id": "offer-1",
        "flight_data": {
            "price": {"total": "5400.00", "base": "4200.00"},
            "itineraries": [{"segments": [{"origin": "DEL", "destination": "BOM"}]}],
        },
        "passengers": [{"first_name": "Asha", "last_name": "Rao"}],
        "contact_email": "asha@example.com",
        "contact_phone": "+919900000000",
    }
    body.update(extra)
    return CreateBookingRequest(**body)


# ── The request contract ──────────────────────────────────────────────

def test_the_booking_request_model_has_no_user_id_field():
    """The field is removed, not merely unread. A reader of the model sees the rule."""
    assert "user_id" not in CreateBookingRequest.model_fields, sorted(CreateBookingRequest.model_fields)


def test_the_alert_request_model_has_no_user_id_field():
    assert "user_id" not in AlertRequest.model_fields, sorted(AlertRequest.model_fields)


def test_an_old_client_still_sending_user_id_is_accepted_not_rejected():
    """Removal must not turn a stale deployed client into a 422.

    Pydantic V2 ignores unknown keys by default; this asserts the project has not
    switched that model config to `forbid` underneath us.
    """
    req = _booking_request(user_id=FORGED_SUBJECT)
    assert not hasattr(req, "user_id")


# ── POST /booking/create ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_forged_body_user_id_does_not_reach_the_bookings_row(monkeypatch):
    """The regression this file exists for.

    A caller sends someone else's account id in the body and a token of their own.
    The stored owner must be the token's subject.
    """
    recorder = _Recorder(token_subject=TOKEN_SUBJECT)
    _install(monkeypatch, recorder)

    await create_booking(
        _booking_request(user_id=FORGED_SUBJECT), current_user_id=TOKEN_SUBJECT,
    )

    stored = recorder.payload_for("bookings")
    assert stored["user_id"] == TOKEN_SUBJECT, stored["user_id"]
    assert FORGED_SUBJECT not in str(stored), stored


@pytest.mark.asyncio
async def test_an_anonymous_booking_stores_no_owner_at_all(monkeypatch):
    """Guest checkout stays open, and NULL is the honest record of "we do not know".

    Not the empty string, and not an id the request suggested.
    """
    recorder = _Recorder(token_subject=None)
    _install(monkeypatch, recorder)

    await create_booking(_booking_request(user_id=FORGED_SUBJECT), current_user_id=None)

    stored = recorder.payload_for("bookings")
    assert "user_id" not in stored, stored


@pytest.mark.asyncio
async def test_a_token_subject_is_stored_as_the_owner(monkeypatch):
    """The other half of the distinction — without this, "never store an owner" passes."""
    recorder = _Recorder(token_subject=TOKEN_SUBJECT)
    _install(monkeypatch, recorder)

    result = await create_booking(_booking_request(), current_user_id=TOKEN_SUBJECT)

    assert recorder.payload_for("bookings")["user_id"] == TOKEN_SUBJECT
    assert result["success"] is True
    assert result["booking_reference"].startswith("SKY"), result["booking_reference"]


# ── POST /alerts/subscribe ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_alert_is_stored_against_the_token_subject(monkeypatch):
    """Previously NULL: `payload["user_id"]` was set only if the body carried one."""
    recorder = _Recorder(token_subject=TOKEN_SUBJECT)
    _install(monkeypatch, recorder)

    await subscribe_alert(
        AlertRequest(origin_code="DEL", destination_code="BOM", target_price=4500),
        current_user_id=TOKEN_SUBJECT,
    )

    assert recorder.payload_for("price_alerts")["user_id"] == TOKEN_SUBJECT


@pytest.mark.asyncio
async def test_the_alert_duplicate_check_runs_and_filters_on_the_token_subject(monkeypatch):
    """The check was gated on the body field, so in practice it never ran."""
    recorder = _Recorder(token_subject=TOKEN_SUBJECT)
    _install(monkeypatch, recorder)

    await subscribe_alert(
        AlertRequest(
            origin_code="DEL", destination_code="BOM",
            target_price=4500, departure_date="2026-12-01",
        ),
        current_user_id=TOKEN_SUBJECT,
    )

    dupe_queries = [f for name, f in recorder.queries if name == "price_alerts"]
    assert dupe_queries, recorder.queries
    assert dupe_queries[0]["user_id"] == TOKEN_SUBJECT, dupe_queries[0]


# ── The dependencies the fix rests on ─────────────────────────────────

@pytest.mark.asyncio
async def test_a_missing_token_is_401_and_not_422():
    """`Header(...)` made the token a required request parameter.

    FastAPI's validation layer then answered a tokenless call with 422 before the
    function ran, which is not the status any client checks for and made eleven
    protected endpoints look schema-broken rather than unauthenticated. Calling the
    coroutine directly cannot exercise that validation layer — the `Header(None)`
    half of the fix is a signature change, verified by reading it — so what this
    pins is the other half: with the header absent, the decision is made *here*,
    and it is a 401.
    """
    with pytest.raises(HTTPException) as excinfo:
        await get_current_user(authorization=None)
    assert excinfo.value.status_code == 401, excinfo.value.status_code


@pytest.mark.asyncio
async def test_a_non_bearer_scheme_is_401():
    with pytest.raises(HTTPException) as excinfo:
        await get_current_user(authorization="Basic YWJjOmRlZg==")
    assert excinfo.value.status_code == 401, excinfo.value.status_code


@pytest.mark.asyncio
async def test_a_token_mapping_to_nobody_keeps_its_own_401_detail(monkeypatch):
    """The inner raise sits inside a `try` whose `except Exception` re-raises as 401.

    Asserting the *status* could not detect the ordering bug this exists for, because
    the generic handler answers 401 too — the specific raise would be swallowed and
    reworded while the test stayed green. The detail is what discriminates: without
    the `except HTTPException: raise` line above the generic handler, this arrives as
    "Could not validate credentials: 401: Invalid token payload".
    """
    _install(monkeypatch, _Recorder(returns_no_user=True))
    with pytest.raises(HTTPException) as excinfo:
        await get_current_user(authorization="Bearer stale-but-well-formed")
    assert excinfo.value.status_code == 401, excinfo.value.status_code
    assert excinfo.value.detail == "Invalid token payload", excinfo.value.detail


@pytest.mark.asyncio
async def test_an_unusable_token_is_401_rather_than_a_500(monkeypatch):
    """A raising auth call is still an authentication failure, not a server error."""
    _install(monkeypatch, _Recorder(token_subject=None))
    with pytest.raises(HTTPException) as excinfo:
        await get_current_user(authorization="Bearer not-a-real-token")
    assert excinfo.value.status_code == 401, excinfo.value.status_code


@pytest.mark.asyncio
async def test_optional_auth_returns_none_instead_of_raising(monkeypatch):
    """A caller with an expired session must get the anonymous path, not a failed
    checkout. The only distinction this dependency draws is "token proves this user"
    versus "we do not know who this is"."""
    _install(monkeypatch, _Recorder(token_subject=None))
    assert await get_current_user_optional(authorization=None) is None
    assert await get_current_user_optional(authorization="Basic xyz") is None
    assert await get_current_user_optional(authorization="Bearer expired") is None


@pytest.mark.asyncio
async def test_optional_auth_returns_the_subject_when_the_token_is_good(monkeypatch):
    _install(monkeypatch, _Recorder(token_subject=TOKEN_SUBJECT))
    assert await get_current_user_optional(authorization="Bearer good") == TOKEN_SUBJECT
