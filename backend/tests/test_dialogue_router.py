import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.mongo import get_db
from app.routers import dialogue as dialogue_mod
from app.services.llm_service import UpstreamUnavailable
from app.services.question_generator import GeneratedQuestion, QuestionParseError
from tests.helpers import _re_project_and_invited_stakeholder


class FakeGen:
    def __init__(self):
        self.calls = 0
        self.history_lengths = []
        self.batch_counts = []
        self.requirements_seen = []

    async def next_question(
        self, *, phase, summary, history, kind="interview", requirements=None
    ):
        self.calls += 1
        self.history_lengths.append(len(history))
        self.requirements_seen.append(requirements)
        return GeneratedQuestion(
            question=f"Q{self.calls}: what about X?",
            strategy="concept",
            attempts=1,
            valid=True,
            mistakes=[],
        )

    async def next_questions(
        self, *, count, phase, summary, history, kind="interview", requirements=None
    ):
        self.calls += 1
        self.history_lengths.append(len(history))
        self.batch_counts.append(count)
        self.requirements_seen.append(requirements)
        return [
            GeneratedQuestion(
                question=f"Q{i}: what about X?",
                strategy="concept",
                attempts=1,
                valid=True,
                mistakes=[],
            )
            for i in range(1, count + 1)
        ]


class FlakyGen(FakeGen):
    """Raises the given exception on every generation call."""

    def __init__(self, exc: Exception):
        super().__init__()
        self.exc = exc

    async def next_question(self, **kwargs):
        self.calls += 1
        raise self.exc

    async def next_questions(self, **kwargs):
        self.calls += 1
        raise self.exc


class FakeExtractor:
    def __init__(self, items=None):
        self.items = items or []
        self.calls = 0

    async def extract(self, text):
        self.calls += 1
        return list(self.items)


class FakeTitleGen:
    def __init__(self, title="Calendar Task Sync"):
        self.title = title
        self.calls = 0

    async def generate(self, text):
        self.calls += 1
        return self.title


class BoomTitleGen:
    async def generate(self, text):
        raise RuntimeError("llm down")


async def _setup_session(c, monkeypatch=None):
    """Create a RE + project + invited stakeholder, open a session, return (reh, sh, pid, sid)."""
    reh, sh, pid = await _re_project_and_invited_stakeholder(c)
    r = await c.post(f"/projects/{pid}/session", headers=sh)
    assert r.status_code in (200, 201), r.text
    sid = r.json()["id"]
    return reh, sh, pid, sid


@pytest.mark.asyncio
async def test_post_turn_default_generates_one_question(monkeypatch):
    # Default count is 1 — matching the UI's default questions-per-turn.
    fg = FakeGen()
    monkeypatch.setattr(dialogue_mod, "_make_generator", lambda: fg)
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        r = await c.post(f"/sessions/{sid}/turns", json={"content": "I want a POS system."}, headers=sh)
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["questions"]) == 1
        assert body["stakeholder_turn_id"]
        assert fg.batch_counts == [1]


@pytest.mark.asyncio
async def test_post_turn_count_5_is_one_batched_generator_call(monkeypatch):
    # A multi-question turn costs a single generator invocation, not N.
    fg = FakeGen()
    monkeypatch.setattr(dialogue_mod, "_make_generator", lambda: fg)
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        r = await c.post(f"/sessions/{sid}/turns?count=5", json={"content": "I want a POS system."}, headers=sh)
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["questions"]) == 5
        assert all(q["strategy"] == "concept" for q in body["questions"])
        assert fg.calls == 1
        assert fg.batch_counts == [5]


@pytest.mark.asyncio
async def test_post_turn_returns_session_title(monkeypatch):
    # The combined endpoint reports the auto-generated title so the UI can
    # rename the sidebar without a second request.
    fg = FakeGen()
    monkeypatch.setattr(dialogue_mod, "_make_generator", lambda: fg)
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen("Calendar Task Sync"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        r = await c.post(f"/sessions/{sid}/turns", json={"content": "Sync my todos."}, headers=sh)
        assert r.status_code == 200, r.text
        assert r.json()["session_title"] == "Calendar Task Sync"


@pytest.mark.asyncio
async def test_post_turn_explicit_done_skips_generation(monkeypatch):
    # An "I'm done" message wraps up without burning Gemini calls on questions
    # the stakeholder no longer wants (mirrors the old UI gating).
    fg = FakeGen()
    monkeypatch.setattr(dialogue_mod, "_make_generator", lambda: fg)
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        r = await c.post(f"/sessions/{sid}/turns", json={"content": "I think that's all, I'm done."}, headers=sh)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["wrap_up_suggested"] is True
        assert body["questions"] == []
        assert fg.calls == 0


@pytest.mark.asyncio
async def test_post_turn_saturation_wrap_up_still_returns_questions(monkeypatch):
    # Saturation is only known after extraction, which runs concurrently with
    # generation — so the wrap-up suggestion arrives WITH questions, and the
    # stakeholder can answer them or finish.
    fg = FakeGen()
    monkeypatch.setattr(dialogue_mod, "_make_generator", lambda: fg)
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())  # never extracts
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        for i in range(2):
            r = await c.post(f"/sessions/{sid}/turns", json={"content": f"nothing new {i}"}, headers=sh)
            assert r.json()["wrap_up_suggested"] is False
        r = await c.post(f"/sessions/{sid}/turns", json={"content": "nothing new again"}, headers=sh)
        body = r.json()
        assert body["wrap_up_suggested"] is True
        assert len(body["questions"]) == 1


