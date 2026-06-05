# Frontend Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the entire frontend in the "Refined Product" direction with a light + dark theme system, preserving all behavior and data flow.

**Architecture:** Introduce semantic color tokens as CSS variables (light in `:root`, dark in `[data-theme="dark"]`), wired into Tailwind via the `rgb(var(--token) / <alpha-value>)` pattern so components use classes like `bg-surface text-foreground border-border`. A small `themeStore` (zustand) toggles `data-theme` on `<html>` and persists to `localStorage`; an inline no-flash script applies it before React mounts. Two tiny UI primitives (`Button`, `Badge`) and a shared `AppHeader` cut duplication. Each screen is then restyled to use the tokens.

**Tech Stack:** React 19, TypeScript, Vite, Tailwind 3.4, Zustand 5, Vitest (node env).

**Reference mockups (committed under `.superpowers/brainstorm/.../content/`, gitignored — open in a browser):** `chat-mockup.html` (chat page, both themes), `auth-mockup-v2.html` (login + signup). These are the visual source of truth for spacing, color, and component shape.

**Testing note:** Vitest runs in the `node` environment (no jsdom), so this repo unit-tests logic only; React components are verified by `npm run build` (type-check), `npm run lint`, and manual visual inspection — consistent with the existing test suite. The only new logic unit (`themeStore`) gets real TDD.

**Per-task definition of done:** `npm run build` and `npm run lint` pass, and (where noted) `npm run test` passes. Run all commands from `frontend/`.

---

## File Structure

**New files:**
- `frontend/src/store/themeStore.ts` — theme state (light/dark), persistence, applies `data-theme`.
- `frontend/src/store/themeStore.test.ts` — unit tests for themeStore.
- `frontend/src/components/ui/Button.tsx` — button primitive (variants/sizes).
- `frontend/src/components/ui/Badge.tsx` — badge/pill primitive (status, strategy, type/priority).
- `frontend/src/components/AppHeader.tsx` — shared top bar (brand, role, theme toggle, logout).

**Modified files:**
- `frontend/index.html` — Inter font link, no-flash theme script, title.
- `frontend/src/index.css` — token definitions + base layer.
- `frontend/tailwind.config.js` — map tokens to colors, fonts, radius, shadows.
- `frontend/src/pages/LoginPage.tsx`, `SignupPage.tsx` — auth restyle.
- `frontend/src/pages/MainPage.tsx`, `SpecPage.tsx` — adopt `AppHeader`, restyle.
- `frontend/src/components/Sidebar/SessionList.tsx`
- `frontend/src/components/Dialogue/ChatPanel.tsx`, `InputBox.tsx`, `StatusIndicator.tsx`
- `frontend/src/components/Requirements/LiveRequirements.tsx`

**Unchanged:** all `src/api/*`, `src/store/{authStore,sessionStore,specStore}.ts`, `App.tsx`, `ProtectedRoute.tsx`, `constants.ts`, existing tests.

---

## Task 1: Theme tokens, Tailwind wiring, fonts, no-flash script

**Files:**
- Modify: `frontend/src/index.css`
- Modify: `frontend/tailwind.config.js`
- Modify: `frontend/index.html`

- [ ] **Step 1: Replace `src/index.css` with token definitions**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 248 250 252;
    --surface: 255 255 255;
    --surface-muted: 248 250 252;
    --border: 226 232 240;
    --foreground: 15 23 42;
    --muted: 100 116 139;
    --accent: 79 70 229;
    --accent-foreground: 255 255 255;
    --ring: 79 70 229;
    --success: 16 185 129;
    --danger: 225 29 72;
    --warning: 217 119 6;
    --info: 37 99 235;
  }

  [data-theme="dark"] {
    --background: 9 11 16;
    --surface: 17 20 27;
    --surface-muted: 22 26 35;
    --border: 38 44 56;
    --foreground: 226 232 240;
    --muted: 148 163 184;
    --accent: 99 102 241;
    --accent-foreground: 255 255 255;
    --ring: 129 140 248;
    --success: 52 211 153;
    --danger: 251 113 133;
    --warning: 245 158 11;
    --info: 96 165 250;
  }

  html {
    font-family: "Inter", system-ui, sans-serif;
  }

  body {
    @apply bg-background text-foreground;
    -webkit-font-smoothing: antialiased;
  }
}
```

- [ ] **Step 2: Replace `tailwind.config.js` to map tokens**

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        background: 'rgb(var(--background) / <alpha-value>)',
        surface: {
          DEFAULT: 'rgb(var(--surface) / <alpha-value>)',
          muted: 'rgb(var(--surface-muted) / <alpha-value>)',
        },
        border: 'rgb(var(--border) / <alpha-value>)',
        foreground: 'rgb(var(--foreground) / <alpha-value>)',
        muted: 'rgb(var(--muted) / <alpha-value>)',
        accent: {
          DEFAULT: 'rgb(var(--accent) / <alpha-value>)',
          foreground: 'rgb(var(--accent-foreground) / <alpha-value>)',
        },
        ring: 'rgb(var(--ring) / <alpha-value>)',
        success: 'rgb(var(--success) / <alpha-value>)',
        danger: 'rgb(var(--danger) / <alpha-value>)',
        warning: 'rgb(var(--warning) / <alpha-value>)',
        info: 'rgb(var(--info) / <alpha-value>)',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 2px rgb(15 23 42 / 0.06), 0 1px 3px rgb(15 23 42 / 0.04)',
        lift: '0 10px 30px -12px rgb(15 23 42 / 0.25)',
      },
    },
  },
  plugins: [],
}
```

