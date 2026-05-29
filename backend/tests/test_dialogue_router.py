import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.routers import dialogue as dialogue_mod
from app.services.question_generator import GeneratedQuestion


class FakeGen:
    def __init__(self):
        self.calls = 0
        self.history_lengths = []

    async def next_question(self, *, phase, summary, history):
        self.calls += 1
        self.history_lengths.append(len(history))
        return GeneratedQuestion(
            question=f"Q{self.calls}: what about X?",
            strategy="concept",
            attempts=1,
            valid=True,
            mistakes=[],
        )


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


async def _signup_login(c, email="a@x.com"):
    await c.post("/auth/signup", json={"email": email, "password": "Passw0rd!", "real_name": "Ada"})
    r = await c.post("/auth/login", json={"email": email, "password": "Passw0rd!"})
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_post_turn_returns_default_5_questions(monkeypatch):
    fg = FakeGen()
    monkeypatch.setattr(dialogue_mod, "_make_generator", lambda: fg)
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        token = await _signup_login(c)
        h = {"Authorization": f"Bearer {token}"}
        sid = (await c.post("/sessions", json={"project_title": "P"}, headers=h)).json()["id"]
        r = await c.post(f"/sessions/{sid}/turns", json={"content": "I want a POS system."}, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["questions"]) == 5
        assert all(q["strategy"] == "concept" for q in body["questions"])
        assert body["stakeholder_turn_id"]


@pytest.mark.asyncio
async def test_count_param_caps_at_10(monkeypatch):
    fg = FakeGen()
    monkeypatch.setattr(dialogue_mod, "_make_generator", lambda: fg)
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        token = await _signup_login(c)
        h = {"Authorization": f"Bearer {token}"}
        sid = (await c.post("/sessions", json={"project_title": "P"}, headers=h)).json()["id"]
        r = await c.post(f"/sessions/{sid}/turns?count=999", json={"content": "x"}, headers=h)
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_history_grows_within_single_request(monkeypatch):
    fg = FakeGen()
    monkeypatch.setattr(dialogue_mod, "_make_generator", lambda: fg)
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        token = await _signup_login(c)
        h = {"Authorization": f"Bearer {token}"}
        sid = (await c.post("/sessions", json={"project_title": "P"}, headers=h)).json()["id"]
        r = await c.post(f"/sessions/{sid}/turns?count=3", json={"content": "hello"}, headers=h)
        assert r.status_code == 200, r.text
        # history starts with the seeded greeting + stakeholder turn, then grows by one
        # agent turn per generated question: [greeting, stakeholder] -> +agent1 -> +agent2
        assert fg.history_lengths == [2, 3, 4]


