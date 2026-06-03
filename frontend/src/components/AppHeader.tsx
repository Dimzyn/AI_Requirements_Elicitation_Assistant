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
    <header className="flex h-[52px] items-center gap-3 border-b border-border bg-surface px-4 py-2">
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
