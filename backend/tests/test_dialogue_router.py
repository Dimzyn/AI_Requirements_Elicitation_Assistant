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
        # first call sees [stakeholder], second sees [stakeholder, agent1], third sees [stakeholder, agent1, agent2]
        assert fg.history_lengths == [1, 2, 3]


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