- [ ] **Step 3: Update `index.html`** — add the no-flash script in `<head>` (before the module script), the Inter font link, and a real title.

Replace the contents of `<head>` with:

```html
<head>
  <meta charset="UTF-8" />
  <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Probing Generator</title>
  <script>
    (function () {
      try {
        if (localStorage.getItem('theme') === 'dark') {
          document.documentElement.setAttribute('data-theme', 'dark');
        }
      } catch (e) {}
    })();
  </script>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link
    href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
    rel="stylesheet"
  />
</head>
```

- [ ] **Step 4: Verify build + lint**

Run: `npm run build && npm run lint`
Expected: both succeed (the app still renders with default light tokens; no visual classes consume them yet, that's fine).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/index.css frontend/tailwind.config.js frontend/index.html
git commit -m "feat(frontend): add light/dark color tokens and Inter font"
```

---

## Task 2: themeStore (TDD)

**Files:**
- Create: `frontend/src/store/themeStore.ts`
- Test: `frontend/src/store/themeStore.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/store/themeStore.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from "vitest";

// Fresh DOM/storage stubs per test; store reads them at import time.
function stubEnv(initialTheme?: string) {
  const storage: Record<string, string> = {};
  if (initialTheme) storage["theme"] = initialTheme;
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => storage[k] ?? null,
    setItem: (k: string, v: string) => {
      storage[k] = v;
    },
    removeItem: (k: string) => {
      delete storage[k];
    },
  });
  const attrs: Record<string, string> = {};
  vi.stubGlobal("document", {
    documentElement: {
      setAttribute: (k: string, v: string) => {
        attrs[k] = v;
      },
      removeAttribute: (k: string) => {
        delete attrs[k];
      },
      getAttribute: (k: string) => attrs[k] ?? null,
    },
  });
}