@pytest.mark.asyncio
async def test_404_on_wrong_user_session(monkeypatch):
    fg = FakeGen()
    monkeypatch.setattr(dialogue_mod, "_make_generator", lambda: fg)
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        token_a = await _signup_login(c, "a@x.com")
        token_b = await _signup_login(c, "b@x.com")
        ha = {"Authorization": f"Bearer {token_a}"}
        hb = {"Authorization": f"Bearer {token_b}"}
        sid_a = (await c.post("/sessions", json={"project_title": "A"}, headers=ha)).json()["id"]
        r = await c.post(f"/sessions/{sid_a}/turns", json={"content": "x"}, headers=hb)
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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        token = await _signup_login(c)
        h = {"Authorization": f"Bearer {token}"}
        sid = (await c.post("/sessions", json={"project_title": "P"}, headers=h)).json()["id"]
        post = await c.post(
            f"/sessions/{sid}/turns",
            json={"content": "I want a POS system."},
            headers=h,
        )
        assert post.status_code == 200, post.text

        r = await c.get(f"/sessions/{sid}/turns", headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        # 1 seeded greeting + 1 stakeholder + 5 agent turns (default count) = 7 total
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
async def test_get_turns_404_for_other_user():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        token_a = await _signup_login(c, "a@x.com")
        token_b = await _signup_login(c, "b@x.com")
        ha = {"Authorization": f"Bearer {token_a}"}
        hb = {"Authorization": f"Bearer {token_b}"}
        sid_a = (await c.post("/sessions", json={"project_title": "A"}, headers=ha)).json()["id"]
        r = await c.get(f"/sessions/{sid_a}/turns", headers=hb)
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_extractor_persists_requirements(monkeypatch):
    fg = FakeGen()
    fx = FakeExtractor(items=[
        {"statement": "Users can pay by card.", "type": "functional"},
        {"statement": "P95 latency below 3s.", "type": "non_functional"},
    ])
    monkeypatch.setattr(dialogue_mod, "_make_generator", lambda: fg)
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: fx)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        token = await _signup_login(c)
        h = {"Authorization": f"Bearer {token}"}
        sid = (await c.post("/sessions", json={"project_title": "POS"}, headers=h)).json()["id"]
        r = await c.post(f"/sessions/{sid}/turns?count=1", json={"content": "I want card payments."}, headers=h)
        assert r.status_code == 200, r.text
        # extractor was called once with the stakeholder content
        assert fx.calls == 1
        # requirements were persisted
        from app.db.mongo import get_db
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
    fx = FakeExtractor(items=[{"statement": "Users can log in.", "type": "functional"}])
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: fx)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        token = await _signup_login(c)
        h = {"Authorization": f"Bearer {token}"}
        sid = (await c.post("/sessions", json={"project_title": "P"}, headers=h)).json()["id"]
        r = await c.post(f"/sessions/{sid}/messages", json={"content": "I want auth."}, headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["stakeholder_turn_id"]
        # session was created with an explicit title, so it is returned unchanged
        assert r.json()["session_title"] == "P"
        # turns persisted: seeded greeting first, then the stakeholder message
        turns = (await c.get(f"/sessions/{sid}/turns", headers=h)).json()
        assert len(turns) == 2
        assert turns[0]["role"] == "agent"
        assert turns[1]["role"] == "stakeholder"
        assert turns[1]["content"] == "I want auth."
        # requirement was extracted
        from app.db.mongo import get_db
        reqs = [d async for d in get_db().requirements.find({"session_id": sid})]
        assert len(reqs) == 1


@pytest.mark.asyncio
async def test_first_message_auto_names_placeholder_session(monkeypatch):
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())
    ftg = FakeTitleGen("Calendar Task Sync")
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: ftg)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        token = await _signup_login(c)
        h = {"Authorization": f"Bearer {token}"}
        # no title -> placeholder, auto_named False
        sid = (await c.post("/sessions", json={}, headers=h)).json()["id"]
        r = await c.post(f"/sessions/{sid}/messages", json={"content": "Sync my todos with Google Calendar."}, headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["session_title"] == "Calendar Task Sync"
        assert ftg.calls == 1
        # the session is renamed in the listing
        sessions = (await c.get("/sessions", headers=h)).json()
        assert sessions[0]["project_title"] == "Calendar Task Sync"
        # a second message does NOT rename again
        r2 = await c.post(f"/sessions/{sid}/messages", json={"content": "Also remind me."}, headers=h)
        assert r2.json()["session_title"] == "Calendar Task Sync"
        assert ftg.calls == 1


@pytest.mark.asyncio
async def test_title_generation_failure_keeps_placeholder(monkeypatch):
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())
    monkeypatch.setattr(dialogue_mod, "_make_title_generator", lambda: BoomTitleGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        token = await _signup_login(c)
        h = {"Authorization": f"Bearer {token}"}
        sid = (await c.post("/sessions", json={}, headers=h)).json()["id"]
        r = await c.post(f"/sessions/{sid}/messages", json={"content": "anything"}, headers=h)
        # reply still succeeds; title falls back to the placeholder
        assert r.status_code == 200, r.text
        assert r.json()["session_title"] == "New conversation"


@pytest.mark.asyncio
async def test_post_message_404_other_user(monkeypatch):
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        ta = await _signup_login(c, "a@x.com")
        tb = await _signup_login(c, "b@x.com")
        sid = (await c.post("/sessions", json={"project_title": "A"}, headers={"Authorization": f"Bearer {ta}"})).json()["id"]
        r = await c.post(f"/sessions/{sid}/messages", json={"content": "x"}, headers={"Authorization": f"Bearer {tb}"})
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_post_question_generates_one_from_history(monkeypatch):
    fg = FakeGen()
    monkeypatch.setattr(dialogue_mod, "_make_generator", lambda: fg)
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: FakeExtractor())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        token = await _signup_login(c)
        h = {"Authorization": f"Bearer {token}"}
        sid = (await c.post("/sessions", json={"project_title": "P"}, headers=h)).json()["id"]
        # seed a stakeholder turn first
        await c.post(f"/sessions/{sid}/messages", json={"content": "I want a POS."}, headers=h)
        # generate one question
        r = await c.post(f"/sessions/{sid}/questions", headers=h)
        assert r.status_code == 200, r.text
        q = r.json()
        assert q["content"].startswith("Q")
        assert q["strategy"] == "concept"
        # verify FakeGen saw history with the seeded greeting + 1 stakeholder turn
        assert fg.history_lengths == [2]


@pytest.mark.asyncio
async def test_post_question_404_other_user(monkeypatch):
    monkeypatch.setattr(dialogue_mod, "_make_generator", lambda: FakeGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        ta = await _signup_login(c, "a@x.com")
        tb = await _signup_login(c, "b@x.com")
        sid = (await c.post("/sessions", json={"project_title": "A"}, headers={"Authorization": f"Bearer {ta}"})).json()["id"]
        r = await c.post(f"/sessions/{sid}/questions", headers={"Authorization": f"Bearer {tb}"})
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_post_message_and_question_401_unauthed():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r1 = await c.post("/sessions/507f1f77bcf86cd799439011/messages", json={"content": "x"})
        r2 = await c.post("/sessions/507f1f77bcf86cd799439011/questions")
        assert r1.status_code == 401
        assert r2.status_code == 401


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
    monkeypatch.setattr(dialogue_mod, "_make_extractor", lambda: next(extractors))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        token = await _signup_login(c)
        h = {"Authorization": f"Bearer {token}"}
        sid = (await c.post("/sessions", json={"project_title": "P"}, headers=h)).json()["id"]
        await c.post(f"/sessions/{sid}/messages", json={"content": "first"}, headers=h)
        await c.post(f"/sessions/{sid}/messages", json={"content": "second"}, headers=h)
        from app.db.mongo import get_db
        reqs = [d async for d in get_db().requirements.find({"session_id": sid})]
        assert len(reqs) == 3, [r["statement"] for r in reqs]
        statements_lower = {r["statement"].lower().rstrip(".") for r in reqs}
        assert "audit log retained 90 days" in statements_lower
        assert "p95 latency below 3s" in statements_lower
        # the card-payment requirement appears once (under its original wording)
        card_reqs = [r for r in reqs if "card" in r["statement"].lower()]
        assert len(card_reqs) == 1