@pytest.mark.asyncio
async def test_post_turn_threads_requirements_into_generator(monkeypatch):
    # Requirements captured on earlier turns are handed to the generator as
    # covered-ground context (fetched before this turn's extraction runs).
    fg = FakeGen()
    fx = FakeExtractor(items=[{"statement": "Users can pay by card.", "type": "functional"}])
    monkeypatch.setattr(dialogue_mod, "_make_generator", lambda: fg)
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: fx)
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        await c.post(f"/sessions/{sid}/turns", json={"content": "card payments please"}, headers=sh)
        assert fg.requirements_seen[0] == []  # nothing extracted before turn 1
        await c.post(f"/sessions/{sid}/turns", json={"content": "more detail"}, headers=sh)
        assert fg.requirements_seen[1] == ["Users can pay by card."]


@pytest.mark.asyncio
async def test_count_param_caps_at_10(monkeypatch):
    fg = FakeGen()
    monkeypatch.setattr(dialogue_mod, "_make_generator", lambda: fg)
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        r = await c.post(f"/sessions/{sid}/turns?count=999", json={"content": "x"}, headers=sh)
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_batch_fetches_history_once(monkeypatch):
    fg = FakeGen()
    monkeypatch.setattr(dialogue_mod, "_make_generator", lambda: fg)
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        r = await c.post(f"/sessions/{sid}/turns?count=3", json={"content": "hello"}, headers=sh)
        assert r.status_code == 200, r.text
        # One generator call for the whole turn, seeing the seeded greeting +
        # the fresh stakeholder turn; the batch keeps its own questions distinct.
        assert fg.history_lengths == [2]
        assert fg.batch_counts == [3]


@pytest.mark.asyncio
async def test_404_on_wrong_user_session(monkeypatch):
    fg = FakeGen()
    monkeypatch.setattr(dialogue_mod, "_make_generator", lambda: fg)
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        # Sign up a second user (not a member of this project)
        await c.post("/auth/signup", json={"email": "other@x.com", "password": "Passw0rd!", "real_name": "Other"})
        other_tok = (await c.post("/auth/login", json={"email": "other@x.com", "password": "Passw0rd!"})).json()["access_token"]
        hb = {"Authorization": f"Bearer {other_tok}"}
        r = await c.post(f"/sessions/{sid}/turns", json={"content": "x"}, headers=hb)
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_401_when_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/sessions/507f1f77bcf86cd799439011/turns", json={"content": "x"})
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_get_turns_returns_history_in_order(monkeypatch):
    fg = FakeGen()
    monkeypatch.setattr(dialogue_mod, "_make_generator", lambda: fg)
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        post = await c.post(
            f"/sessions/{sid}/turns?count=5",
            json={"content": "I want a POS system."},
            headers=sh,
        )
        assert post.status_code == 200, post.text

        r = await c.get(f"/sessions/{sid}/turns", headers=sh)
        assert r.status_code == 200, r.text
        body = r.json()
        # 1 seeded greeting + 1 stakeholder + 5 agent turns (count=5) = 7 total
        assert isinstance(body, list)
        assert len(body) == 7
        # First turn is the seeded greeting: an agent turn with no strategy badge
        assert body[0]["role"] == "agent"
        assert body[0]["strategy"] is None
        # The stakeholder turn carries the original content
        stakeholders = [t for t in body if t["role"] == "stakeholder"]
        assert len(stakeholders) == 1
        assert stakeholders[0]["content"] == "I want a POS system."
        # 1 greeting + 5 generated questions; only the questions carry a strategy
        agents = [t for t in body if t["role"] == "agent"]
        assert len(agents) == 6
        assert len([t for t in agents if t.get("strategy")]) == 5
        # Sorted by created_at ascending
        timestamps = [t["created_at"] for t in body]
        assert timestamps == sorted(timestamps)


