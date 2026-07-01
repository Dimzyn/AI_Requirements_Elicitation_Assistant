import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.mongo import get_db
from app.services.export_service import compile_markdown, compile_srs, compile_srs_pdf
from datetime import datetime, timedelta, timezone


def test_compile_markdown_groups_by_type():
    reqs = [
        {"statement": "Users can log in.", "type": "functional"},
        {"statement": "P95 latency < 5s for 1000-word input.", "type": "non_functional"},
    ]
    md = compile_markdown(project_title="Payments", requirements=reqs)
    assert "# Requirements: Payments" in md
    assert "## Functional Requirements" in md
    assert "Users can log in." in md
    assert "## Non-Functional Requirements" in md
    assert "P95 latency" in md


def test_compile_markdown_skips_empty_buckets():
    md = compile_markdown(project_title="Empty", requirements=[])
    assert md.startswith("# Requirements: Empty")
    assert "## Functional Requirements" not in md


async def _re_project_and_session(c, project_title="POS"):
    """Create an RE, project, invite + accept stakeholder, open a session.
    Returns (reh, sh, pid, sid) headers and IDs."""
    await c.post("/auth/signup", json={"email": "re_exp@x.com", "password": "Passw0rd!", "real_name": "RE"})
    await get_db().users.update_one({"email": "re_exp@x.com"}, {"$set": {"role": "requirements_engineer"}})
    re_tok = (await c.post("/auth/login", json={"email": "re_exp@x.com", "password": "Passw0rd!"})).json()["access_token"]
    reh = {"Authorization": f"Bearer {re_tok}"}
    pid = (await c.post("/projects", json={"title": project_title}, headers=reh)).json()["id"]
    token = (await c.post(f"/projects/{pid}/invitations", json={"email": "sh_exp@x.com"}, headers=reh)).json()["token"]
    s_tok = (await c.post(f"/invitations/{token}/accept", json={"password": "Stake123!", "real_name": "S", "job_title": "Stakeholder"})).json()["access_token"]
    sh = {"Authorization": f"Bearer {s_tok}"}
    sid = (await c.post(f"/projects/{pid}/session", headers=sh)).json()["id"]
    return reh, sh, pid, sid


@pytest.mark.asyncio
async def test_export_403_for_stakeholder():
    """Stakeholders are blocked from exporting — only the owning RE may export."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _re_project_and_session(c, project_title="POS")
        await get_db().requirements.insert_one({
            "session_id": sid, "statement": "Cashiers can ring up sales.", "type": "functional"
        })
        r = await c.get(f"/sessions/{sid}/export", headers=sh)
        assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_export_returns_markdown_for_re():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _re_project_and_session(c, project_title="POS")
        await get_db().requirements.insert_one({
            "session_id": sid, "statement": "Cashiers can ring up sales.", "type": "functional"
        })
        r = await c.get(f"/sessions/{sid}/export", headers=reh)
        assert r.status_code == 200, r.text
        assert "# Requirements: POS" in r.text
        assert "Cashiers can ring up sales." in r.text


@pytest.mark.asyncio
async def test_export_txt_strips_markdown_hashes():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _re_project_and_session(c)
        r = await c.get(f"/sessions/{sid}/export?format=txt", headers=reh)
        assert r.status_code == 200
        assert "#" not in r.text


@pytest.mark.asyncio
async def test_export_403_for_non_re_user():
    """A plain (stakeholder-role) outsider gets 403 — only REs may export."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _re_project_and_session(c)
        await c.post("/auth/signup", json={"email": "outsider_exp@x.com", "password": "Passw0rd!", "real_name": "O"})
        out_tok = (await c.post("/auth/login", json={"email": "outsider_exp@x.com", "password": "Passw0rd!"})).json()["access_token"]
        r = await c.get(f"/sessions/{sid}/export", headers={"Authorization": f"Bearer {out_tok}"})
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_export_401_when_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/sessions/507f1f77bcf86cd799439011/export")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_get_requirements_returns_seeded_items():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _re_project_and_session(c)
        base = datetime.now(timezone.utc)
        await get_db().requirements.insert_many([
            {
                "session_id": sid,
                "statement": "Cashiers can ring up sales.",
                "type": "functional",
                "source_turn_id": "turn-1",
                "created_at": base,
            },
            {
                "session_id": sid,
                "statement": "P95 latency below 3s.",
                "type": "non_functional",
                "source_turn_id": "turn-1",
                "created_at": base + timedelta(seconds=1),
            },
        ])
        r = await c.get(f"/sessions/{sid}/requirements", headers=reh)
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body, list)
        assert len(body) == 2
        # ordered by created_at ascending
        assert body[0]["statement"] == "Cashiers can ring up sales."
        assert body[0]["type"] == "functional"
        assert body[0]["source_turn_id"] == "turn-1"
        assert body[0]["created_at"]
        assert body[0]["id"]
        assert body[1]["statement"] == "P95 latency below 3s."
        assert body[1]["type"] == "non_functional"


