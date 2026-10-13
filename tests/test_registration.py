from __future__ import annotations

from datetime import timedelta

import pytest

from nyagallery.auth import validate_password_strength, validate_username
from nyagallery.db import (
    claim_registration_invite,
    create_engine_for_url,
    create_registration_invite,
    create_user,
    get_security_settings,
    get_user_by_username,
    init_database,
    list_registration_invites,
    make_session_factory,
    now_utc,
    registration_invite_to_dict,
    release_registration_invite,
    revoke_registration_invite,
    update_security_settings,
)
from nyagallery.security import DEFAULT_REGISTRATION_MODE, normalize_security_settings


@pytest.fixture()
def session(tmp_path):
    engine = create_engine_for_url(f"sqlite:///{tmp_path / 'gallery.db'}")
    init_database(engine)
    db = make_session_factory(engine)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def test_registration_mode_defaults_to_closed(session):
    assert get_security_settings(session)["registration_mode"] == DEFAULT_REGISTRATION_MODE


def test_registration_mode_round_trip_and_fallback(session):
    updated = update_security_settings(session, {"registration_mode": "open"}, updated_by_username="boss")
    assert updated["registration_mode"] == "open"
    updated = update_security_settings(session, {"registration_mode": "invite"}, updated_by_username="boss")
    assert updated["registration_mode"] == "invite"
    # Unknown values fall back to the safe default instead of being persisted.
    updated = update_security_settings(session, {"registration_mode": "wide-open"}, updated_by_username="boss")
    assert updated["registration_mode"] == DEFAULT_REGISTRATION_MODE
    assert normalize_security_settings({"registration_mode": None})["registration_mode"] == DEFAULT_REGISTRATION_MODE


def test_invite_codes_are_stored_hashed_and_claimed_atomically(session):
    invite, code = create_registration_invite(session, label="friends", max_uses=2, created_by_username="boss")
    assert code.startswith("nyi_")
    assert invite.code_hash != code
    assert registration_invite_to_dict(invite)["active"] is True

    claimed = claim_registration_invite(session, code)
    assert claimed.used_count == 1
    assert registration_invite_to_dict(claimed)["remaining_uses"] == 1

    claim_registration_invite(session, code)
    with pytest.raises(ValueError, match="no remaining uses"):
        claim_registration_invite(session, code)
    assert registration_invite_to_dict(session.get(type(invite), invite.id))["active"] is False


def test_invite_claim_rejects_unknown_revoked_and_expired_codes(session):
    with pytest.raises(ValueError, match="invalid"):
        claim_registration_invite(session, "nope")

    _, code = create_registration_invite(session, max_uses=3, created_by_username="boss")
    revoke_registration_invite(session, list_registration_invites(session)[0].id)
    with pytest.raises(ValueError, match="revoked"):
        claim_registration_invite(session, code)

    _, expired_code = create_registration_invite(
        session,
        max_uses=1,
        expires_at=now_utc() - timedelta(days=1),
        created_by_username="boss",
    )
    with pytest.raises(ValueError, match="expired"):
        claim_registration_invite(session, expired_code)


def test_release_returns_a_claimed_use(session):
    invite, code = create_registration_invite(session, max_uses=1, created_by_username="boss")
    claim_registration_invite(session, code)
    assert registration_invite_to_dict(session.get(type(invite), invite.id))["remaining_uses"] == 0
    release_registration_invite(session, invite.id)
    assert registration_invite_to_dict(session.get(type(invite), invite.id))["remaining_uses"] == 1
    # Releasing an unused invite must not push the counter below zero.
    release_registration_invite(session, invite.id)
    assert registration_invite_to_dict(session.get(type(invite), invite.id))["used_count"] == 0


def test_create_invite_guards_duplicate_and_custom_codes(session):
    _, code = create_registration_invite(session, code="FRIEND-2026", max_uses=1, created_by_username="boss")
    assert code == "FRIEND-2026"
    with pytest.raises(ValueError, match="already exists"):
        create_registration_invite(session, code="FRIEND-2026", max_uses=1, created_by_username="boss")
    with pytest.raises(ValueError, match="invite not found"):
        revoke_registration_invite(session, 999)


def test_create_user_rejects_duplicate_usernames(session):
    create_user(session, "cat", "hunter2000", "viewer")
    assert get_user_by_username(session, "  CAT  ") is not None
    with pytest.raises(ValueError, match="already exists"):
        create_user(session, "Cat", "hunter2000", "viewer")


@pytest.mark.parametrize(
    "username",
    ["ab", "", "   ", "cat name", "猫猫猫", "cat@home", "guest", "x" * 65],
)
def test_validate_username_rejects_bad_values(username):
    with pytest.raises(ValueError):
        validate_username(username)


@pytest.mark.parametrize("username", ["cat", "cat_01", "cat-01", "cat.01", "x" * 64])
def test_validate_username_accepts_supported_values(username):
    assert validate_username(f"  {username}  ") == username


def test_validate_password_strength():
    assert validate_password_strength("hunter2000") == "hunter2000"
    with pytest.raises(ValueError, match="at least"):
        validate_password_strength("short1")
    with pytest.raises(ValueError, match="at most"):
        validate_password_strength("x" * 513)
