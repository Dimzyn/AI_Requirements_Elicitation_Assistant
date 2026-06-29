import pytest
from bson import ObjectId
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.db.mongo import get_db
from app.routers import conflicts as conflicts_mod
from app.routers import dialogue as dialogue_mod
from app.services.conflict_resolution import (
    build_resolution_opener,
    build_resolution_summary,
    build_self_resolution_opener,
)
from app.services.llm_service import UpstreamUnavailable
from tests.helpers import _re_project_and_invited_stakeholder


# --------------------------------------------------------------------------- #
# Pure builder unit tests                                                      #
# --------------------------------------------------------------------------- #


def test_cross_opener_contains_both_statements_and_explanation():
    msg = build_resolution_opener(
        stakeholder_name="Alice Tan",
        their_statement="Auto-approve all refunds.",
        other_statement="All refunds require manager sign-off.",
        explanation="Both cannot hold at once.",
        project_title="Refunds App",
    )
    assert "Hi Alice 👋" in msg  # first name only
    assert "Auto-approve all refunds." in msg
    assert "All refunds require manager sign-off." in msg
    assert "Both cannot hold at once." in msg
    assert "Refunds App" in msg
    # the stakeholder's own requirement is framed as "what you asked for"
    assert "What you asked for" in msg


def test_self_opener_lists_both_statements():
    msg = build_self_resolution_opener(
        stakeholder_name="Bob",
        statement_a="Cache responses for one hour.",
        statement_b="Never cache responses.",
        explanation="These contradict.",
        project_title="P",
    )
    assert "Cache responses for one hour." in msg
    assert "Never cache responses." in msg
    assert "These contradict." in msg
    assert "different directions" in msg.lower()


def test_opener_name_and_title_fallbacks():
    msg = build_resolution_opener(
        stakeholder_name=None,
        their_statement="A",
        other_statement="B",
        explanation="E",
        project_title="",
    )
    assert "Hi there 👋" in msg
    assert "this project" in msg


def test_summary_distinguishes_same_and_cross():
    cross = build_resolution_summary(
        their_statement="Statement Alpha",
        other_statement="Statement Beta",
        explanation="Explan Gamma",
        same_stakeholder=False,
    )
    same = build_resolution_summary(
        their_statement="Statement Alpha",
        other_statement="Statement Beta",
        explanation="Explan Gamma",
        same_stakeholder=True,
    )
    assert "another stakeholder" in cross
    assert "own requirements" in same
    for needle in ("Statement Alpha", "Statement Beta", "Explan Gamma"):
        assert needle in cross and needle in same


# --------------------------------------------------------------------------- #
# Router integration                                                           #
# --------------------------------------------------------------------------- #


class FakeDetector:
    def __init__(self, pairs):
        self._pairs = pairs

    async def detect(self, requirements):
        return self._pairs