@pytest.mark.asyncio
async def test_get_turns_401_when_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/sessions/507f1f77bcf86cd799439011/turns")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_get_turns_404_for_other_user(monkeypatch):
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        # Second user with no access
        await c.post("/auth/signup", json={"email": "other2@x.com", "password": "Passw0rd!", "real_name": "O2"})
        other_tok = (await c.post("/auth/login", json={"email": "other2@x.com", "password": "Passw0rd!"})).json()["access_token"]
        r = await c.get(f"/sessions/{sid}/turns", headers={"Authorization": f"Bearer {other_tok}"})
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_re_can_read_turns_of_owned_project_session(monkeypatch):
    """RE who owns the project can read turns even though they're not the stakeholder."""
    monkeypatch.setattr(dialogue_mod, "_make_generator", lambda: FakeGen())
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        await c.post(f"/sessions/{sid}/messages", json={"content": "hi"}, headers=sh)
        r = await c.get(f"/sessions/{sid}/turns", headers=reh)
        assert r.status_code == 200
        assert len(r.json()) >= 2  # greeting + stakeholder turn


@pytest.mark.asyncio
async def test_extractor_persists_requirements(monkeypatch):
    fg = FakeGen()
    fx = FakeExtractor(items=[
        {"statement": "Users can pay by card.", "type": "functional"},
        {"statement": "P95 latency below 3s.", "type": "non_functional"},
    ])
    monkeypatch.setattr(dialogue_mod, "_make_generator", lambda: fg)
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: fx)
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        r = await c.post(f"/sessions/{sid}/turns?count=1", json={"content": "I want card payments."}, headers=sh)
        assert r.status_code == 200, r.text
        # extractor was called once with the stakeholder content
        assert fx.calls == 1
        # requirements were persisted
        rows = [d async for d in get_db().requirements.find({"session_id": sid})]
        assert len(rows) == 2
        statements = sorted(d["statement"] for d in rows)
        assert "P95 latency below 3s." in statements
        assert "Users can pay by card." in statements
        # source_turn_id is the stakeholder turn we just inserted
        body = r.json()
        assert all(d["source_turn_id"] == body["stakeholder_turn_id"] for d in rows)


@pytest.mark.asyncio
async def test_post_message_persists_stakeholder_and_extracts_requirements(monkeypatch):
    ftg = FakeTitleGen("My Project Title")
    fx = FakeExtractor(items=[{"statement": "Users can log in.", "type": "functional"}])
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: fx)
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: ftg)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        r = await c.post(f"/sessions/{sid}/messages", json={"content": "I want auth."}, headers=sh)
        assert r.status_code == 200, r.text
        assert r.json()["stakeholder_turn_id"]
        # title is auto-generated from first message
        assert r.json()["session_title"] == "My Project Title"
        # turns persisted: seeded greeting first, then the stakeholder message
        turns = (await c.get(f"/sessions/{sid}/turns", headers=sh)).json()
        assert len(turns) == 2
        assert turns[0]["role"] == "agent"
        assert turns[1]["role"] == "stakeholder"
        assert turns[1]["content"] == "I want auth."
        # requirement was extracted
        reqs = [d async for d in get_db().requirements.find({"session_id": sid})]
        assert len(reqs) == 1


@pytest.mark.asyncio
async def test_first_message_auto_names_session(monkeypatch):
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())
    ftg = FakeTitleGen("Calendar Task Sync")
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: ftg)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        r = await c.post(f"/sessions/{sid}/messages", json={"content": "Sync my todos with Google Calendar."}, headers=sh)
        assert r.status_code == 200, r.text
        assert r.json()["session_title"] == "Calendar Task Sync"
        assert ftg.calls == 1
        # the session is renamed in the listing
        sessions = (await c.get("/sessions", headers=sh)).json()
        assert sessions[0]["title"] == "Calendar Task Sync"
        # a second message does NOT rename again
        r2 = await c.post(f"/sessions/{sid}/messages", json={"content": "Also remind me."}, headers=sh)
        assert r2.json()["session_title"] == "Calendar Task Sync"
        assert ftg.calls == 1


@pytest.mark.asyncio
async def test_title_generation_failure_returns_none(monkeypatch):
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: BoomTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        r = await c.post(f"/sessions/{sid}/messages", json={"content": "anything"}, headers=sh)
        # reply still succeeds; title is None when generation fails
        assert r.status_code == 200, r.text
        assert r.json()["session_title"] is None


