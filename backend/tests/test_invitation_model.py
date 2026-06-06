from datetime import datetime, timezone
from app.models.invitation import Invitation, InvitationStatus


def test_invitation_defaults_pending_and_future_expiry():
    inv = Invitation(project_id="p1", email="s@x.com", token="tok123")
    assert inv.status == InvitationStatus.PENDING
    assert inv.expires_at > datetime.now(timezone.utc)


def test_invitation_status_enum_values():
    assert InvitationStatus.PENDING == "pending"
    assert InvitationStatus.ACCEPTED == "accepted"
    assert InvitationStatus.EXPIRED == "expired"
