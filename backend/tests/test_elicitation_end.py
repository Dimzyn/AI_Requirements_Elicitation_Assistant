import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.db.mongo import get_db
from app.routers import dialogue as dialogue_mod
from tests.helpers import _re_project_and_invited_stakeholder
from tests.test_dialogue_router import FakeExtractor, FakeTitleGen, _setup_session


# --------------------------------------------------------------------------- #
# Saturation -> wrap-up suggestion                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_saturation_suggests_wrap_up_after_threshold(monkeypatch):
    # Every turn extracts nothing new, so the streak climbs to the threshold (3).
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor(items=[]))
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        r1 = await c.post(f"/sessions/{sid}/messages", json={"content": "hmm"}, headers=sh)
        r2 = await c.post(f"/sessions/{sid}/messages", json={"content": "ok"}, headers=sh)
        r3 = await c.post(f"/sessions/{sid}/messages", json={"content": "sure"}, headers=sh)
        assert r1.json()["wrap_up_suggested"] is False
        assert r2.json()["wrap_up_suggested"] is False
        assert r3.json()["wrap_up_suggested"] is True


@pytest.mark.asyncio
async def test_new_requirement_resets_saturation(monkeypatch):
    # Two empty turns, then a turn that yields a requirement resets the streak.
    extractors = iter([
        FakeExtractor(items=[]),
        FakeExtractor(items=[]),
        FakeExtractor(items=[{"statement": "Users can log in.", "type": "functional"}]),
        FakeExtractor(items=[]),
    ])
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: next(extractors))
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        await c.post(f"/sessions/{sid}/messages", json={"content": "a"}, headers=sh)  # streak 1
        await c.post(f"/sessions/{sid}/messages", json={"content": "b"}, headers=sh)  # streak 2
        r3 = await c.post(f"/sessions/{sid}/messages", json={"content": "c"}, headers=sh)  # reset
        r4 = await c.post(f"/sessions/{sid}/messages", json={"content": "d"}, headers=sh)  # streak 1
        assert r3.json()["wrap_up_suggested"] is False
        assert r4.json()["wrap_up_suggested"] is False
        from bson import ObjectId
        sess = await get_db().sessions.find_one({"_id": ObjectId(sid)})
        assert sess["saturation_streak"] == 1
        assert sess["wrap_up_suggested"] is False


# --------------------------------------------------------------------------- #
# Stakeholder "I'm done"                                                       #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_stakeholder_finish_flags_session_for_review():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid = await _re_project_and_invited_stakeholder(c)
        sid = (await c.post(f"/projects/{pid}/session", headers=sh)).json()["id"]
        r = await c.post(f"/sessions/{sid}/finish", headers=sh)
        assert r.status_code == 200, r.text
        assert r.json()["stakeholder_finished"] is True
        # Stays active until the RE confirms; the RE listing surfaces the flag.
        assert r.json()["status"] == "active"
        sessions = (await c.get(f"/projects/{pid}/sessions", headers=reh)).json()
        assert sessions[0]["stakeholder_finished"] is True
        assert sessions[0]["status"] == "active"


@pytest.mark.asyncio
async def test_re_cannot_finish_session():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid = await _re_project_and_invited_stakeholder(c)
        sid = (await c.post(f"/projects/{pid}/session", headers=sh)).json()["id"]
        r = await c.post(f"/sessions/{sid}/finish", headers=reh)
        assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_finish_other_user_404():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid = await _re_project_and_invited_stakeholder(c)
        sid = (await c.post(f"/projects/{pid}/session", headers=sh)).json()["id"]
        # A different stakeholder cannot finish someone else's session.
        await c.post("/auth/signup", json={"email": "other@x.com", "password": "Passw0rd!", "real_name": "O"})
        tok = (await c.post("/auth/login", json={"email": "other@x.com", "password": "Passw0rd!"})).json()["access_token"]
        r = await c.post(f"/sessions/{sid}/finish", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 404, r.text


# --------------------------------------------------------------------------- #
# Explicit "I'm done" intent -> immediate wrap-up suggestion                   #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_explicit_done_suggests_wrap_up_immediately(monkeypatch):
    # Even on the very first message, an explicit "I'm done" offers to wrap up —
    # without waiting for the 3-turn saturation streak to build.
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor(items=[]))
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        r = await c.post(f"/sessions/{sid}/messages", json={"content": "No, that's all I had."}, headers=sh)
        assert r.json()["wrap_up_suggested"] is True


@pytest.mark.asyncio
async def test_done_intent_wraps_up_even_with_new_requirement(monkeypatch):
    # "that's everything" wraps up immediately even when the turn also yields a
    # requirement — and that requirement is still persisted.
    monkeypatch.setattr(
        dialogue_mod,
        "_make_extractor",
        lambda: FakeExtractor(items=[{"statement": "Users can log in.", "type": "functional"}]),
    )
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        r = await c.post(
            f"/sessions/{sid}/messages",
            json={"content": "Add a login screen, and that's everything from me."},
            headers=sh,
        )
        assert r.json()["wrap_up_suggested"] is True
        reqs = [d async for d in get_db().requirements.find({"session_id": sid})]
        assert len(reqs) == 1


@pytest.mark.asyncio
async def test_ordinary_message_does_not_suggest_wrap_up(monkeypatch):
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor(items=[]))
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        r = await c.post(f"/sessions/{sid}/messages", json={"content": "I want a booking system."}, headers=sh)
        assert r.json()["wrap_up_suggested"] is False
