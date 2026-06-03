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