describe("themeStore", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.unstubAllGlobals();
  });

  it("defaults to light when nothing is stored", async () => {
    stubEnv();
    const { useThemeStore } = await import("./themeStore");
    expect(useThemeStore.getState().theme).toBe("light");
  });

  it("initializes from a stored dark preference", async () => {
    stubEnv("dark");
    const { useThemeStore } = await import("./themeStore");
    expect(useThemeStore.getState().theme).toBe("dark");
  });

  it("toggle flips theme, persists, and sets data-theme", async () => {
    stubEnv();
    const { useThemeStore } = await import("./themeStore");
    useThemeStore.getState().toggle();
    expect(useThemeStore.getState().theme).toBe("dark");
    expect(localStorage.getItem("theme")).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    useThemeStore.getState().toggle();
    expect(useThemeStore.getState().theme).toBe("light");
    expect(localStorage.getItem("theme")).toBe("light");
    expect(document.documentElement.getAttribute("data-theme")).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- themeStore`
Expected: FAIL — cannot resolve `./themeStore`.

- [ ] **Step 3: Implement `frontend/src/store/themeStore.ts`**

```ts
import { create } from "zustand";

type Theme = "light" | "dark";

function readInitial(): Theme {
  try {
    return localStorage.getItem("theme") === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

function apply(theme: Theme) {
  if (typeof document === "undefined") return;
  const el = document.documentElement;
  if (theme === "dark") el.setAttribute("data-theme", "dark");
  else el.removeAttribute("data-theme");
}

type ThemeState = {
  theme: Theme;
  setTheme: (t: Theme) => void;
  toggle: () => void;
};

export const useThemeStore = create<ThemeState>((set, get) => ({
  theme: readInitial(),
  setTheme: (theme) => {
    try {
      localStorage.setItem("theme", theme);
    } catch {
      /* ignore */
    }
    apply(theme);
    set({ theme });
  },
  toggle: () => get().setTheme(get().theme === "dark" ? "light" : "dark"),
}));
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- themeStore`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/store/themeStore.ts frontend/src/store/themeStore.test.ts
git commit -m "feat(frontend): add themeStore with light/dark toggle and persistence"
```

---

## Task 3: UI primitives — Button and Badge

**Files:**
- Create: `frontend/src/components/ui/Button.tsx`
- Create: `frontend/src/components/ui/Badge.tsx`

- [ ] **Step 1: Create `frontend/src/components/ui/Button.tsx`**

```tsx
import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "ghost" | "subtle" | "danger";
type Size = "sm" | "md";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-accent text-accent-foreground shadow-sm hover:brightness-110 disabled:bg-accent/40",
  ghost:
    "border border-border text-foreground hover:bg-surface-muted disabled:opacity-40",
  subtle:
    "text-muted hover:bg-surface-muted hover:text-foreground disabled:opacity-40",
  danger:
    "border border-transparent text-danger hover:bg-danger hover:text-white disabled:opacity-40",
};

const SIZES: Record<Size, string> = {
  sm: "text-xs px-2.5 py-1 rounded-md",
  md: "text-sm px-4 py-2 rounded-lg",
};

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
};

export default function Button({
  variant = "primary",
  size = "md",
  className = "",
  ...rest
}: Props) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-1.5 font-medium transition focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 disabled:cursor-not-allowed ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...rest}
    />
  );
}
```

- [ ] **Step 2: Create `frontend/src/components/ui/Badge.tsx`**

```tsx
import type { ReactNode } from "react";

export type BadgeTone =
  | "neutral"
  | "accent"
  | "success"
  | "danger"
  | "warning"
  | "info";

const TONES: Record<BadgeTone, string> = {
  neutral: "bg-surface-muted text-muted",
  accent: "bg-accent/12 text-accent",
  success: "bg-success/15 text-success",
  danger: "bg-danger/15 text-danger",
  warning: "bg-warning/16 text-warning",
  info: "bg-info/14 text-info",
};

export default function Badge({
  tone = "neutral",
  className = "",
  children,
}: {
  tone?: BadgeTone;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold leading-none ${TONES[tone]} ${className}`}
    >
      {children}
    </span>
  );
}
```

- [ ] **Step 3: Verify build + lint**

Run: `npm run build && npm run lint`
Expected: both pass (components compile; unused-for-now is fine since they're exported modules, but if lint flags no-unused you will consume them in later tasks — they are not imported yet, which is allowed for module files).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ui/Button.tsx frontend/src/components/ui/Badge.tsx
git commit -m "feat(frontend): add Button and Badge UI primitives"
```

---

## Task 4: Shared AppHeader with theme toggle

**Files:**
- Create: `frontend/src/components/AppHeader.tsx`

- [ ] **Step 1: Create `frontend/src/components/AppHeader.tsx`**

```tsx
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/authStore";
import { useThemeStore } from "../store/themeStore";
import Button from "./ui/Button";

export default function AppHeader({ title }: { title: string }) {
  const clear = useAuthStore((s) => s.clear);
  const role = useAuthStore((s) => s.role);
  const theme = useThemeStore((s) => s.theme);
  const toggle = useThemeStore((s) => s.toggle);
  const nav = useNavigate();

  const roleLabel =
    role === "requirements_engineer"
      ? "Requirements Engineer"
      : role === "stakeholder"
        ? "Stakeholder"
        : null;

  return (
    <header className="flex h-13 items-center gap-3 border-b border-border bg-surface px-4 py-2">
      <span className="grid h-7 w-7 place-items-center rounded-lg bg-accent text-sm text-accent-foreground shadow-sm">
        ◆
      </span>
      <h1 className="font-semibold text-foreground">{title}</h1>
      {roleLabel && (
        <span className="rounded-full border border-border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted">
          {roleLabel}
        </span>
      )}
      <div className="flex-1" />
      <button
        onClick={toggle}
        title="Toggle theme"
        aria-label="Toggle theme"
        className="grid h-8 w-8 place-items-center rounded-lg border border-border text-muted transition hover:bg-surface-muted hover:text-foreground"
      >
        {theme === "dark" ? "☀" : "☾"}
      </button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => {
          clear();
          nav("/login");
        }}
      >
        Log out
      </Button>
    </header>
  );
}
```

Note: `h-13` is not a default Tailwind class. Add it via arbitrary value — use `h-[52px]` instead of `h-13` in the header className.

Correct the header line to:

```tsx
    <header className="flex h-[52px] items-center gap-3 border-b border-border bg-surface px-4 py-2">
```

- [ ] **Step 2: Verify build + lint**

Run: `npm run build && npm run lint`
Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/AppHeader.tsx
git commit -m "feat(frontend): add shared AppHeader with theme toggle"
```

---

## Task 5: Restyle auth pages (Login + Signup)

**Files:**
- Modify: `frontend/src/pages/LoginPage.tsx`
- Modify: `frontend/src/pages/SignupPage.tsx`

Visual reference: `auth-mockup-v2.html`. Keep all state, handlers, and fields unchanged — only markup/classes change.

- [ ] **Step 1: Replace the `return (...)` JSX in `LoginPage.tsx`**

Keep all hooks/handlers above `return` exactly as-is. Replace only the returned JSX with:

```tsx
  return (
    <div className="grid min-h-screen place-items-center bg-background bg-[radial-gradient(700px_360px_at_18%_-8%,rgb(var(--accent)/0.10),transparent_60%),radial-gradient(600px_340px_at_100%_110%,rgb(124_58_237/0.08),transparent_60%)] p-6">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm rounded-2xl border border-border bg-surface p-8 shadow-lift"
      >
        <div className="mb-1 flex items-center justify-center gap-2.5">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-accent text-lg text-accent-foreground shadow-sm">
            ◆
          </span>
          <span className="font-semibold text-foreground">Probing Generator</span>
        </div>
        <h1 className="mt-3 text-center text-xl font-semibold text-foreground">
          Welcome back
        </h1>
        <p className="mb-6 mt-2 text-center text-sm text-muted">
          Sign in to continue your requirements interviews.
        </p>

        <label className="mb-1.5 mt-3 block text-xs font-semibold text-muted">
          Email
        </label>
        <input
          className="w-full rounded-lg border border-border bg-surface px-3 py-2.5 text-sm text-foreground transition placeholder:text-muted/70 focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20"
          placeholder="you@company.com"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />

        <label className="mb-1.5 mt-3.5 block text-xs font-semibold text-muted">
          Password
        </label>
        <input
          className="w-full rounded-lg border border-border bg-surface px-3 py-2.5 text-sm text-foreground transition placeholder:text-muted/70 focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20"
          placeholder="••••••••"
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        {err && (
          <div className="mt-3.5 rounded-lg border border-danger/25 bg-danger/10 px-3 py-2 text-sm text-danger">
            {err}
          </div>
        )}

        <button
          type="submit"
          className="mt-5 w-full rounded-lg bg-accent py-2.5 text-sm font-semibold text-accent-foreground shadow-sm transition hover:brightness-110"
        >
          Sign in
        </button>

        <p className="mt-4 text-center text-sm text-muted">
          Don't have an account?{" "}
          <Link to="/signup" className="font-semibold text-accent hover:underline">
            Create one
          </Link>
        </p>
      </form>
    </div>
  );
```

- [ ] **Step 2: Replace the `return (...)` JSX in `SignupPage.tsx`**

Keep all hooks/handlers and the four fields (email, password, realName, phone) exactly. Replace only the returned JSX with:

```tsx
  return (
    <div className="grid min-h-screen place-items-center bg-background bg-[radial-gradient(700px_360px_at_18%_-8%,rgb(var(--accent)/0.10),transparent_60%),radial-gradient(600px_340px_at_100%_110%,rgb(124_58_237/0.08),transparent_60%)] p-6">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm rounded-2xl border border-border bg-surface p-8 shadow-lift"
      >
        <div className="mb-1 flex items-center justify-center gap-2.5">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-accent text-lg text-accent-foreground shadow-sm">
            ◆
          </span>
          <span className="font-semibold text-foreground">Probing Generator</span>
        </div>
        <h1 className="mt-3 text-center text-xl font-semibold text-foreground">
          Create your account
        </h1>
        <p className="mb-6 mt-2 text-center text-sm text-muted">
          Start eliciting requirements with AI-guided probing.
        </p>

        <label className="mb-1.5 mt-3 block text-xs font-semibold text-muted">Email</label>
        <input
          className="w-full rounded-lg border border-border bg-surface px-3 py-2.5 text-sm text-foreground transition placeholder:text-muted/70 focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20"
          placeholder="you@company.com"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />

        <label className="mb-1.5 mt-3.5 block text-xs font-semibold text-muted">Password</label>
        <input
          className="w-full rounded-lg border border-border bg-surface px-3 py-2.5 text-sm text-foreground transition placeholder:text-muted/70 focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20"
          placeholder="••••••••"
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        <label className="mb-1.5 mt-3.5 block text-xs font-semibold text-muted">Full name</label>
        <input
          className="w-full rounded-lg border border-border bg-surface px-3 py-2.5 text-sm text-foreground transition placeholder:text-muted/70 focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20"
          placeholder="Jane Doe"
          required
          value={realName}
          onChange={(e) => setRealName(e.target.value)}
        />

        <label className="mb-1.5 mt-3.5 block text-xs font-semibold text-muted">
          Phone <span className="font-normal normal-case">(optional)</span>
        </label>
        <input
          className="w-full rounded-lg border border-border bg-surface px-3 py-2.5 text-sm text-foreground transition placeholder:text-muted/70 focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20"
          placeholder="+60 12-345 6789"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
        />

        {err && (
          <div className="mt-3.5 rounded-lg border border-danger/25 bg-danger/10 px-3 py-2 text-sm text-danger">
            {err}
          </div>
        )}

        <button
          type="submit"
          className="mt-5 w-full rounded-lg bg-accent py-2.5 text-sm font-semibold text-accent-foreground shadow-sm transition hover:brightness-110"
        >
          Create account
        </button>

        <p className="mt-4 text-center text-sm text-muted">
          Already have an account?{" "}
          <Link to="/login" className="font-semibold text-accent hover:underline">
            Sign in
          </Link>
        </p>
      </form>
    </div>
  );
```

- [ ] **Step 3: Verify build + lint, then manual check**

Run: `npm run build && npm run lint`
Expected: pass. Then `npm run dev`, visit `/login` and `/signup`, toggle the OS/localStorage theme by running `localStorage.setItem('theme','dark')` in devtools + reload to confirm dark tokens apply.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/LoginPage.tsx frontend/src/pages/SignupPage.tsx
git commit -m "feat(frontend): restyle login and signup pages"
```

---

## Task 6: MainPage shell + SessionList

**Files:**
- Modify: `frontend/src/pages/MainPage.tsx`
- Modify: `frontend/src/components/Sidebar/SessionList.tsx`

Visual reference: `chat-mockup.html` (header + left sidebar).

- [ ] **Step 1: Update `MainPage.tsx` to use AppHeader and token background**

Keep the `useEffect` draft logic unchanged. Replace the component body's `return` with:

```tsx
  return (
    <div className="grid h-screen grid-rows-[auto_1fr] bg-background">
      <AppHeader title="Probing Generator" />
      <div className="grid grid-cols-[248px_1fr_312px] overflow-hidden">
        <SessionList />
        <main className="flex flex-col overflow-hidden bg-surface-muted">
          <ChatPanel />
          <InputBox />
        </main>
        <LiveRequirements />
      </div>
    </div>
  );
```

Add the import at the top and remove the now-unused `useAuthStore`/`useNavigate` imports and the local `clear`/`nav` (logout now lives in AppHeader). Final import block:

```tsx
import { useEffect } from "react";
import { useSessionStore } from "../store/sessionStore";
import SessionList from "../components/Sidebar/SessionList";
import ChatPanel from "../components/Dialogue/ChatPanel";
import InputBox from "../components/Dialogue/InputBox";
import LiveRequirements from "../components/Requirements/LiveRequirements";
import AppHeader from "../components/AppHeader";
```

And the component reduces to just the `useEffect` + `return` (no `clear`/`nav`):

```tsx
export default function MainPage() {
  useEffect(() => {
    const { activeId, draft, setDraft } = useSessionStore.getState();
    if (!activeId && !draft) setDraft(true);
  }, []);

  return (
    /* the JSX above */
  );
}
```

- [ ] **Step 2: Restyle `SessionList.tsx`**

Keep all hooks, `refresh`, `onArchive`, `onUnarchive`, `onDelete`, and the `active`/`archived` split unchanged. Replace the returned JSX with token-based markup:

```tsx
  return (
    <aside className="flex flex-col border-r border-border bg-surface">
      <div className="border-b border-border p-3.5">
        <button
          onClick={() => setDraft(true)}
          disabled={draft && !activeId}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-accent py-2 text-sm font-medium text-accent-foreground shadow-sm transition hover:brightness-110 disabled:bg-accent/40"
        >
          <span className="text-base leading-none">＋</span> New Session
        </button>
      </div>
      <div className="flex-1 space-y-5 overflow-y-auto p-3 text-sm">
        <div>
          <h3 className="mb-2 px-1 text-[10px] font-semibold uppercase tracking-wider text-muted">
            Active
          </h3>
          <ul className="space-y-0.5">
            {active.length === 0 && (
              <li className="px-2 italic text-muted">No active sessions</li>
            )}
            {active.map((s) => (
              <li key={s.id}>
                <div
                  onClick={() => setActive(s.id)}
                  className={`group relative flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-2 transition ${
                    activeId === s.id
                      ? "bg-accent/10 text-accent before:absolute before:left-0 before:top-1.5 before:bottom-1.5 before:w-[3px] before:rounded-full before:bg-accent"
                      : "hover:bg-surface-muted"
                  }`}
                >
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-success" />
                  <span className="flex-1 truncate font-medium">{s.project_title}</span>
                  <button
                    onClick={(e) => onArchive(s.id, e)}
                    disabled={busyId === s.id}
                    className="rounded-md border border-border px-1.5 py-0.5 text-[10px] text-muted opacity-0 transition hover:bg-surface hover:text-foreground group-hover:opacity-100 disabled:opacity-40"
                    title="Archive session"
                  >
                    Archive
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
        {archived.length > 0 && (
          <div>
            <h3 className="mb-2 px-1 text-[10px] font-semibold uppercase tracking-wider text-muted">
              Archived
            </h3>
            <ul className="space-y-0.5">
              {archived.map((s) => (
                <li key={s.id}>
                  <div
                    onClick={() => setActive(s.id)}
                    className={`group flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-2 text-muted transition ${
                      activeId === s.id ? "bg-surface-muted" : "hover:bg-surface-muted"
                    }`}
                  >
                    <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-border" />
                    <span className="flex-1 truncate">{s.project_title}</span>
                    <button
                      onClick={(e) => onUnarchive(s.id, e)}
                      disabled={busyId === s.id}
                      className="rounded-md border border-border px-1.5 py-0.5 text-[10px] text-muted opacity-0 transition hover:bg-surface hover:text-success group-hover:opacity-100 disabled:opacity-40"
                      title="Restore to active"
                    >
                      Restore
                    </button>
                    <button
                      onClick={(e) => onDelete(s.id, s.project_title, e)}
                      disabled={busyId === s.id}
                      className="rounded-md border border-transparent px-1.5 py-0.5 text-[10px] text-danger opacity-0 transition hover:bg-danger hover:text-white group-hover:opacity-100 disabled:opacity-40"
                      title="Permanently delete"
                    >
                      Delete
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </aside>
  );
```

- [ ] **Step 3: Verify build + lint**

Run: `npm run build && npm run lint`
Expected: pass (no unused imports left in MainPage).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/MainPage.tsx frontend/src/components/Sidebar/SessionList.tsx
git commit -m "feat(frontend): restyle main shell and session list"
```

---

## Task 7: ChatPanel + StatusIndicator

**Files:**
- Modify: `frontend/src/components/Dialogue/ChatPanel.tsx`
- Modify: `frontend/src/components/Dialogue/StatusIndicator.tsx`

Visual reference: `chat-mockup.html` (center column).

- [ ] **Step 1: Update the `STRATEGY_DISPLAY` map in `ChatPanel.tsx` to Badge tones**

Replace the map and its usage so strategy chips use `Badge`. New top section:

```tsx
import { useEffect, useRef } from "react";
import { useSessionStore } from "../../store/sessionStore";
import { GREETING } from "../../constants";
import StatusIndicator from "./StatusIndicator";
import Badge, { type BadgeTone } from "../ui/Badge";

const STRATEGY_DISPLAY: Record<string, { label: string; tone: BadgeTone }> = {
  concept: { label: "Drilling deeper", tone: "info" },
  related_concept: { label: "Broadening scope", tone: "accent" },
  general: { label: "Clarifying", tone: "neutral" },
  nfr_probe: { label: "Probing NFRs", tone: "warning" },
  pivot: { label: "Pivoting topic", tone: "success" },
};
```

- [ ] **Step 2: Replace the three returned branches in `ChatPanel.tsx`**

Draft welcome branch:

```tsx
  if (turns.length === 0 && draft) {
    return (
      <div className="flex-1 space-y-3 overflow-y-auto p-6">
        <div className="flex justify-start">
          <div className="max-w-[74%] whitespace-pre-wrap rounded-2xl rounded-bl-sm border border-border bg-surface px-4 py-2.5 text-sm text-foreground shadow-card">
            {GREETING}
          </div>
        </div>
      </div>
    );
  }

  if (turns.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center px-6 text-center text-sm text-muted">
        Describe what you want to build to start the interview.
      </div>
    );
  }

  return (
    <div className="flex-1 space-y-3.5 overflow-y-auto p-6">
      {turns.map((t) => (
        <div
          key={t.id}
          data-role={t.role}
          className={`flex ${t.role === "stakeholder" ? "justify-end" : "justify-start"}`}
        >
          <div
            className={`max-w-[74%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm shadow-card ${
              t.role === "stakeholder"
                ? "rounded-br-sm bg-accent text-accent-foreground"
                : "rounded-bl-sm border border-border bg-surface text-foreground"
            }`}
          >
            {t.role === "agent" && t.strategy && (
              <Badge
                tone={STRATEGY_DISPLAY[t.strategy]?.tone ?? "neutral"}
                className="mb-1.5"
              >
                {STRATEGY_DISPLAY[t.strategy]?.label ?? t.strategy}
              </Badge>
            )}
            {t.content}
          </div>
        </div>
      ))}
      <div className="pt-2">
        <StatusIndicator />
      </div>
      <div ref={bottomRef} />
    </div>
  );