@pytest.mark.asyncio
async def test_get_requirements_401_when_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/sessions/507f1f77bcf86cd799439011/requirements")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_get_requirements_403_for_non_re_user():
    """A plain (stakeholder-role) outsider gets 403 on GET /sessions/{sid}/requirements."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _re_project_and_session(c)
        await c.post("/auth/signup", json={"email": "outsider2_exp@x.com", "password": "Passw0rd!", "real_name": "O2"})
        out_tok = (await c.post("/auth/login", json={"email": "outsider2_exp@x.com", "password": "Passw0rd!"})).json()["access_token"]
        r = await c.get(f"/sessions/{sid}/requirements", headers={"Authorization": f"Bearer {out_tok}"})
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_get_requirements_403_for_stakeholder():
    """Stakeholders are blocked from listing requirements (403)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _re_project_and_session(c)
        r = await c.get(f"/sessions/{sid}/requirements", headers=sh)
        assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_export_404_for_cross_owner_re():
    """A second RE who does NOT own the project gets 404 on export."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _re_project_and_session(c)
        # Create a second RE (different owner)
        await c.post("/auth/signup", json={"email": "re2_exp@x.com", "password": "Passw0rd!", "real_name": "RE2"})
        await get_db().users.update_one({"email": "re2_exp@x.com"}, {"$set": {"role": "requirements_engineer"}})
        re2_tok = (await c.post("/auth/login", json={"email": "re2_exp@x.com", "password": "Passw0rd!"})).json()["access_token"]
        re2h = {"Authorization": f"Bearer {re2_tok}"}
        r = await c.get(f"/sessions/{sid}/export", headers=re2h)
        assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_get_requirements_404_for_cross_owner_re():
    """A second RE who does NOT own the project gets 404 on GET /sessions/{sid}/requirements."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _re_project_and_session(c)
        # Create a second RE (different owner)
        await c.post("/auth/signup", json={"email": "re3_exp@x.com", "password": "Passw0rd!", "real_name": "RE3"})
        await get_db().users.update_one({"email": "re3_exp@x.com"}, {"$set": {"role": "requirements_engineer"}})
        re3_tok = (await c.post("/auth/login", json={"email": "re3_exp@x.com", "password": "Passw0rd!"})).json()["access_token"]
        re3h = {"Authorization": f"Bearer {re3_tok}"}
        r = await c.get(f"/sessions/{sid}/requirements", headers=re3h)
        assert r.status_code == 404, r.text


# --------------------------------------------------------------------------- #
# SRS export (compile_srs + GET /projects/{pid}/export)                         #
# --------------------------------------------------------------------------- #


def test_compile_srs_has_sections_numbering_and_metadata():
    reqs = [
        {
            "statement": "Users can browse the menu and place an order.",
            "type": "functional", "stakeholder": "Alice", "priority": "must",
            "status": "approved", "acceptance_criteria": "Given a menu, when selecting items, an order is created.",
        },
        {
            "statement": "The system should support up to 50,000 concurrent orders during peak hours.",
            "type": "non_functional", "stakeholder": "Bob", "priority": None,
            "status": "pending", "acceptance_criteria": None,
        },
        {
            "statement": "The system must ship before 2026-08-01.",
            "type": "constraint", "stakeholder": None, "priority": None,
            "status": "pending", "acceptance_criteria": None,
        },
    ]
    md = compile_srs(
        project_title="POS", project_background="A point-of-sale system.",
        project_scope="Phase 1 only.", requirements=reqs,
    )
    assert "# Software Requirements Specification — POS" in md
    assert "## 1. Introduction" in md
    assert "### 1.2 Background" in md and "A point-of-sale system." in md
    assert "### 1.3 Scope" in md and "Phase 1 only." in md
    assert "### 2.1 Functional Requirements" in md
    assert "**FR-1.** Users can browse the menu and place an order." in md
    assert "### 2.2 Non-Functional Requirements" in md
    assert "**NFR-1.** The system should support up to 50,000 concurrent orders during peak hours." in md
    assert "### 2.3 Constraints" in md
    assert "**CON-1.** The system must ship before 2026-08-01." in md
    # metadata sub-line for the first requirement
    assert "Priority: Must" in md
    assert "Source: Alice" in md
    assert "Acceptance: Given a menu" in md