@pytest.mark.asyncio
async def test_post_message_404_other_user(monkeypatch):
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        await c.post("/auth/signup", json={"email": "other3@x.com", "password": "Passw0rd!", "real_name": "O3"})
        other_tok = (await c.post("/auth/login", json={"email": "other3@x.com", "password": "Passw0rd!"})).json()["access_token"]
        r = await c.post(f"/sessions/{sid}/messages", json={"content": "x"}, headers={"Authorization": f"Bearer {other_tok}"})
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_post_question_generates_one_from_history(monkeypatch):
    fg = FakeGen()
    monkeypatch.setattr(dialogue_mod, "_make_generator", lambda: fg)
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        # seed a stakeholder turn first
        await c.post(f"/sessions/{sid}/messages", json={"content": "I want a POS."}, headers=sh)
        # generate one question
        r = await c.post(f"/sessions/{sid}/questions", headers=sh)
        assert r.status_code == 200, r.text
        q = r.json()
        assert q["content"].startswith("Q")
        assert q["strategy"] == "concept"
        # verify FakeGen saw history with the seeded greeting + 1 stakeholder turn
        assert fg.history_lengths == [2]


@pytest.mark.asyncio
async def test_post_question_404_other_user(monkeypatch):
    monkeypatch.setattr(dialogue_mod, "_make_generator", lambda: FakeGen())
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        await c.post("/auth/signup", json={"email": "other4@x.com", "password": "Passw0rd!", "real_name": "O4"})
        other_tok = (await c.post("/auth/login", json={"email": "other4@x.com", "password": "Passw0rd!"})).json()["access_token"]
        r = await c.post(f"/sessions/{sid}/questions", headers={"Authorization": f"Bearer {other_tok}"})
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_post_message_and_question_401_unauthed():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r1 = await c.post("/sessions/507f1f77bcf86cd799439011/messages", json={"content": "x"})
        r2 = await c.post("/sessions/507f1f77bcf86cd799439011/questions")
        assert r1.status_code == 401
        assert r2.status_code == 401


@pytest.mark.asyncio
async def test_re_cannot_post_turn():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid = await _re_project_and_invited_stakeholder(c)
        sid = (await c.post(f"/projects/{pid}/session", headers=sh)).json()["id"]
        r = await c.post(f"/sessions/{sid}/turns", json={"content": "hi"}, headers=reh)
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_completed_session_rejects_messages(monkeypatch):
    """After RE marks session complete, stakeholder POST /messages returns 409."""
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        # RE marks session complete
        complete_r = await c.post(f"/sessions/{sid}/complete", headers=reh)
        assert complete_r.status_code == 200, complete_r.text
        assert complete_r.json()["status"] == "completed"
        # Stakeholder tries to post a message after session is completed
        r = await c.post(f"/sessions/{sid}/messages", json={"content": "still trying"}, headers=sh)
        assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_completed_session_rejects_turns(monkeypatch):
    """After RE marks session complete, stakeholder POST /turns returns 409."""
    monkeypatch.setattr(dialogue_mod, "_make_generator", lambda: FakeGen())
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        complete_r = await c.post(f"/sessions/{sid}/complete", headers=reh)
        assert complete_r.status_code == 200, complete_r.text
        r = await c.post(f"/sessions/{sid}/turns", json={"content": "still trying"}, headers=sh)
        assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_completed_session_rejects_questions(monkeypatch):
    """After RE marks session complete, stakeholder POST /questions returns 409."""
    monkeypatch.setattr(dialogue_mod, "_make_generator", lambda: FakeGen())
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        complete_r = await c.post(f"/sessions/{sid}/complete", headers=reh)
        assert complete_r.status_code == 200, complete_r.text
        r = await c.post(f"/sessions/{sid}/questions", headers=sh)
        assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_post_turn_returns_503_when_llm_unavailable(monkeypatch):
    """Upstream outage maps to 503, and the stakeholder turn + extraction side
    effects are persisted even though no questions could be generated."""
    fx = FakeExtractor(items=[{"statement": "Users can pay by card.", "type": "functional"}])
    monkeypatch.setattr(
        dialogue_mod,
        "_make_generator",
        lambda: FlakyGen(UpstreamUnavailable("Gemini is temporarily overloaded.")),
    )
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: fx)
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        r = await c.post(f"/sessions/{sid}/turns", json={"content": "I want a POS system."}, headers=sh)
        assert r.status_code == 503, r.text
        assert "overloaded" in r.json()["detail"].lower()
        # the stakeholder's reply was persisted before generation failed ...
        turns = (await c.get(f"/sessions/{sid}/turns", headers=sh)).json()
        assert [t["content"] for t in turns if t["role"] == "stakeholder"] == ["I want a POS system."]
        # ... and no orphaned agent turns exist (the batch failed atomically)
        assert all(not t.get("strategy") for t in turns if t["role"] == "agent")
        # the concurrent extraction still completed and persisted
        reqs = [d async for d in get_db().requirements.find({"session_id": sid})]
        assert len(reqs) == 1


