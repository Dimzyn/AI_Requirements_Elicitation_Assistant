# FYPver2

## Roles & onboarding

The app has two roles: **Requirements Engineer (RE)** and **Stakeholder**.

- Promote a user to RE: `python -m scripts.promote_user <email>` (run inside the backend container).
- The RE creates a **project**, sets its background/goals (used as AI context), and invites stakeholders by email.
- Email is **not** sent automatically (current scope): the invite link is shown on the RE's project page — copy and share it manually. *(Future work: automatic email delivery.)*
- The stakeholder opens the invite link, sets a password, and lands in their interview for that project.
- Each stakeholder has one interview session per project. When elicitation is done, the RE marks the session **ended**; the stakeholder then sees an end-of-interview banner and can no longer send.
- The RE reviews sessions per project (Projects → project detail) and can curate extracted requirements on the spec page.