def test_compile_srs_excludes_rejected_and_keeps_numbering():
    reqs = [
        {"statement": "Kept requirement.", "type": "functional", "status": "approved"},
        {"statement": "Rejected requirement.", "type": "functional", "status": "rejected"},
    ]
    md = compile_srs(project_title="P", requirements=reqs)
    assert "**FR-1.** Kept requirement." in md
    assert "Rejected requirement." not in md
    assert "FR-2" not in md  # the rejected one didn't consume a number


def test_compile_srs_empty_shows_placeholders():
    md = compile_srs(project_title="Empty", requirements=[])
    assert "# Software Requirements Specification — Empty" in md
    assert md.count("_None captured._") == 3  # one per requirement section


@pytest.mark.asyncio
async def test_project_export_returns_srs_for_owner():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _re_project_and_session(c, project_title="POS")
        await get_db().requirements.insert_one({
            "session_id": sid, "statement": "Users can place an order.",
            "type": "functional", "status": "approved", "created_at": datetime.now(timezone.utc),
        })
        r = await c.get(f"/projects/{pid}/export", headers=reh)
        assert r.status_code == 200, r.text
        assert "Software Requirements Specification — POS" in r.text
        assert "Users can place an order." in r.text
        assert "Source: S" in r.text  # stakeholder real_name from the helper


@pytest.mark.asyncio
async def test_project_export_excludes_rejected():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _re_project_and_session(c)
        base = datetime.now(timezone.utc)
        await get_db().requirements.insert_many([
            {"session_id": sid, "statement": "Visible req.", "type": "functional", "status": "approved", "created_at": base},
            {"session_id": sid, "statement": "Hidden req.", "type": "functional", "status": "rejected", "created_at": base},
        ])
        r = await c.get(f"/projects/{pid}/export", headers=reh)
        assert r.status_code == 200, r.text
        assert "Visible req." in r.text
        assert "Hidden req." not in r.text


@pytest.mark.asyncio
async def test_project_export_txt_strips_markdown():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _re_project_and_session(c)
        r = await c.get(f"/projects/{pid}/export?format=txt", headers=reh)
        assert r.status_code == 200, r.text
        assert "#" not in r.text and "*" not in r.text


@pytest.mark.asyncio
async def test_project_export_403_for_stakeholder():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _re_project_and_session(c)
        r = await c.get(f"/projects/{pid}/export", headers=sh)
        assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_project_export_404_for_cross_owner_re():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _re_project_and_session(c)
        await c.post("/auth/signup", json={"email": "re4_exp@x.com", "password": "Passw0rd!", "real_name": "RE4"})
        await get_db().users.update_one({"email": "re4_exp@x.com"}, {"$set": {"role": "requirements_engineer"}})
        re4_tok = (await c.post("/auth/login", json={"email": "re4_exp@x.com", "password": "Passw0rd!"})).json()["access_token"]
        re4h = {"Authorization": f"Bearer {re4_tok}"}
        r = await c.get(f"/projects/{pid}/export", headers=re4h)
        assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_project_export_401_when_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/projects/507f1f77bcf86cd799439011/export")
        assert r.status_code == 401, r.text


def test_compile_srs_pdf_returns_pdf_bytes():
    # Includes em dash, ellipsis, and curly quotes to confirm sanitization doesn't crash.
    reqs = [
        {
            "statement": "Users can place an order — quickly.", "type": "functional",
            "stakeholder": "Alice", "priority": "must", "status": "approved",
            "acceptance_criteria": "Given a menu…",
        },
        {"statement": "The system should handle 50,000 orders.", "type": "non_functional", "status": "pending"},
        {"statement": "Dropped.", "type": "functional", "status": "rejected"},
    ]
    pdf = compile_srs_pdf(
        project_title="POS “Pro”", project_background="A POS.", project_scope="Phase 1.", requirements=reqs,
    )
    assert isinstance(pdf, (bytes, bytearray))
    assert bytes(pdf[:5]) == b"%PDF-"
    assert len(pdf) > 500


def test_compile_srs_pdf_handles_empty_requirements():
    pdf = compile_srs_pdf(project_title="Empty", requirements=[])
    assert bytes(pdf[:5]) == b"%PDF-"


@pytest.mark.asyncio
async def test_project_export_pdf_returns_pdf():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _re_project_and_session(c, project_title="POS")
        await get_db().requirements.insert_one({
            "session_id": sid, "statement": "Users can place an order.",
            "type": "functional", "status": "approved", "created_at": datetime.now(timezone.utc),
        })
        r = await c.get(f"/projects/{pid}/export?format=pdf", headers=reh)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/pdf"
        assert r.content[:5] == b"%PDF-"


@pytest.mark.asyncio
async def test_project_export_pdf_403_for_stakeholder():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _re_project_and_session(c)
        r = await c.get(f"/projects/{pid}/export?format=pdf", headers=sh)
        assert r.status_code == 403, r.text