@pytest.mark.asyncio
async def test_post_turn_surfaces_unexpected_generation_error(monkeypatch):
    # The 503 degradation must not swallow genuine bugs: a non-upstream error
    # still propagates loudly instead of returning 200 with an empty list.
    monkeypatch.setattr(
        dialogue_mod, "_make_generator", lambda: FlakyGen(RuntimeError("boom"))
    )
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        with pytest.raises(RuntimeError, match="boom"):
            await c.post(f"/sessions/{sid}/turns", json={"content": "hello"}, headers=sh)


@pytest.mark.asyncio
async def test_post_turn_returns_503_on_unparseable_llm_payload(monkeypatch):
    # QuestionParseError is an UpstreamUnavailable, so the same mapping applies.
    monkeypatch.setattr(
        dialogue_mod,
        "_make_generator",
        lambda: FlakyGen(QuestionParseError("Gemini returned an unreadable response.")),
    )
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        r = await c.post(f"/sessions/{sid}/turns", json={"content": "hi"}, headers=sh)
        assert r.status_code == 503, r.text


@pytest.mark.asyncio
async def test_post_question_returns_503_on_unparseable_llm_payload(monkeypatch):
    monkeypatch.setattr(
        dialogue_mod,
        "_make_generator",
        lambda: FlakyGen(QuestionParseError("Gemini returned an unreadable response.")),
    )
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        r = await c.post(f"/sessions/{sid}/questions", headers=sh)
        assert r.status_code == 503, r.text


@pytest.mark.asyncio
async def test_requirement_dedup_across_messages(monkeypatch):
    # Two stakeholder turns whose extractions produce overlapping statements.
    # Turn 1 produces {A, B}; turn 2 produces {A (paraphrased), C}.
    # After both, the DB should hold {A, B, C} — A only once.
    extractors = iter([
        FakeExtractor(items=[
            {"statement": "Users shall be able to pay by card.", "type": "functional"},
            {"statement": "P95 latency below 3s.", "type": "non_functional"},
        ]),
        FakeExtractor(items=[
            {"statement": "users can pay by card", "type": "functional"},  # paraphrase of A
            {"statement": "Audit log retained 90 days.", "type": "constraint"},
        ]),
    ])
    ftg = FakeTitleGen("Dedup Project")
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: next(extractors))
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: ftg)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        await c.post(f"/sessions/{sid}/messages", json={"content": "first"}, headers=sh)
        await c.post(f"/sessions/{sid}/messages", json={"content": "second"}, headers=sh)
        reqs = [d async for d in get_db().requirements.find({"session_id": sid})]
        assert len(reqs) == 3, [r["statement"] for r in reqs]
        statements_lower = {r["statement"].lower().rstrip(".") for r in reqs}
        assert "audit log retained 90 days" in statements_lower
        assert "p95 latency below 3s" in statements_lower
        # the card-payment requirement appears once (under its original wording)
        card_reqs = [r for r in reqs if "card" in r["statement"].lower()]
        assert len(card_reqs) == 1


@pytest.mark.asyncio
async def test_nfr_not_deduped_against_functional_sibling(monkeypatch):
    # A functional behaviour and a non-functional threshold that share most of
    # their words must BOTH survive — dedup is scoped per requirement type.
    # (Token overlap here is ~0.71, which would be dropped by a type-blind dedup.)
    extractors = iter([
        FakeExtractor(items=[
            {"statement": "Users can register a QR code check-in.", "type": "functional"},
        ]),
        FakeExtractor(items=[
            {"statement": "The system must register a QR code check-in within 5 seconds.",
             "type": "non_functional"},
        ]),
    ])
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: next(extractors))
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: FakeTitleGen("QR Project"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _setup_session(c)
        await c.post(f"/sessions/{sid}/messages", json={"content": "qr check-in feature"}, headers=sh)
        await c.post(f"/sessions/{sid}/messages", json={"content": "and it has a speed target"}, headers=sh)
        reqs = [d async for d in get_db().requirements.find({"session_id": sid})]
        types = sorted(r["type"] for r in reqs)
        assert types == ["functional", "non_functional"], [r["statement"] for r in reqs]
