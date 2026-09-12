"""plan_service.py — the single place that answers "is this user
premium" and "how many of X do they have." is_premium() is pure logic
(no DB), tested directly on plain User() instances; the count_* helpers
are exercised indirectly by the route tests in test_accounts.py /
test_assets.py / test_categories.py / test_recurring.py, which need a
real database to have anything to count."""
from datetime import datetime, timedelta, timezone

from app.models.user import User
from app.services.plan_service import is_premium


def test_admin_is_always_premium_regardless_of_premium_until():
    admin = User(email="a@example.com", password_hash="x", is_admin=True, premium_until=None)
    assert is_premium(admin) is True


def test_free_user_with_no_premium_until_is_not_premium():
    user = User(email="b@example.com", password_hash="x", is_admin=False, premium_until=None)
    assert is_premium(user) is False


def test_user_with_future_premium_until_is_premium():
    user = User(
        email="c@example.com",
        password_hash="x",
        is_admin=False,
        premium_until=datetime.now(timezone.utc) + timedelta(days=30),
    )
    assert is_premium(user) is True


def test_user_with_past_premium_until_is_not_premium():
    user = User(
        email="d@example.com",
        password_hash="x",
        is_admin=False,
        premium_until=datetime.now(timezone.utc) - timedelta(days=1),
    )
    assert is_premium(user) is False


def test_premium_until_exactly_now_is_treated_as_expired():
    """The boundary is exclusive (`>`, not `>=`) — a premium_until equal
    to the current instant no longer counts as active."""
    now = datetime.now(timezone.utc)
    user = User(email="e@example.com", password_hash="x", is_admin=False, premium_until=now)
    assert is_premium(user) is False