async def _create_re(c, email):
    await c.post("/auth/signup", json={"email": email, "password": "Passw0rd!", "real_name": "RE"})
    await get_db().users.update_one({"email": email}, {"$set": {"role": "requirements_engineer"}})
    tok = (await c.post("/auth/login", json={"email": email, "password": "Passw0rd!"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


async def _add_stakeholder(c, reh, pid, email, name):
    token = (await c.post(f"/projects/{pid}/invitations", json={"email": email}, headers=reh)).json()["token"]
    s_tok = (await c.post(f"/invitations/{token}/accept", json={"password": "Stake123!", "real_name": name})).json()["access_token"]
    sh = {"Authorization": f"Bearer {s_tok}"}
    sid = (await c.post(f"/projects/{pid}/session", headers=sh)).json()["id"]
    return sh, sid


async def _seed_req(sid, statement):
    now = datetime.now(timezone.utc)
    res = await get_db().requirements.insert_one(
        {"session_id": sid, "statement": statement, "type": "functional", "source_turn_id": "t", "created_at": now}
    )
    return str(res.inserted_id)


def _patch_detector(monkeypatch, rid_a, rid_b):
    a, b = sorted((rid_a, rid_b))
    monkeypatch.setattr(
        conflicts_mod,
        "_make_detector",
        lambda: FakeDetector([{"requirement_a": a, "requirement_b": b, "explanation": "Cannot coexist."}]),
    )


@pytest.mark.asyncio
async def test_same_stakeholder_conflict_opens_one_resolution_chat(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh = await _create_re(c, "re_res1@x.com")
        pid = (await c.post("/projects", json={"title": "Refunds"}, headers=reh)).json()["id"]
        sh, sid = await _add_stakeholder(c, reh, pid, "sh_res1@x.com", "Alice")
        rid_a = await _seed_req(sid, "Auto-approve all refunds.")
        rid_b = await _seed_req(sid, "All refunds require manager sign-off.")
        _patch_detector(monkeypatch, rid_a, rid_b)

        body = (await c.post(f"/projects/{pid}/conflicts/detect", headers=reh)).json()
        cid = body[0]["id"]

        sessions = [s async for s in get_db().sessions.find({"conflict_id": cid, "kind": "conflict_resolution"})]
        assert len(sessions) == 1
        rs = sessions[0]
        assert rs["status"] == "active" and rs["phase"] == "validation"

        turns = [t async for t in get_db().turns.find({"session_id": str(rs["_id"])})]
        assert len(turns) == 1 and turns[0]["role"] == "agent"
        assert "resolve" in turns[0]["content"].lower()

        assert len(body[0]["resolution_sessions"]) == 1
        assert body[0]["resolution_sessions"][0]["stakeholder"] == "Alice"


@pytest.mark.asyncio
async def test_cross_stakeholder_conflict_opens_two_resolution_chats(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh = await _create_re(c, "re_res2@x.com")
        pid = (await c.post("/projects", json={"title": "Refunds"}, headers=reh)).json()["id"]
        sh1, sid1 = await _add_stakeholder(c, reh, pid, "sh_res2a@x.com", "Alice")
        sh2, sid2 = await _add_stakeholder(c, reh, pid, "sh_res2b@x.com", "Bob")
        rid_a = await _seed_req(sid1, "Auto-approve all refunds.")
        rid_b = await _seed_req(sid2, "All refunds require manager sign-off.")
        _patch_detector(monkeypatch, rid_a, rid_b)

        body = (await c.post(f"/projects/{pid}/conflicts/detect", headers=reh)).json()
        cid = body[0]["id"]

        sessions = [s async for s in get_db().sessions.find({"conflict_id": cid, "kind": "conflict_resolution"})]
        assert len(sessions) == 2
        assert len({s["stakeholder_id"] for s in sessions}) == 2  # one per stakeholder
        names = {rs["stakeholder"] for rs in body[0]["resolution_sessions"]}
        assert names == {"Alice", "Bob"}


@pytest.mark.asyncio
async def test_resolution_chats_idempotent_on_redetect(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh = await _create_re(c, "re_res3@x.com")
        pid = (await c.post("/projects", json={"title": "Refunds"}, headers=reh)).json()["id"]
        sh, sid = await _add_stakeholder(c, reh, pid, "sh_res3@x.com", "Alice")
        rid_a = await _seed_req(sid, "Auto-approve all refunds.")
        rid_b = await _seed_req(sid, "All refunds require manager sign-off.")
        _patch_detector(monkeypatch, rid_a, rid_b)

        body = (await c.post(f"/projects/{pid}/conflicts/detect", headers=reh)).json()
        cid = body[0]["id"]
        await c.post(f"/projects/{pid}/conflicts/detect", headers=reh)  # re-detect

        count = await get_db().sessions.count_documents(
            {"conflict_id": cid, "kind": "conflict_resolution"}
        )
        assert count == 1


@pytest.mark.asyncio
async def test_stakeholder_sessions_include_resolution_chat(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh = await _create_re(c, "re_res4@x.com")
        pid = (await c.post("/projects", json={"title": "Refunds"}, headers=reh)).json()["id"]
        sh, sid = await _add_stakeholder(c, reh, pid, "sh_res4@x.com", "Alice")
        rid_a = await _seed_req(sid, "Auto-approve all refunds.")
        rid_b = await _seed_req(sid, "All refunds require manager sign-off.")
        _patch_detector(monkeypatch, rid_a, rid_b)
        await c.post(f"/projects/{pid}/conflicts/detect", headers=reh)

        r = await c.get("/sessions", headers=sh)
        assert r.status_code == 200, r.text
        kinds = [s["kind"] for s in r.json()]
        assert "conflict_resolution" in kinds
        # the original interview session must still be openable (not shadowed)
        opened = await c.post(f"/projects/{pid}/session", headers=sh)
        assert opened.json()["id"] == sid


# --------------------------------------------------------------------------- #
# Dialogue: resolution chats never mint new spec rows                          #
# --------------------------------------------------------------------------- #


class _BoomExtractor:
    """If this ever runs, it would create a requirement — so calls must stay 0."""

    def __init__(self):
        self.calls = 0

    async def extract(self, text):
        self.calls += 1
        return [{"statement": "Should not be stored.", "type": "functional"}]


@pytest.mark.asyncio
async def test_resolution_chat_message_creates_no_requirements(monkeypatch):
    boom = _BoomExtractor()
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: boom)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid = await _re_project_and_invited_stakeholder(c)
        sh_user = await get_db().users.find_one({"email": "s@x.com"})
        now = datetime.now(timezone.utc)
        res = await get_db().sessions.insert_one(
            {
                "project_id": pid,
                "stakeholder_id": str(sh_user["_id"]),
                "title": "Resolve requirement conflict",
                "kind": "conflict_resolution",
                "conflict_id": "deadbeef",
                "status": "active",
                "phase": "validation",
                "summary": "conflict context",
                "auto_named": True,
                "created_at": now,
                "updated_at": now,
            }
        )
        sid = str(res.inserted_id)
        r = await c.post(f"/sessions/{sid}/messages", json={"content": "Option A should win."}, headers=sh)
        assert r.status_code == 200, r.text
        assert boom.calls == 0
        assert await get_db().requirements.count_documents({"session_id": sid}) == 0


# --------------------------------------------------------------------------- #
# AI-suggested reconciled wording (RE approves)                                #
# --------------------------------------------------------------------------- #


class FakeSuggester:
    def __init__(self, result=None, exc=None):
        self.result = result or {"suggestion": "Refunds auto-approve under $50; manager signs off above.", "rationale": "Compromise."}
        self.exc = exc
        self.calls = 0
        self.last_kwargs = None

    async def suggest(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        if self.exc:
            raise self.exc
        return self.result


async def _detect_one_conflict(c, monkeypatch, *, re_email, sh_email):
    """Seed a same-stakeholder conflict and run detection; return (reh, sh, pid, cid, rid_a, rid_b)."""
    reh = await _create_re(c, re_email)
    pid = (await c.post("/projects", json={"title": "Refunds"}, headers=reh)).json()["id"]
    sh, sid = await _add_stakeholder(c, reh, pid, sh_email, "Alice")
    rid_a = await _seed_req(sid, "Auto-approve all refunds.")
    rid_b = await _seed_req(sid, "All refunds require manager sign-off.")
    _patch_detector(monkeypatch, rid_a, rid_b)
    body = (await c.post(f"/projects/{pid}/conflicts/detect", headers=reh)).json()
    return reh, sh, pid, body[0]["id"], rid_a, rid_b


@pytest.mark.asyncio
async def test_suggest_resolution_returns_editable_draft(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, cid, _, _ = await _detect_one_conflict(
            c, monkeypatch, re_email="re_sug1@x.com", sh_email="sh_sug1@x.com"
        )
        fake = FakeSuggester()
        monkeypatch.setattr(conflicts_mod, "_make_suggester", lambda: fake)
        r = await c.post(f"/conflicts/{cid}/suggest", headers=reh)
        assert r.status_code == 200, r.text
        assert r.json()["suggestion"].startswith("Refunds auto-approve")
        assert r.json()["rationale"] == "Compromise."
        assert fake.calls == 1
        # The transcript (resolution opener) was passed through to the suggester.
        assert isinstance(fake.last_kwargs["transcript"], list)
        assert fake.last_kwargs["same_stakeholder"] is True


@pytest.mark.asyncio
async def test_suggest_resolution_503_when_llm_unavailable(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, cid, _, _ = await _detect_one_conflict(
            c, monkeypatch, re_email="re_sug2@x.com", sh_email="sh_sug2@x.com"
        )
        fake = FakeSuggester(exc=UpstreamUnavailable("busy"))
        monkeypatch.setattr(conflicts_mod, "_make_suggester", lambda: fake)
        r = await c.post(f"/conflicts/{cid}/suggest", headers=reh)
        assert r.status_code == 503, r.text


@pytest.mark.asyncio
async def test_suggest_resolution_stakeholder_forbidden(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, cid, _, _ = await _detect_one_conflict(
            c, monkeypatch, re_email="re_sug3@x.com", sh_email="sh_sug3@x.com"
        )
        r = await c.post(f"/conflicts/{cid}/suggest", headers=sh)
        assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_propose_sets_proposal_and_surfaces_on_list(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, cid, _, _ = await _detect_one_conflict(
            c, monkeypatch, re_email="re_prop1@x.com", sh_email="sh_prop1@x.com"
        )
        r = await c.post(
            f"/conflicts/{cid}/propose",
            json={"statement": "Compromise wording.", "rationale": "Splits the difference."},
            headers=reh,
        )
        assert r.status_code == 200, r.text
        assert r.json()["proposal"]["statement"] == "Compromise wording."
        assert r.json()["votes"] == []
        listed = (await c.get(f"/projects/{pid}/conflicts", headers=reh)).json()
        assert listed[0]["proposal"]["statement"] == "Compromise wording."


@pytest.mark.asyncio
async def test_propose_clears_existing_votes(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, cid, _, _ = await _detect_one_conflict(
            c, monkeypatch, re_email="re_prop2@x.com", sh_email="sh_prop2@x.com"
        )
        sh_user = await get_db().users.find_one({"email": "sh_prop2@x.com"})
        # seed a stale vote directly, then re-propose
        await get_db().conflicts.update_one(
            {"_id": ObjectId(cid)},
            {"$set": {f"votes.{str(sh_user['_id'])}": {"choice": "accept", "comment": None, "voted_at": datetime.now(timezone.utc)}}},
        )
        await c.post(f"/conflicts/{cid}/propose", json={"statement": "New wording."}, headers=reh)
        conf = await get_db().conflicts.find_one({"_id": ObjectId(cid)})
        assert conf.get("votes", {}) == {}
