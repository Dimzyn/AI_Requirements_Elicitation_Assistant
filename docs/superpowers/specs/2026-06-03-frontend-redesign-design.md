# Frontend Redesign — Design Spec

**Date:** 2026-06-03
**Status:** Approved (pending implementation plan)
**Scope:** Visual + light-touch UX redesign of the entire frontend (`frontend/`)

## 1. Goal

Replace the current generic stock-Tailwind styling (slate/indigo, thin borders, no
visual identity) with a cohesive, polished design system in the **"Refined Product"**
direction — crisp, high-contrast, modern SaaS (Linear/Vercel feel): near-black chrome,
tight typography, one confident accent. The redesign covers **all screens** and adds a
**light + dark theme system**.

Behavior, data flow, store logic, API calls, and routing stay **identical**. Changes are
visual plus light UX touches (better empty states, loading/transitions, hover feedback,
tidier layouts).

## 2. Decisions (locked)

| Decision | Choice |
|---|---|
| Visual direction | A — Refined Product (light-first, crisp SaaS) |
| Screens in scope | Everything: Chat (MainPage), Spec (SpecPage), Login, Signup |
| Depth | Polish + UX touches; **no** behavior/data-flow/structure changes |
| Theme | Light default **+ dark mode toggle**, persisted |
| Font | Inter (UI), system fallback |

## 3. Design System

### 3.1 Color tokens (CSS variables)
Defined in `src/index.css` as space-separated RGB channels so Tailwind can apply
`<alpha-value>`. Two themes: `:root` (light) and `[data-theme="dark"]`.

Token set:
- `--background` — app canvas
- `--surface` — cards/panels/header
- `--surface-muted` — subtle fills, chat stream background
- `--border`
- `--foreground` — primary text
- `--muted` — secondary text
- `--accent`, `--accent-foreground` — primary actions, active states
- `--ring` — focus ring
- Status: `--success`, `--danger`, `--warning`, `--info`
- Shadow scale: `--shadow`, `--shadow-lg`

Light values (approx): background `248 250 252`, surface `255 255 255`, border
`226 232 240`, foreground `15 23 42`, muted `100 116 139`, accent `79 70 229`.
Dark values (approx): background `9 11 16`, surface `17 20 27`, border `38 44 56`,
foreground `226 232 240`, muted `148 163 184`, accent `99 102 241`.

(Exact hex from the approved mockup `chat-mockup.html`.)

### 3.2 Tailwind wiring
`tailwind.config.js` maps tokens into `theme.extend.colors` using the
`rgb(var(--token) / <alpha-value>)` pattern so components write `bg-surface`,
`text-foreground`, `text-muted`, `border-border`, `bg-accent`, `text-success`, etc.
This avoids `dark:` variant duplication — themes swap by variable. Also extend
`fontFamily.sans` to lead with Inter, and add the radius/shadow scale.

### 3.3 Theme toggle
- New `src/store/themeStore.ts` (zustand): `theme: 'light' | 'dark'`, `toggle()`,
  persisted to `localStorage` (key `theme`). On change, sets `data-theme` on
  `document.documentElement`.
- Inline no-flash script in `index.html` `<head>` reads `localStorage.theme` (defaulting
  to light) and sets `data-theme` before React mounts, preventing a flash.
- Inter loaded via Google Fonts `<link>` in `index.html`.

### 3.4 UI primitives
New `src/components/ui/`, kept deliberately small:
- `Button.tsx` — variants `primary | ghost | subtle | danger`, sizes `sm | md`.
- `Badge.tsx` — variants for requirement status, strategy chips, type/priority tags.

Everything else remains inline Tailwind using the tokens. Goal: kill repeated class-soup
across the ~8 buttons and many status pills without a heavy refactor.

### 3.5 Shared app chrome
New `src/components/AppHeader.tsx` used by both MainPage and SpecPage (header is currently
duplicated). Contains: brand mark + product name, a role indicator chip, the theme toggle,
and logout. Page-specific title text passed as a prop.

## 4. Per-screen changes (behavior unchanged)

### 4.1 Auth — `LoginPage`, `SignupPage`
Centered card on a subtly accent-tinted canvas, brand mark + product name above the form,
labeled inputs with focus rings, styled error banner, primary submit button, consistent
alt-action link. Both pages share the same visual structure.

Fields are kept exactly as today (no new fields, no role selector — role is server-assigned):
- **Login:** email, password.
- **Signup:** email, password, **real name** (required), **phone** (optional).

### 4.2 Chat — `MainPage` + children
- **`MainPage`** — adopt `AppHeader`; keep the `grid-rows-[auto_1fr]` +
  `grid-cols-[sidebar_main_reqs]` structure and the existing draft-welcome effect.
- **`SessionList`** — refined rows with active accent bar, status dots (active=success,
  archived=muted), hover-revealed Archive/Restore/Delete actions, Active/Archived section
  headers, restyled "New Session" button, empty states. Same handlers and `confirm()` flow.
- **`ChatPanel`** — restyled AI vs stakeholder bubbles (asymmetric radii), strategy chips
  via `Badge` using the existing `STRATEGY_DISPLAY` map (re-expressed in tokens), a
  welcoming greeting/empty hero, auto-scroll preserved.
- **`StatusIndicator`** — animated three-dot typing indicator with the existing
  validating/thinking labels.
- **`InputBox`** — unified rounded composer with focus-within ring, textarea + Send,
  tidied "Qs per turn" select, styled error banner, archived-session notice. All send /
  optimistic / error-rollback logic untouched.
- **`LiveRequirements`** — requirements grouped into bordered cards by type with a header
  label + count badge, optional priority tag per item, export controls, empty state. Same
  grouping reduce and export-blob logic.

### 4.3 Spec — `SpecPage`
Adopt `AppHeader`. Styled filter bar with refined selects; cleaner requirements table
(zebra rows, sticky header, hover + selected-row states); status as pills and type/priority
as `Badge`s; the `EditDrawer` reworked into a polished panel with labeled fields and a
sticky save bar. Filtering, fetching, and patch logic untouched.

## 5. Out of scope (YAGNI)

- No new features, routes, store fields, API calls, or backend changes.
- No data-flow or interaction-logic changes.
- No full mobile/responsive rework — desktop-first; existing fixed-width panels kept.
- No component library / heavy abstraction beyond the two small primitives.

## 6. Files touched

**New:** `src/store/themeStore.ts`, `src/components/ui/Button.tsx`,
`src/components/ui/Badge.tsx`, `src/components/AppHeader.tsx`.
**Modified:** `index.html`, `src/index.css`, `tailwind.config.js`, `src/pages/MainPage.tsx`,
`src/pages/SpecPage.tsx`, `src/pages/LoginPage.tsx`, `src/pages/SignupPage.tsx`,
`src/components/Sidebar/SessionList.tsx`, `src/components/Dialogue/ChatPanel.tsx`,
`src/components/Dialogue/InputBox.tsx`, `src/components/Dialogue/StatusIndicator.tsx`,
`src/components/Requirements/LiveRequirements.tsx`.
**Unchanged:** all `src/api/*`, all `src/store/*` except the new `themeStore`, `App.tsx`,
`ProtectedRoute.tsx`, `constants.ts`, all existing tests.

## 7. Verification

- `npm run build` (tsc -b + vite build) passes.
- `npm run test` (vitest) — existing store tests stay green (no store changes).
- `npm run lint` passes.
- Manual visual check of all four screens in **both** light and dark themes, including:
  empty states, active/archived sessions, strategy chips, typing indicator, edit drawer,
  and theme persistence across reload (no flash).
