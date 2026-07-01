from app.db.mongo import get_db


async def _re_project_and_invited_stakeholder(c):
    """Sign up + promote an RE, create a project, invite & accept a stakeholder.
    Returns (re_headers, stakeholder_headers, project_id)."""
    await c.post("/auth/signup", json={"email": "re@x.com", "password": "Passw0rd!", "real_name": "RE"})
    await get_db().users.update_one({"email": "re@x.com"}, {"$set": {"role": "requirements_engineer"}})
    re_tok = (await c.post("/auth/login", json={"email": "re@x.com", "password": "Passw0rd!"})).json()["access_token"]
    reh = {"Authorization": f"Bearer {re_tok}"}
    pid = (await c.post("/projects", json={"title": "P"}, headers=reh)).json()["id"]
    token = (await c.post(f"/projects/{pid}/invitations", json={"email": "s@x.com"}, headers=reh)).json()["token"]
    s_tok = (await c.post(f"/invitations/{token}/accept", json={"password": "Stake123!", "real_name": "S", "job_title": "Stakeholder"})).json()["access_token"]
    sh = {"Authorization": f"Bearer {s_tok}"}
    return reh, sh, pid
