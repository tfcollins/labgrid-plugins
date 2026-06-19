import "@testing-library/jest-dom";

// Node >= 22 exposes a built-in global `localStorage` (Web Storage API) that,
// under vitest's jsdom environment, shadows jsdom's window.localStorage and is
// non-functional (it expects a `--localstorage-file` that vitest does not
// pass), so calls like `localStorage.clear()` throw. Install a working
// in-memory Storage on both the global and window so the test suite is
// independent of the Node version it runs on.
function createMemoryStorage() {
  let store: Record<string, string> = {};
  return {
    get length() {
      return Object.keys(store).length;
    },
    clear(): void {
      store = {};
    },
    getItem(key: string): string | null {
      return Object.prototype.hasOwnProperty.call(store, key) ? store[key] : null;
    },
    key(index: number): string | null {
      return Object.keys(store)[index] ?? null;
    },
    removeItem(key: string): void {
      delete store[key];
    },
    setItem(key: string, value: string): void {
      store[key] = String(value);
    },
  };
}

const memoryStorage = createMemoryStorage();
for (const target of [globalThis, typeof window !== "undefined" ? window : undefined]) {
  if (target) {
    Object.defineProperty(target, "localStorage", {
      configurable: true,
      writable: true,
      value: memoryStorage,
    });
  }
}