```

Note: when the agent bubble has a Badge, render it on its own line — wrap `{t.content}` so the badge sits above. Change the badge+content block to:

```tsx
            {t.role === "agent" && t.strategy && (
              <div>
                <Badge tone={STRATEGY_DISPLAY[t.strategy]?.tone ?? "neutral"} className="mb-1.5">
                  {STRATEGY_DISPLAY[t.strategy]?.label ?? t.strategy}
                </Badge>
              </div>
            )}
            {t.content}
```

- [ ] **Step 3: Restyle `StatusIndicator.tsx` with an animated dot indicator**

```tsx
import { useSessionStore } from "../../store/sessionStore";

export default function StatusIndicator() {
  const status = useSessionStore((s) => s.status);
  if (status === "idle") return null;
  const label =
    status === "thinking"
      ? "Generating probing question…"
      : "Validating question relevance…";
  return (
    <div className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1.5 text-xs text-muted shadow-card">
      <span className="flex gap-1">
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent [animation-delay:-0.2s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent [animation-delay:-0.1s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent" />
      </span>
      {label}
    </div>
  );
}
```

- [ ] **Step 4: Verify build + lint**

Run: `npm run build && npm run lint`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Dialogue/ChatPanel.tsx frontend/src/components/Dialogue/StatusIndicator.tsx
git commit -m "feat(frontend): restyle chat panel and typing indicator"
```

---

## Task 8: InputBox composer

**Files:**
- Modify: `frontend/src/components/Dialogue/InputBox.tsx`

Visual reference: `chat-mockup.html` (composer). Keep ALL logic (`onSend`, optimistic turns, error rollback, `describeError`, archived check, counts) unchanged — change only the three returned JSX blocks.

- [ ] **Step 1: Replace the archived-session return block**

```tsx
  if (isArchived) {
    return (
      <div className="border-t border-border bg-surface-muted px-4 py-3 text-center text-xs text-muted">
        This session is archived. Restore it from the sidebar to continue the conversation.
      </div>
    );
  }
```

- [ ] **Step 2: Replace the main composer return block**

```tsx
  return (
    <form onSubmit={onSend} className="border-t border-border bg-surface p-3.5">
      {error && (
        <div className="mb-2 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
          {error}
        </div>
      )}
      <div className="flex items-end gap-2.5 rounded-xl border border-border bg-surface p-2.5 transition focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/15">
        <textarea
          className="h-10 flex-1 resize-none bg-transparent text-sm text-foreground outline-none placeholder:text-muted/70"
          rows={2}
          placeholder="Describe what you want…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSend(e);
            }
          }}
          disabled={busy}
        />
        <div className="flex flex-col items-end gap-1.5">
          <label
            className="flex items-center gap-1 text-[11px] text-muted"
            title="Questions per turn"
          >
            Qs
            <select
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
              disabled={busy}
              className="rounded-md border border-border bg-surface px-1 py-0.5 text-[11px] text-foreground"
            >
              {Array.from(
                { length: MAX_COUNT - MIN_COUNT + 1 },
                (_, i) => MIN_COUNT + i
              ).map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <button
            type="submit"
            disabled={busy || !text.trim()}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-foreground shadow-sm transition hover:brightness-110 disabled:bg-accent/40"
          >
            Send
          </button>
        </div>
      </div>
    </form>
  );
```

- [ ] **Step 3: Verify build + lint**

Run: `npm run build && npm run lint`
Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/Dialogue/InputBox.tsx
git commit -m "feat(frontend): restyle message composer"
```

---

## Task 9: LiveRequirements panel

**Files:**
- Modify: `frontend/src/components/Requirements/LiveRequirements.tsx`

Visual reference: `chat-mockup.html` (right column). Keep the `useEffect` load, `grouped` reduce, and `onExport` unchanged. Replace the `TYPE_LABEL` map and the returned JSX.

- [ ] **Step 1: Update the type label map to include an icon glyph**

```tsx
const TYPE_LABEL: Record<string, string> = {
  functional: "⚙ Functional",
  non_functional: "◷ Non-Functional",
  constraint: "⊘ Constraints",
};
```

- [ ] **Step 2: Replace the returned JSX**

```tsx
  return (
    <aside className="flex flex-col gap-3.5 overflow-y-auto border-l border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">Live Requirements</h2>
        {activeId && (
          <div className="flex gap-1.5">
            <button
              onClick={() => onExport("md")}
              className="rounded-md border border-border px-2 py-1 text-[10px] text-muted transition hover:bg-surface-muted hover:text-foreground"
              title="Download as Markdown"
            >
              .md
            </button>
            <button
              onClick={() => onExport("txt")}
              className="rounded-md border border-border px-2 py-1 text-[10px] text-muted transition hover:bg-surface-muted hover:text-foreground"
              title="Download as plain text"
            >
              .txt
            </button>
          </div>
        )}
      </div>
      {Object.keys(TYPE_LABEL).map((k) => {
        const items = grouped[k] || [];
        if (items.length === 0) return null;
        return (
          <div key={k} className="overflow-hidden rounded-xl border border-border bg-surface">
            <div className="flex items-center justify-between border-b border-border bg-surface-muted px-3 py-2.5">
              <span className="text-[11px] font-semibold text-foreground">
                {TYPE_LABEL[k]}
              </span>
              <span className="rounded-full bg-accent/12 px-2 py-0.5 text-[10px] font-semibold text-accent">
                {items.length}
              </span>
            </div>
            <ul>
              {items.map((r) => (
                <li
                  key={r.id}
                  className="border-b border-border px-3 py-2.5 text-sm text-foreground last:border-b-0"
                >
                  {r.statement}
                </li>
              ))}
            </ul>
          </div>
        );
      })}
      {requirements.length === 0 && (
        <p className="text-sm italic text-muted">No requirements extracted yet.</p>
      )}
    </aside>
  );
```

- [ ] **Step 3: Verify build + lint**

Run: `npm run build && npm run lint`
Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/Requirements/LiveRequirements.tsx
git commit -m "feat(frontend): restyle live requirements panel"
```

---

## Task 10: SpecPage (curator view)

**Files:**
- Modify: `frontend/src/pages/SpecPage.tsx`

Keep ALL state, effects, `onSave`, `EditDrawer` logic, and the option/label constant maps unchanged. Adopt `AppHeader` and restyle the rail, filter bar, table, and drawer with tokens + `Badge`.

- [ ] **Step 1: Add imports and replace the header**

Add to the import block:

```tsx
import AppHeader from "../components/AppHeader";
import Badge, { type BadgeTone } from "../components/ui/Badge";
```

Remove the now-unused `useAuthStore`/`useNavigate` usage for logout (AppHeader owns it). If `useNavigate` is unused afterward, delete its import; keep `useState`/`useEffect`. Replace the outer wrapper + header:

```tsx
  return (
    <div className="grid h-screen grid-rows-[auto_1fr] bg-background">
      <AppHeader title="Requirements Spec — Curator View" />

      <div className="grid grid-cols-[220px_1fr] overflow-hidden">
```

(Delete the old `<header>...</header>` block entirely, and the `clear`/`nav` constants if no longer referenced.)

- [ ] **Step 2: Restyle the sessions rail**

```tsx
        <aside className="overflow-y-auto border-r border-border bg-surface p-3">
          <h2 className="mb-2 px-1 text-[10px] font-semibold uppercase tracking-wider text-muted">
            Sessions
          </h2>
          <button
            onClick={() => setFilterSessionId(null)}
            className={`mb-1 block w-full rounded-lg px-2.5 py-1.5 text-left text-sm transition ${
              !filterSessionId
                ? "bg-accent/10 font-medium text-accent"
                : "text-foreground hover:bg-surface-muted"
            }`}
          >
            All sessions
          </button>
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => setFilterSessionId(s.id)}
              className={`mb-1 block w-full truncate rounded-lg px-2.5 py-1.5 text-left text-sm transition ${
                filterSessionId === s.id
                  ? "bg-accent/10 font-medium text-accent"
                  : "text-foreground hover:bg-surface-muted"
              }`}
              title={s.project_title}
            >
              {s.project_title}
            </button>
          ))}
        </aside>
```

- [ ] **Step 3: Restyle the main column — filter bar + table**

Replace the `<div className="flex flex-col overflow-hidden">` content down to (but not including) the `{selected && (` drawer with:

```tsx
        <div className="flex flex-col overflow-hidden">
          <div className="flex items-center gap-3 border-b border-border bg-surface px-4 py-2.5 text-sm">
            <label className="flex items-center gap-1.5 text-muted">
              Type
              <select
                value={filterType ?? ""}
                onChange={(e) => setFilterType(e.target.value || null)}
                className="rounded-md border border-border bg-surface px-2 py-1 text-foreground"
              >
                <option value="">All</option>
                {TYPE_OPTIONS.map((t) => (
                  <option key={t} value={t}>
                    {TYPE_LABEL[t]}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-1.5 text-muted">
              Status
              <select
                value={filterStatus ?? ""}
                onChange={(e) => setFilterStatus(e.target.value || null)}
                className="rounded-md border border-border bg-surface px-2 py-1 text-foreground"
              >
                <option value="">All</option>
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {STATUS_LABEL[s]}
                  </option>
                ))}
              </select>
            </label>
            <span className="ml-auto text-muted">{requirements.length} requirements</span>
          </div>

          <div className="flex-1 overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-surface-muted text-left text-muted">
                <tr>
                  <th className="w-16 px-3 py-2 font-medium">#</th>
                  <th className="px-3 py-2 font-medium">Statement</th>
                  <th className="w-16 px-3 py-2 font-medium">Type</th>
                  <th className="w-16 px-3 py-2 font-medium">Pri</th>
                  <th className="w-24 px-3 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {requirements.map((r, i) => (
                  <tr
                    key={r.id}
                    onClick={() => setSelectedId(r.id)}
                    className={`cursor-pointer border-b border-border transition ${
                      selectedId === r.id ? "bg-accent/10" : "hover:bg-surface-muted"
                    }`}
                  >
                    <td className="px-3 py-2 text-muted">{i + 1}</td>
                    <td className="px-3 py-2 text-foreground">{r.statement}</td>
                    <td className="px-3 py-2 text-foreground">{TYPE_LABEL[r.type] ?? r.type}</td>
                    <td className="px-3 py-2 text-foreground">
                      {r.priority ? (PRIORITY_LABEL[r.priority] ?? r.priority) : "—"}
                    </td>
                    <td className="px-3 py-2">
                      <Badge tone={STATUS_TONE[r.status ?? "pending"] ?? "neutral"}>
                        {STATUS_LABEL[r.status ?? "pending"] ?? "Pending"}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {requirements.length === 0 && (
              <p className="mt-8 text-center text-muted">No requirements match filters.</p>
            )}
          </div>

          {selected && (
            <EditDrawer
              key={selected.id}
              requirement={selected}
              saving={saving}
              onSave={onSave}
              onClose={() => setSelectedId(null)}
            />
          )}
        </div>
```

- [ ] **Step 4: Add the `STATUS_TONE` map** near the other label maps at the top of the file:

```tsx
const STATUS_TONE: Record<string, BadgeTone> = {
  approved: "success",
  rejected: "danger",
  needs_clarification: "warning",
  pending: "neutral",
};
```

- [ ] **Step 5: Restyle the `EditDrawer`** — replace its returned JSX (keep its hooks/`dirty`/`handleSave` unchanged):

```tsx
  return (
    <div className="space-y-2.5 border-t border-border bg-surface px-4 py-3.5 shadow-lift">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-foreground">Edit Requirement</h3>
        <button
          onClick={onClose}
          className="text-lg leading-none text-muted transition hover:text-foreground"
        >
          &times;
        </button>
      </div>
      <div className="grid grid-cols-[1fr_auto_auto] items-end gap-2.5">
        <label className="text-xs text-muted">
          Statement
          <input
            value={statement}
            onChange={(e) => setStatement(e.target.value)}
            className="mt-1 block w-full rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-foreground focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20"
          />
        </label>
        <label className="text-xs text-muted">
          Type
          <select
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="mt-1 block rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-foreground"
          >
            {TYPE_OPTIONS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-muted">
          Priority
          <select
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
            className="mt-1 block rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-foreground"
          >
            <option value="">—</option>
            {PRIORITY_OPTIONS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="grid grid-cols-[auto_1fr] items-end gap-2.5">
        <label className="text-xs text-muted">
          Status
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="mt-1 block rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-foreground"
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-muted">
          Acceptance Criteria
          <input
            value={ac}
            onChange={(e) => setAc(e.target.value)}
            placeholder="Given… When… Then…"
            className="mt-1 block w-full rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-foreground placeholder:text-muted/70 focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20"
          />
        </label>
      </div>
      <div className="flex justify-end gap-2 pt-1">
        <button
          onClick={handleSave}
          disabled={!dirty || saving}
          className="rounded-lg bg-accent px-4 py-1.5 text-sm font-medium text-accent-foreground shadow-sm transition hover:brightness-110 disabled:opacity-40"
        >
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
```

- [ ] **Step 6: Verify build + lint**

Run: `npm run build && npm run lint`
Expected: pass (no unused imports — confirm `useAuthStore`/`useNavigate` are removed if no longer used).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/SpecPage.tsx
git commit -m "feat(frontend): restyle requirements spec curator page"
```

---

## Task 11: Full verification pass

**Files:** none (verification only).

- [ ] **Step 1: Run the full check**

Run: `npm run build && npm run test && npm run lint`
Expected: build succeeds, all vitest tests pass (themeStore + existing store tests), lint clean.

- [ ] **Step 2: Manual visual smoke test**

Run `npm run dev`. For BOTH themes (toggle via the header button):
- `/login` and `/signup` — card, focus rings, error banner styling, theme persists across reload (no flash).
- `/chat` — new session greeting hero, send a message, confirm bubbles, strategy chip, animated typing indicator, composer focus ring, Qs select, live requirements cards with counts; archive/restore/delete a session.
- `/spec` (as a requirements_engineer account) — rail selection, filter selects, table hover/selected rows, status badges, edit drawer open/save.

- [ ] **Step 3: Final commit (if any tweaks were needed)**

```bash
git add -A
git commit -m "chore(frontend): final redesign verification tweaks"
```

---

## Self-Review (completed)

**Spec coverage:** §3.1 tokens → Task 1; §3.2 Tailwind wiring → Task 1; §3.3 theme toggle/no-flash/font → Tasks 1+2+4; §3.4 primitives → Task 3; §3.5 AppHeader → Task 4; §4.1 auth → Task 5; §4.2 chat (MainPage/SessionList/ChatPanel/StatusIndicator/InputBox/LiveRequirements) → Tasks 6–9; §4.3 spec → Task 10; §7 verification → Task 11. No gaps.

**Placeholder scan:** No TBD/TODO; all code blocks are concrete and copy-pasteable.

**Type consistency:** `BadgeTone` exported from `Badge.tsx` and imported in ChatPanel + SpecPage; `STRATEGY_DISPLAY` uses `tone` keys matching `TONES`; `STATUS_TONE` defined in Task 10 Step 4 before use in Step 3 (apply both in the same task); `useThemeStore` API (`theme`, `toggle`) consistent between store, test, and AppHeader.
