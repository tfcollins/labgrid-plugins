# Coordinator Dashboard Restyle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the entire `coordinator/web` dashboard to the premium "Instrument Precision" aesthetic (both light and dark first-class, ADI blue as the structural accent) without changing any behavior.

**Architecture:** A centralized Chakra theme (`src/theme/`) plus a small set of shared UI primitives (`src/components/ui/`) carry the design language; a token sweep propagates it to non-hero pages; the five hero pages get bespoke layout polish. Presentation-only, with two documented exceptions (Places density toggle; fixing a pre-existing dead `/exporters` link).

**Tech Stack:** React 18, TypeScript, Vite, Chakra UI v2.8.2, `@chakra-ui/anatomy`, reactflow, vitest + `@testing-library/react`, react-router-dom.

## Working directory & branch

- All paths below are relative to `coordinator/web/` unless noted. **Run all `npm`/`npx` commands from `coordinator/web/`.**
- Work on the existing branch **`coordinator-dashboard-restyle`** (already created off `main`; the spec is committed there).
- Imports are **relative** (no path aliases configured in `tsconfig.json`/`vite.config.ts`).

## Global Constraints

Every task implicitly includes these (copied from the spec):

- **Chakra UI v2.8.2** APIs only. Multipart component overrides use `createMultiStyleConfigHelpers(<anatomy>.keys)` with keys imported from `@chakra-ui/anatomy`.
- **Both light and dark must be first-class and AA-accessible** (body text ≥ 4.5:1, large/UI ≥ 3:1, in both modes). Never use a sub-AA gray (`#97a2ad`/`gray.400`) for real text. Status color lives on dots/borders, not on label text.
- **ADI blue is the only structural accent** (`accent` = `adi.500 #0071ba` light / `adi.400 #1e9bd7` dark). No Chakra-blue (`#3182ce`) anywhere after the sweep.
- **Presentation-only.** No API/backend/route/data-fetching/behavior changes, EXCEPT: (1) Places density toggle (local UI state, default comfortable, `localStorage`-persisted); (2) repoint the Dashboard "exporters online" link from the dead `/exporters` to `/resources`.
- **Preserve** all user-facing text, ARIA, and routes. Specifically keep the Topology legend strings `"Places (free)"`, `"Places (held)"`, `"Match rules"`; leave `Term.tsx`, the local `StatCard` in `Statistics.tsx`, and the `Help.tsx` code block untouched.
- **`npm test` (vitest) must stay green at the end of every task.** Run from `coordinator/web/`.
- Test convention: vitest globals (`describe/it/expect`), `@testing-library/react`, wrap UI in `<ChakraProvider>` (+ `<MemoryRouter>` when the component renders router links). `setupFiles` already loads `@testing-library/jest-dom`.

## Shared interfaces (defined once, referenced by many tasks)

These types/components are created in Phase 2 and consumed throughout. Names are fixed here:

```ts
// src/components/ui/status.ts
export type PlaceStatus = "free" | "acquired" | "offline" | "degraded" | "reservation";
```

- `Panel` — `(props: BoxProps) => JSX` — hairline surface container.
- `MicroLabel` — `({ children, ...rest }: TextProps) => JSX` — uppercase tracked 11px label.
- `SectionLabel` — `({ children, ...rest }: HeadingProps) => JSX` — small tracked section heading.
- `StatusDot` — `({ status, size }: { status: PlaceStatus; size?: number }) => JSX`.
- `StatusPill` — `({ status, children }: { status: PlaceStatus; children?: React.ReactNode }) => JSX`.
- `UtilizationBar` — `({ free, acquired, offline }: { free: number; acquired: number; offline: number }) => JSX`.
- `MetricCard` — `({ label, value, to, children }: { label: string; value: React.ReactNode; to?: string; children?: React.ReactNode }) => JSX`.
- `NavItem` — `({ to, icon, label, isActive }: { to: string; icon: React.ElementType; label: string; isActive: boolean }) => JSX`.

---

# Phase 1 — Theme foundation + fonts

### Task 1: Raw theme tokens (`src/theme/tokens.ts`)

**Files:**
- Create: `src/theme/tokens.ts`
- Test: `src/theme/__tests__/tokens.test.ts`

**Interfaces:**
- Produces: `export const colors`, `export const fonts`, `export const radii` (plain objects merged by Task 4).

- [ ] **Step 1: Write the failing test**

```ts
// src/theme/__tests__/tokens.test.ts
import { describe, it, expect } from "vitest";
import { colors, fonts, radii } from "../tokens";

describe("theme tokens", () => {
  it("keeps the ADI brand blue palette anchored at 500/400", () => {
    expect(colors.adi[500]).toBe("#0071ba");
    expect(colors.adi[400]).toBe("#1e9bd7");
  });

  it("uses the new distinctive font families, not Inter", () => {
    expect(fonts.heading).toContain("Hanken Grotesk");
    expect(fonts.body).toContain("Public Sans");
    expect(fonts.mono).toContain("IBM Plex Mono");
    expect(`${fonts.heading} ${fonts.body}`).not.toContain("Inter");
  });

  it("defines a small consistent radius scale", () => {
    expect(radii.md).toBe("5px");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/theme/__tests__/tokens.test.ts`
Expected: FAIL — cannot find module `../tokens`.

- [ ] **Step 3: Write minimal implementation**

```ts
// src/theme/tokens.ts
// Raw scales used to assemble the theme. ADI blue palette is unchanged from the
// previous theme.ts; fonts + radii are new (Instrument Precision direction).
export const colors = {
  adi: {
    50: "#e6f2fa",
    100: "#b3d9f0",
    200: "#80bfe6",
    300: "#4da6dc",
    400: "#1e9bd7",
    500: "#0071ba",
    600: "#005fa0",
    700: "#004d85",
    800: "#003d71",
    900: "#002b50",
  },
};

export const fonts = {
  heading: '"Hanken Grotesk", system-ui, sans-serif',
  body: '"Public Sans", system-ui, sans-serif',
  mono: '"IBM Plex Mono", ui-monospace, monospace',
};

export const radii = {
  sm: "3px",
  md: "5px",
  lg: "6px",
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/theme/__tests__/tokens.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/theme/tokens.ts src/theme/__tests__/tokens.test.ts
git commit -m "feat(theme): raw tokens — ADI palette, Instrument Precision fonts + radii"
```

---

### Task 2: Semantic tokens (`src/theme/semanticTokens.ts`)

**Files:**
- Create: `src/theme/semanticTokens.ts`
- Test: `src/theme/__tests__/semanticTokens.test.ts`

**Interfaces:**
- Produces: `export const semanticTokens` (Chakra `semanticTokens` object) with `colors` covering: `page.bg`, `surface.bg`, `surface.raised`, `surface.subtle`, `border.hairline`, `text.primary`, `text.secondary`, `accent`, `link`, `accent.text`, `sidebar.bg`, `sidebar.text`, `sidebar.hover`, and `status.{free,acquired,offline,degraded,reservation}`. Each has `default` + `_dark`.

- [ ] **Step 1: Write the failing test**

```ts
// src/theme/__tests__/semanticTokens.test.ts
import { describe, it, expect } from "vitest";
import { semanticTokens } from "../semanticTokens";

const c = semanticTokens.colors;

describe("semantic tokens", () => {
  it("defines co-equal light + dark surfaces", () => {
    expect(c["page.bg"]).toEqual({ default: "#fafbfc", _dark: "#0b0f14" });
    expect(c["surface.bg"]).toEqual({ default: "#ffffff", _dark: "#0e141b" });
    expect(c["surface.subtle"]).toEqual({ default: "#f3f5f7", _dark: "#161f2a" });
    expect(c["border.hairline"]).toEqual({ default: "#e4e8ec", _dark: "#1c2530" });
  });

  it("maps accent, link and the retained accent.text alias to ADI blue per mode", () => {
    const adi = { default: "adi.500", _dark: "adi.400" };
    expect(c["accent"]).toEqual(adi);
    expect(c["link"]).toEqual(adi);
    expect(c["accent.text"]).toEqual(adi); // retained so Statistics.tsx:42 keeps working
  });

  it("defines all five status tokens with AA-safe dark variants", () => {
    expect(c["status.free"]).toEqual({ default: "#38a169", _dark: "#48bb78" });
    expect(c["status.acquired"]).toEqual({ default: "#dd6b20", _dark: "#ed8936" });
    expect(c["status.offline"]).toEqual({ default: "#718096", _dark: "#a0aec0" });
    expect(c["status.degraded"]).toEqual({ default: "#e53e3e", _dark: "#fc8181" });
    expect(c["status.reservation"]).toEqual({ default: "#d69e2e", _dark: "#f6e05e" });
  });

  it("keeps text.secondary AA-legible (no faint grays)", () => {
    expect(c["text.secondary"]).toEqual({ default: "#52606d", _dark: "#9fb0c0" });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/theme/__tests__/semanticTokens.test.ts`
Expected: FAIL — cannot find module `../semanticTokens`.

- [ ] **Step 3: Write minimal implementation**

```ts
// src/theme/semanticTokens.ts
// Semantic color tokens — the single source of per-mode design decisions.
// `accent`, `link`, and `accent.text` are all aliases of ADI blue (same values),
// so links/accents track the brand color per mode automatically.
export const semanticTokens = {
  colors: {
    "page.bg": { default: "#fafbfc", _dark: "#0b0f14" },
    "surface.bg": { default: "#ffffff", _dark: "#0e141b" },
    "surface.raised": { default: "#ffffff", _dark: "#121a24" },
    "surface.subtle": { default: "#f3f5f7", _dark: "#161f2a" },
    "border.hairline": { default: "#e4e8ec", _dark: "#1c2530" },
    "text.primary": { default: "#1a2430", _dark: "#e6edf3" },
    "text.secondary": { default: "#52606d", _dark: "#9fb0c0" },
    accent: { default: "adi.500", _dark: "adi.400" },
    link: { default: "adi.500", _dark: "adi.400" },
    "accent.text": { default: "adi.500", _dark: "adi.400" },
    "sidebar.bg": { default: "#003d71", _dark: "#06101d" },
    "sidebar.text": { default: "#e6edf3", _dark: "#e6edf3" },
    "sidebar.hover": { default: "#004d85", _dark: "#0e1f33" },
    "status.free": { default: "#38a169", _dark: "#48bb78" },
    "status.acquired": { default: "#dd6b20", _dark: "#ed8936" },
    "status.offline": { default: "#718096", _dark: "#a0aec0" },
    "status.degraded": { default: "#e53e3e", _dark: "#fc8181" },
    "status.reservation": { default: "#d69e2e", _dark: "#f6e05e" },
  },
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/theme/__tests__/semanticTokens.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/theme/semanticTokens.ts src/theme/__tests__/semanticTokens.test.ts
git commit -m "feat(theme): semantic tokens — co-equal light/dark surfaces, status, ADI accent aliases"
```

---

### Task 3: Component style overrides (`src/theme/components.ts`)

**Files:**
- Create: `src/theme/components.ts`
- Test: `src/theme/__tests__/components.test.ts`

**Interfaces:**
- Produces: `export const components` — Chakra `components` config object with keys `Button`, `Badge`, `Tag`, `Heading`, `Link`, `Code`, `Table`.

- [ ] **Step 1: Write the failing test**

```ts
// src/theme/__tests__/components.test.ts
import { describe, it, expect } from "vitest";
import { components } from "../components";

describe("component overrides", () => {
  it("keeps the ADI default color scheme on Button and Badge", () => {
    expect(components.Button.defaultProps.colorScheme).toBe("adi");
    expect(components.Badge.defaultProps.colorScheme).toBe("adi");
  });

  it("colors links with the brand link token and disables underline", () => {
    expect(components.Link.baseStyle.color).toBe("link");
  });

  it("provides a multipart Table override (hairline spec-sheet look)", () => {
    // createMultiStyleConfigHelpers produces a config with baseStyle/variants.
    expect(components.Table).toBeTypeOf("object");
    expect(components.Table.baseStyle).toBeDefined();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/theme/__tests__/components.test.ts`
Expected: FAIL — cannot find module `../components`.

- [ ] **Step 3: Write minimal implementation**

```ts
// src/theme/components.ts
import { createMultiStyleConfigHelpers } from "@chakra-ui/react";
import { tableAnatomy } from "@chakra-ui/anatomy";

const tableHelpers = createMultiStyleConfigHelpers(tableAnatomy.keys);

// Hairline "spec-sheet" table: thin rules, tabular mono cells, tracked uppercase headers.
const Table = tableHelpers.defineMultiStyleConfig({
  baseStyle: {
    th: {
      textTransform: "uppercase",
      letterSpacing: "0.12em",
      fontSize: "11px",
      fontWeight: "600",
      color: "text.secondary",
      borderColor: "border.hairline",
    },
    td: {
      borderColor: "border.hairline",
      fontVariantNumeric: "tabular-nums",
    },
  },
  defaultProps: { size: "sm" },
});

export const components = {
  Button: {
    defaultProps: { colorScheme: "adi" },
    baseStyle: { borderRadius: "md", fontWeight: "600" },
  },
  Badge: {
    defaultProps: { colorScheme: "adi" },
    baseStyle: { borderRadius: "sm", textTransform: "none" },
  },
  Tag: {
    baseStyle: { container: { borderRadius: "sm" } },
  },
  Heading: {
    baseStyle: { fontFamily: "heading", letterSpacing: "-0.01em" },
  },
  Link: {
    baseStyle: { color: "link", _hover: { textDecoration: "none", color: "accent" } },
  },
  Code: {
    baseStyle: { fontFamily: "mono", borderRadius: "sm" },
  },
  Table,
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/theme/__tests__/components.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/theme/components.ts src/theme/__tests__/components.test.ts
git commit -m "feat(theme): component overrides — hairline table, brand links, square radii"
```

---

### Task 4: Assemble theme + delete old `theme.ts` (`src/theme/index.ts`)

**Files:**
- Create: `src/theme/index.ts`
- Delete: `src/theme.ts`
- Test: `src/theme/__tests__/index.test.ts`
- Verify: `src/main.tsx` import (`import theme from "./theme"` already resolves to the folder — no change needed)

**Interfaces:**
- Consumes: `colors`, `fonts`, `radii` (Task 1), `semanticTokens` (Task 2), `components` (Task 3).
- Produces: `export default theme` (Chakra theme). `theme.config.initialColorMode === "light"`, `useSystemColorMode: true`.

- [ ] **Step 1: Write the failing test**

```ts
// src/theme/__tests__/index.test.ts
import { describe, it, expect } from "vitest";
import theme from "../index";

describe("assembled theme", () => {
  it("preserves color-mode config", () => {
    expect(theme.config.initialColorMode).toBe("light");
    expect(theme.config.useSystemColorMode).toBe(true);
  });
  it("wires fonts, the ADI palette, and semantic tokens together", () => {
    expect(theme.fonts.body).toContain("Public Sans");
    expect(theme.colors.adi[500]).toBe("#0071ba");
    expect(theme.semanticTokens.colors["status.free"].default).toBe("#38a169");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/theme/__tests__/index.test.ts`
Expected: FAIL — cannot find module `../index`.

- [ ] **Step 3: Write minimal implementation, then delete the old theme file**

```ts
// src/theme/index.ts
import { extendTheme, type ThemeConfig } from "@chakra-ui/react";
import { colors, fonts, radii } from "./tokens";
import { semanticTokens } from "./semanticTokens";
import { components } from "./components";

const config: ThemeConfig = {
  initialColorMode: "light",
  useSystemColorMode: true,
};

const theme = extendTheme({
  config,
  colors,
  fonts,
  radii,
  semanticTokens,
  components,
  styles: {
    global: {
      body: { bg: "page.bg", color: "text.primary" },
    },
  },
});

export default theme;
```

```bash
git rm src/theme.ts
```

- [ ] **Step 4: Run the test + the full suite to verify nothing broke**

Run: `npx vitest run src/theme/__tests__/index.test.ts && npm test`
Expected: index test PASS (2 tests); full suite PASS (the `./theme` import in `main.tsx` now resolves to `src/theme/index.ts`).

- [ ] **Step 5: Verify the app still type-checks/builds**

Run: `npm run build`
Expected: `tsc -b` + `vite build` succeed with no errors.

- [ ] **Step 6: Commit**

```bash
git add src/theme/index.ts src/theme/__tests__/index.test.ts
git commit -m "feat(theme): assemble theme/ folder, global page bg, drop single-file theme.ts"
```

---

### Task 5: Fonts in `index.html` (replace Inter, add preconnect)

**Files:**
- Modify: `index.html` (the `<head>` font `<link>`)

- [ ] **Step 1: Replace the Inter link with the three new families + preconnect**

Replace this block in `index.html`:

```html
    <link
      href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
      rel="stylesheet"
    />
```

with:

```html
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&family=Public+Sans:wght@400;500;600;700&display=swap"
      rel="stylesheet"
    />
```

- [ ] **Step 2: Verify Inter is gone and the new families + preconnect are present**

Run: `grep -c "Inter" index.html; grep -c "Hanken+Grotesk" index.html; grep -c "preconnect" index.html`
Expected: `0` (Inter), `1` (Hanken), `2` (preconnect).

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "feat(web): load Hanken Grotesk + Public Sans + IBM Plex Mono, drop Inter"
```

---

### Task 6: `ChipIcon` adapts to current color

**Files:**
- Modify: `src/components/ChipIcon.tsx`
- Test: `src/components/__tests__/ChipIcon.test.tsx`

**Interfaces:**
- Produces: `ChipIcon` renders SVG strokes using `currentColor` (so the caller's `color` controls it). Keeps the `size` prop and the blue signal trace.

- [ ] **Step 1: Write the failing test**

```tsx
// src/components/__tests__/ChipIcon.test.tsx
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import ChipIcon from "../ChipIcon";

describe("ChipIcon", () => {
  it("uses currentColor for the chip body so it adapts to the sidebar fg", () => {
    const { container } = render(<ChipIcon size={36} />);
    const strokes = [...container.querySelectorAll("[stroke]")].map((n) => n.getAttribute("stroke"));
    expect(strokes).toContain("currentColor");
    expect(strokes).not.toContain("#e6edf3"); // the old hardcoded light color is gone
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/components/__tests__/ChipIcon.test.tsx`
Expected: FAIL — strokes still `#e6edf3`.

- [ ] **Step 3: Write the implementation**

Replace every `stroke="#e6edf3"` in `src/components/ChipIcon.tsx` with `stroke="currentColor"` (the chip outline, pins, and pin pads — ~16 attributes). Leave the signal trace `stroke="#4db8ff"` unchanged. Fastest exact edit:

```bash
sed -i 's/stroke="#e6edf3"/stroke="currentColor"/g' src/components/ChipIcon.tsx
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/components/__tests__/ChipIcon.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/components/ChipIcon.tsx src/components/__tests__/ChipIcon.test.tsx
git commit -m "refactor(web): ChipIcon strokes use currentColor (adapts to both modes)"
```

> Note: the call-site color context is supplied in Task 13 (Layout wraps `ChipIcon` in `color="sidebar.text"`).

---

# Phase 2 — Shared primitives + Layout shell

### Task 7: `Panel`, `MicroLabel`, `SectionLabel`

**Files:**
- Create: `src/components/ui/Panel.tsx`
- Create: `src/components/ui/Labels.tsx`
- Test: `src/components/ui/__tests__/Panel.test.tsx`

**Interfaces:**
- Produces: `Panel` (`BoxProps` pass-through), `MicroLabel` (`TextProps`), `SectionLabel` (`HeadingProps`). See Shared interfaces.

- [ ] **Step 1: Write the failing test**

```tsx
// src/components/ui/__tests__/Panel.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChakraProvider } from "@chakra-ui/react";
import theme from "../../../theme";
import Panel from "../Panel";
import { MicroLabel, SectionLabel } from "../Labels";

const wrap = (ui: React.ReactNode) => <ChakraProvider theme={theme}>{ui}</ChakraProvider>;

describe("Panel + labels", () => {
  it("renders Panel children", () => {
    render(wrap(<Panel>inside</Panel>));
    expect(screen.getByText("inside")).toBeInTheDocument();
  });
  it("renders an uppercased micro-label and a section label", () => {
    render(wrap(<><MicroLabel>exporters</MicroLabel><SectionLabel>Places</SectionLabel></>));
    expect(screen.getByText("exporters")).toBeInTheDocument();
    expect(screen.getByText("Places")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/components/ui/__tests__/Panel.test.tsx`
Expected: FAIL — cannot find module `../Panel`.

- [ ] **Step 3: Write the implementation**

```tsx
// src/components/ui/Panel.tsx
import { Box, type BoxProps } from "@chakra-ui/react";

/** Hairline-bordered surface container. Replaces the ad-hoc
 *  `Box bg=card borderRadius shadow` pattern across the app. */
export default function Panel(props: BoxProps) {
  return (
    <Box
      bg="surface.bg"
      borderWidth="1px"
      borderColor="border.hairline"
      borderRadius="lg"
      {...props}
    />
  );
}
```

```tsx
// src/components/ui/Labels.tsx
import { Text, type TextProps, Heading, type HeadingProps } from "@chakra-ui/react";

/** Tiny uppercase tracked label (instrument micro-label). */
export function MicroLabel({ children, ...rest }: TextProps) {
  return (
    <Text
      fontSize="11px"
      fontWeight="600"
      textTransform="uppercase"
      letterSpacing="0.14em"
      color="text.secondary"
      {...rest}
    >
      {children}
    </Text>
  );
}

/** Section heading in the tracked instrument style. */
export function SectionLabel({ children, ...rest }: HeadingProps) {
  return (
    <Heading size="sm" color="text.primary" letterSpacing="-0.01em" {...rest}>
      {children}
    </Heading>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/components/ui/__tests__/Panel.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/components/ui/Panel.tsx src/components/ui/Labels.tsx src/components/ui/__tests__/Panel.test.tsx
git commit -m "feat(ui): Panel surface + MicroLabel/SectionLabel primitives"
```

---

### Task 8: `StatusDot`

**Files:**
- Create: `src/components/ui/status.ts`
- Create: `src/components/ui/StatusDot.tsx`
- Test: `src/components/ui/__tests__/StatusDot.test.tsx`

**Interfaces:**
- Produces: `PlaceStatus` type (`status.ts`); `StatusDot` colored dot, pulses (CSS) for `free`/`acquired`. Exposes `data-status={status}` for assertions.

- [ ] **Step 1: Write the failing test**

```tsx
// src/components/ui/__tests__/StatusDot.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChakraProvider } from "@chakra-ui/react";
import theme from "../../../theme";
import StatusDot from "../StatusDot";

const wrap = (ui: React.ReactNode) => <ChakraProvider theme={theme}>{ui}</ChakraProvider>;

describe("StatusDot", () => {
  it("exposes its status for assertions", () => {
    render(wrap(<StatusDot status="degraded" />));
    expect(screen.getByTestId("status-dot")).toHaveAttribute("data-status", "degraded");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/components/ui/__tests__/StatusDot.test.tsx`
Expected: FAIL — cannot find module `../StatusDot`.

- [ ] **Step 3: Write the implementation**

```ts
// src/components/ui/status.ts
export type PlaceStatus = "free" | "acquired" | "offline" | "degraded" | "reservation";

/** Maps a status to its semantic color token. */
export const STATUS_TOKEN: Record<PlaceStatus, string> = {
  free: "status.free",
  acquired: "status.acquired",
  offline: "status.offline",
  degraded: "status.degraded",
  reservation: "status.reservation",
};

/** Default visible label per status (callers may override). */
export const STATUS_LABEL: Record<PlaceStatus, string> = {
  free: "ready",
  acquired: "held",
  offline: "offline",
  degraded: "degraded",
  reservation: "reservation",
};
```

```tsx
// src/components/ui/StatusDot.tsx
import { Box, keyframes } from "@chakra-ui/react";
import { type PlaceStatus, STATUS_TOKEN } from "./status";

const pulse = keyframes`
  0% { box-shadow: 0 0 0 0 var(--dot-glow); }
  70% { box-shadow: 0 0 0 4px transparent; }
  100% { box-shadow: 0 0 0 0 transparent; }
`;

/** Small status LED. Pulses subtly for live states (free/acquired). */
export default function StatusDot({ status, size = 8 }: { status: PlaceStatus; size?: number }) {
  const token = STATUS_TOKEN[status];
  const animate = status === "free" || status === "acquired";
  return (
    <Box
      data-testid="status-dot"
      data-status={status}
      w={`${size}px`}
      h={`${size}px`}
      borderRadius="full"
      bg={token}
      sx={{ "--dot-glow": "currentColor" }}
      color={token}
      animation={animate ? `${pulse} 3.4s ease-in-out infinite` : undefined}
      flexShrink={0}
    />
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/components/ui/__tests__/StatusDot.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/components/ui/status.ts src/components/ui/StatusDot.tsx src/components/ui/__tests__/StatusDot.test.tsx
git commit -m "feat(ui): StatusDot LED + shared PlaceStatus/status-token maps"
```

---

### Task 9: `StatusPill`

**Files:**
- Create: `src/components/ui/StatusPill.tsx`
- Test: `src/components/ui/__tests__/StatusPill.test.tsx`

**Interfaces:**
- Consumes: `PlaceStatus`, `STATUS_LABEL` (Task 8), `StatusDot` (Task 8).
- Produces: `StatusPill({ status, children })` — dot + label (color on the dot/border, text in `text.primary`). Default label from `STATUS_LABEL` when no children.

- [ ] **Step 1: Write the failing test**

```tsx
// src/components/ui/__tests__/StatusPill.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChakraProvider } from "@chakra-ui/react";
import theme from "../../../theme";
import StatusPill from "../StatusPill";

const wrap = (ui: React.ReactNode) => <ChakraProvider theme={theme}>{ui}</ChakraProvider>;

describe("StatusPill", () => {
  it("renders the default label for a status", () => {
    render(wrap(<StatusPill status="free" />));
    expect(screen.getByText("ready")).toBeInTheDocument();
  });
  it("renders an overriding label (e.g. the degraded count)", () => {
    render(wrap(<StatusPill status="degraded">3 not live</StatusPill>));
    expect(screen.getByText("3 not live")).toBeInTheDocument();
    expect(screen.getByTestId("status-dot")).toHaveAttribute("data-status", "degraded");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/components/ui/__tests__/StatusPill.test.tsx`
Expected: FAIL — cannot find module `../StatusPill`.

- [ ] **Step 3: Write the implementation**

```tsx
// src/components/ui/StatusPill.tsx
import { HStack, Text } from "@chakra-ui/react";
import { type PlaceStatus, STATUS_LABEL, STATUS_TOKEN } from "./status";
import StatusDot from "./StatusDot";

/** Outlined status pill: color lives on the dot + border, label stays in
 *  text.primary for AA legibility in both modes. */
export default function StatusPill({
  status,
  children,
}: {
  status: PlaceStatus;
  children?: React.ReactNode;
}) {
  return (
    <HStack
      as="span"
      display="inline-flex"
      spacing={1.5}
      px={2}
      py={0.5}
      borderWidth="1px"
      borderColor={STATUS_TOKEN[status]}
      borderRadius="sm"
      bg="transparent"
    >
      <StatusDot status={status} size={7} />
      <Text as="span" fontSize="xs" fontWeight="600" color="text.primary" lineHeight="1.2">
        {children ?? STATUS_LABEL[status]}
      </Text>
    </HStack>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/components/ui/__tests__/StatusPill.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/components/ui/StatusPill.tsx src/components/ui/__tests__/StatusPill.test.tsx
git commit -m "feat(ui): StatusPill — outlined dot+label, AA-safe text"
```

---

### Task 10: `UtilizationBar`

**Files:**
- Create: `src/components/ui/UtilizationBar.tsx`
- Test: `src/components/ui/__tests__/UtilizationBar.test.tsx`

**Interfaces:**
- Produces: `UtilizationBar({ free, acquired, offline })` — three proportional segments (status colors), `role="img"` + descriptive `aria-label`. Renders nothing-but-empty bar safely when total is 0.

- [ ] **Step 1: Write the failing test**

```tsx
// src/components/ui/__tests__/UtilizationBar.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChakraProvider } from "@chakra-ui/react";
import theme from "../../../theme";
import UtilizationBar from "../UtilizationBar";

const wrap = (ui: React.ReactNode) => <ChakraProvider theme={theme}>{ui}</ChakraProvider>;

describe("UtilizationBar", () => {
  it("describes the breakdown for screen readers and renders 3 segments", () => {
    render(wrap(<UtilizationBar free={6} acquired={4} offline={2} />));
    const bar = screen.getByRole("img");
    expect(bar).toHaveAttribute("aria-label", "12 places: 6 free, 4 acquired, 2 offline");
    expect(bar.querySelectorAll("[data-seg]").length).toBe(3);
  });
  it("does not crash when there are no places", () => {
    render(wrap(<UtilizationBar free={0} acquired={0} offline={0} />));
    expect(screen.getByRole("img")).toHaveAttribute("aria-label", "0 places: 0 free, 0 acquired, 0 offline");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/components/ui/__tests__/UtilizationBar.test.tsx`
Expected: FAIL — cannot find module `../UtilizationBar`.

- [ ] **Step 3: Write the implementation**

```tsx
// src/components/ui/UtilizationBar.tsx
import { Box, Flex } from "@chakra-ui/react";

/** Thin segmented proportion bar built from real instantaneous counts.
 *  Conveys the bench-instrument feel without any time-series data. */
export default function UtilizationBar({
  free,
  acquired,
  offline,
}: {
  free: number;
  acquired: number;
  offline: number;
}) {
  const total = free + acquired + offline;
  const segs = [
    { key: "free", value: free, token: "status.free" },
    { key: "acquired", value: acquired, token: "status.acquired" },
    { key: "offline", value: offline, token: "status.offline" },
  ];
  return (
    <Flex
      role="img"
      aria-label={`${total} places: ${free} free, ${acquired} acquired, ${offline} offline`}
      h="6px"
      borderRadius="full"
      overflow="hidden"
      bg="surface.subtle"
      w="full"
    >
      {segs.map((s) => (
        <Box
          key={s.key}
          data-seg={s.key}
          bg={s.token}
          w={total === 0 ? "0%" : `${(s.value / total) * 100}%`}
        />
      ))}
    </Flex>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/components/ui/__tests__/UtilizationBar.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/components/ui/UtilizationBar.tsx src/components/ui/__tests__/UtilizationBar.test.tsx
git commit -m "feat(ui): UtilizationBar — segmented proportion bar (role=img)"
```

---

### Task 11: `MetricCard`

**Files:**
- Create: `src/components/ui/MetricCard.tsx`
- Test: `src/components/ui/__tests__/MetricCard.test.tsx`

**Interfaces:**
- Consumes: `Panel` (Task 7), `MicroLabel` (Task 7).
- Produces: `MetricCard({ label, value, to?, children? })` — Panel with micro-label, big Hanken value, optional `children` (e.g. `UtilizationBar`); when `to` is set the whole card is a `RouterLink` (`getByRole("link")`).

- [ ] **Step 1: Write the failing test**

```tsx
// src/components/ui/__tests__/MetricCard.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChakraProvider } from "@chakra-ui/react";
import { MemoryRouter } from "react-router-dom";
import theme from "../../../theme";
import MetricCard from "../MetricCard";

const wrap = (ui: React.ReactNode) => (
  <ChakraProvider theme={theme}><MemoryRouter>{ui}</MemoryRouter></ChakraProvider>
);

describe("MetricCard", () => {
  it("renders label + value", () => {
    render(wrap(<MetricCard label="Places" value="12 total" />));
    expect(screen.getByText("Places")).toBeInTheDocument();
    expect(screen.getByText("12 total")).toBeInTheDocument();
  });
  it("wraps in a router link when `to` is provided", () => {
    render(wrap(<MetricCard label="Places" value="12" to="/places" />));
    expect(screen.getByRole("link")).toHaveAttribute("href", "/places");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/components/ui/__tests__/MetricCard.test.tsx`
Expected: FAIL — cannot find module `../MetricCard`.

- [ ] **Step 3: Write the implementation**

```tsx
// src/components/ui/MetricCard.tsx
import { VStack, Text, LinkBox, LinkOverlay } from "@chakra-ui/react";
import { Link as RouterLink } from "react-router-dom";
import Panel from "./Panel";
import { MicroLabel } from "./Labels";

/** Stat tile: tracked micro-label + large value + optional extra (e.g. a
 *  UtilizationBar). When `to` is set the whole tile is a router link. */
export default function MetricCard({
  label,
  value,
  to,
  children,
}: {
  label: string;
  value: React.ReactNode;
  to?: string;
  children?: React.ReactNode;
}) {
  return (
    <LinkBox as={Panel} p={4} _hover={to ? { borderColor: "accent" } : undefined} transition="border-color 0.15s">
      <VStack align="stretch" spacing={2}>
        <MicroLabel>{label}</MicroLabel>
        <Text fontFamily="heading" fontSize="2xl" fontWeight="800" color="text.primary" lineHeight="1.1">
          {to ? (
            <LinkOverlay as={RouterLink} to={to}>
              {value}
            </LinkOverlay>
          ) : (
            value
          )}
        </Text>
        {children}
      </VStack>
    </LinkBox>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/components/ui/__tests__/MetricCard.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/components/ui/MetricCard.tsx src/components/ui/__tests__/MetricCard.test.tsx
git commit -m "feat(ui): MetricCard — labelled stat tile with optional link + extra"
```

---

### Task 12: `NavItem` (extracted, testable, with `aria-current`)

**Files:**
- Create: `src/components/ui/NavItem.tsx`
- Test: `src/components/ui/__tests__/NavItem.test.tsx`

**Interfaces:**
- Produces: `NavItem({ to, icon, label, isActive })` — router link; when `isActive` it exposes `aria-current="page"` and renders the lit channel-indicator bar.

- [ ] **Step 1: Write the failing test**

```tsx
// src/components/ui/__tests__/NavItem.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChakraProvider } from "@chakra-ui/react";
import { MemoryRouter } from "react-router-dom";
import { MdDashboard } from "react-icons/md";
import theme from "../../../theme";
import NavItem from "../NavItem";

const wrap = (ui: React.ReactNode) => (
  <ChakraProvider theme={theme}><MemoryRouter>{ui}</MemoryRouter></ChakraProvider>
);

describe("NavItem", () => {
  it("marks the active item with aria-current=page", () => {
    render(wrap(<NavItem to="/" icon={MdDashboard} label="Dashboard" isActive />));
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute("aria-current", "page");
  });
  it("does not set aria-current when inactive", () => {
    render(wrap(<NavItem to="/places" icon={MdDashboard} label="Places" isActive={false} />));
    expect(screen.getByRole("link", { name: "Places" })).not.toHaveAttribute("aria-current");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/components/ui/__tests__/NavItem.test.tsx`
Expected: FAIL — cannot find module `../NavItem`.

- [ ] **Step 3: Write the implementation**

```tsx
// src/components/ui/NavItem.tsx
import { Link as RouterLink } from "react-router-dom";
import { Box, HStack, Icon, Text } from "@chakra-ui/react";

/** Sidebar nav row with a lit channel-indicator bar + aria-current on the
 *  active route. */
export default function NavItem({
  to,
  icon,
  label,
  isActive,
}: {
  to: string;
  icon: React.ElementType;
  label: string;
  isActive: boolean;
}) {
  return (
    <Box
      as={RouterLink}
      to={to}
      aria-current={isActive ? "page" : undefined}
      position="relative"
      w="full"
      px={4}
      py={3}
      borderRadius="md"
      bg={isActive ? "whiteAlpha.200" : "transparent"}
      _hover={{ bg: "sidebar.hover" }}
      transition="background 0.15s"
    >
      {isActive && (
        <Box
          position="absolute"
          left="0"
          top="20%"
          bottom="20%"
          w="3px"
          borderRadius="full"
          bg="accent"
        />
      )}
      <HStack spacing={3}>
        <Icon as={icon} boxSize={5} color="sidebar.text" />
        <Text color="sidebar.text" fontSize="sm" fontWeight={isActive ? "600" : "400"}>
          {label}
        </Text>
      </HStack>
    </Box>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/components/ui/__tests__/NavItem.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/components/ui/NavItem.tsx src/components/ui/__tests__/NavItem.test.tsx
git commit -m "feat(ui): NavItem — lit channel indicator + aria-current"
```

---

### Task 13: Rebuild `Layout` shell

**Files:**
- Modify: `src/components/Layout.tsx`

**Interfaces:**
- Consumes: `NavItem` (Task 12), `ChipIcon` (Task 6).

- [ ] **Step 1: Replace the inline `NavItem` with the shared one and tokenize surfaces**

In `src/components/Layout.tsx`:

1. Delete the local `NavItem` function (lines ~32-60) and its `NavItemProps` interface.
2. Add the import: `import NavItem from "./ui/NavItem";`
3. Wrap the logo `ChipIcon` so it inherits the sidebar color — change:

```tsx
        <Box px={4} mb={8}>
          <ChipIcon size={36} />
```

to:

```tsx
        <Box px={4} mb={8} color="sidebar.text">
          <ChipIcon size={36} />
```

4. Tokenize the header + page-content surfaces. Replace:

```tsx
  const headerBg = useColorModeValue("white", "gray.800");
  const borderColor = useColorModeValue("gray.200", "gray.700");
```

with:

```tsx
  const headerBg = "surface.bg";
  const borderColor = "border.hairline";
```

Then remove the now-unused `useColorModeValue` from the `@chakra-ui/react` import line (keep `useColorMode`, which the header toggle still uses) — otherwise `tsc` (noUnusedLocals) fails the build.

and change the page-content `Box` background (line ~190):

```tsx
        <Box flex={1} overflow="auto" p={6} bg={useColorModeValue("gray.50", "gray.900")}>
```

to:

```tsx
        <Box flex={1} overflow="auto" p={6} bg="page.bg">
```

(Leave the `ExternalNavItem`, header toggle, and `AccountMenu` as-is — the toggle already works.)

- [ ] **Step 2: Run the full suite + build**

Run: `npm test && npm run build`
Expected: PASS + clean build. (No Layout test renders the full shell; `NavItem` is covered by Task 12.)

- [ ] **Step 3: Visual check (manual)**

Run: `npm run dev` → open the app, toggle light/dark. Confirm: sidebar logo visible in both modes, the active nav row shows the blue channel bar, header/content use the new surfaces. Stop the dev server when done.

- [ ] **Step 4: Commit**

```bash
git add src/components/Layout.tsx
git commit -m "feat(web): Layout uses shared NavItem (lit nav) + semantic surfaces"
```

---

# Phase 3 — Global token sweep (non-hero pages + shared)

> Hero pages (Dashboard, Places, PlaceDetail, Resources, Topology) fix their own colors in Phase 4 — do **not** touch them here.

### Task 14: Harden PlaceWizard checkbox queries (do this before any row restyle)

**Files:**
- Modify: `src/pages/PlaceWizard.tsx` (group row, ~line 252)
- Modify: `src/pages/__tests__/PlaceWizard.test.tsx` (3 DOM-walk lookups)

**Why first:** three PlaceWizard tests find the group checkbox by walking the DOM from the label text. Adding a stable `aria-label` lets the tests use `getByRole` and decouples them from layout, so later restyles can't break them.

- [ ] **Step 1: Add an aria-label to the group checkbox**

In `src/pages/PlaceWizard.tsx`, change:

```tsx
                      <Checkbox
                        isChecked={ticked}
                        onChange={() => togglePick(g.exporter, g.group, g.classes)}
                        mt={1}
                      />
```

to:

```tsx
                      <Checkbox
                        aria-label={`Select group ${g.exporter}/${g.group}`}
                        isChecked={ticked}
                        onChange={() => togglePick(g.exporter, g.group, g.classes)}
                        mt={1}
                      />
```

- [ ] **Step 2: Switch the three test lookups to getByRole**

In `src/pages/__tests__/PlaceWizard.test.tsx`, there are three occurrences of this pattern (around lines 86-89, 128-130, 154-156, 196-198):

```tsx
    const groupRow = await screen.findByText("exp1 / grpA");
    const cb = groupRow.closest("div")?.parentElement?.querySelector("input[type=checkbox]");
    expect(cb).toBeTruthy();
    fireEvent.click(cb!);
```

Replace each with a role-based lookup using the matching group name (`exp1/grpA` for the `exp1 / grpA` rows, `exp2/grpB` for the `exp2 / grpB` row):

```tsx
    const cb = await screen.findByRole("checkbox", { name: /select group exp1\/grpA/i });
    fireEvent.click(cb);
```

(For the `exp2 / grpB` test at ~line 154, use `/select group exp2\/grpB/i`.) Also delete the now-unused `findByLabelText(... selector: "select")` line and the `void checkbox;` cleanup in the "walks through all steps" test if they become unused.

- [ ] **Step 3: Run the PlaceWizard suite**

Run: `npx vitest run src/pages/__tests__/PlaceWizard.test.tsx`
Expected: PASS (all 5 tests).

- [ ] **Step 4: Commit**

```bash
git add src/pages/PlaceWizard.tsx src/pages/__tests__/PlaceWizard.test.tsx
git commit -m "test(web): query PlaceWizard group checkbox by aria-label (decouple from layout)"
```

---

### Task 15: Sweep links and Chakra-blue on non-hero/shared files

**Files (non-hero + shared only):**
- Modify: `src/components/RelatedPanel.tsx`, `src/components/DownloadEnvModal.tsx`, `src/pages/Reservations.tsx`, `src/pages/EventLog.tsx`, `src/pages/ExporterDetail.tsx`, `src/pages/AdminUsers.tsx`, `src/pages/Login.tsx`, `src/pages/PlaceWizard.tsx`, plus any other non-hero file the greps below surface.

- [ ] **Step 1: Find the candidates**

Run: `grep -rn 'color="blue.500"\|colorScheme="blue"' src/ | grep -vE 'pages/(Dashboard|Places|PlaceDetail|Resources|Topology)\.tsx'`
Expected: a list of link colors and Chakra-blue components on non-hero/shared files (e.g. `RelatedPanel.tsx:51` Footer `color="blue.500"`).

- [ ] **Step 2: Apply the two rules per hit**

- `color="blue.500"` → `color="link"`.
- `colorScheme="blue"` on a **Button** → delete the prop (inherits the `adi` default). On a **Tag/Badge** → `colorScheme="adi"`.

Example (`src/components/RelatedPanel.tsx:51`):

```tsx
      <Link as={RouterLink} to={to} color="blue.500" fontSize="sm" fontWeight={500}>
```
→
```tsx
      <Link as={RouterLink} to={to} color="link" fontSize="sm" fontWeight={500}>
```

- [ ] **Step 3: Verify no residual Chakra-blue on non-hero/shared files**

Run: `grep -rn 'color="blue.500"\|colorScheme="blue"' src/ | grep -vE 'pages/(Dashboard|Places|PlaceDetail|Resources|Topology)\.tsx'`
Expected: no output.

- [ ] **Step 4: Run the suite**

Run: `npm test`
Expected: PASS (RelatedPanel/DownloadEnvModal/AdminUsers/Login tests assert text/role/href, not color).

- [ ] **Step 5: Commit**

```bash
git add -u src/
git commit -m "style(web): sweep links to brand `link` token + drop Chakra-blue (non-hero)"
```

---

### Task 16: Sweep surfaces + faint grays on non-hero/shared files

**Files (non-hero + shared only):** `src/pages/Reservations.tsx`, `src/pages/EventLog.tsx`, `src/pages/ExporterDetail.tsx`, `src/pages/AdminUsers.tsx`, `src/components/*` (excluding hero-only usages). Skip `Help.tsx` code block and `Statistics.tsx` local `StatCard` (out of scope).

- [ ] **Step 1: Find the candidates**

Run: `grep -rn 'useColorModeValue("white", "gray.800")\|gray.50\|gray.700\|gray.500\|gray.400' src/ | grep -vE 'pages/(Dashboard|Places|PlaceDetail|Resources|Topology)\.tsx|theme/|Help.tsx|Statistics.tsx'`

- [ ] **Step 2: Apply per-hit replacements**

- Card pattern `Box bg={useColorModeValue("white","gray.800")} borderRadius=... shadow=...` → use `<Panel>` (`import Panel from "../components/ui/Panel"` or `./ui/Panel`), dropping the manual `bg`/`shadow`. **Do not** re-nest in a way that changes DOM the tests query (PlaceWizard rows already hardened in Task 14; for any other row queried by tests, keep structure and only swap colors).
- Row-hover/inset `useColorModeValue("gray.50","gray.700")` → `"surface.subtle"`.
- Faint text `color="gray.500"` / `color="gray.400"` that carries real text → `color="text.secondary"` (fixes sub-AA).

- [ ] **Step 3: Run the suite + build**

Run: `npm test && npm run build`
Expected: PASS + clean build.

- [ ] **Step 4: Commit**

```bash
git add -u src/
git commit -m "style(web): sweep surfaces to Panel/surface.subtle + AA text (non-hero)"
```

---

# Phase 4 — Hero pages

### Task 17: Dashboard restyle (MetricCard row + UtilizationBar + StatusPill)

**Files:**
- Modify: `src/pages/Dashboard.tsx`
- Modify: `src/components/ConceptGlanceCard.tsx` (restyle in place — keep name/export; Help.tsx import stays valid)

**Interfaces:**
- Consumes: `MetricCard`, `UtilizationBar`, `StatusPill`, `Panel`.

- [ ] **Step 1: Add imports**

At the top of `src/pages/Dashboard.tsx` add:

```tsx
import MetricCard from "../components/ui/MetricCard";
import UtilizationBar from "../components/ui/UtilizationBar";
import StatusPill from "../components/ui/StatusPill";
import Panel from "../components/ui/Panel";
import { SimpleGrid } from "@chakra-ui/react";
```

- [ ] **Step 2: Compute the places breakdown + resource count**

Just after the existing `labStatus` object (around line 56-60), add (uses only data already in scope — `places`, `placeToExporters`, `exporters` — so no new fetch):

```tsx
  const placesBreakdown = useMemo(() => {
    let free = 0, acquired = 0, offline = 0;
    for (const p of places) {
      const live = (placeToExporters.get(p.name) ?? []).length > 0;
      if (!live) offline += 1;
      else if (p.acquired) acquired += 1;
      else free += 1;
    }
    return { free, acquired, offline, total: places.length };
  }, [places, placeToExporters]);

  const resourceCount = useMemo(
    () => exporters.reduce((n, e) => n + Object.values(e.groups).reduce((m, rs) => m + rs.length, 0), 0),
    [exporters],
  );
```

- [ ] **Step 3: Replace the status badge row with a 4-up MetricCard row**

Replace this block (lines ~222-237):

```tsx
      <HStack spacing={4}>
        <Badge colorScheme="green" fontSize="0.85em" px={3} py={1}>
          <Link as={RouterLink} to="/exporters">{labStatus.exportersOnline} exporters online</Link>
        </Badge>
        <Badge colorScheme="blue" fontSize="0.85em" px={3} py={1}>
          <Link as={RouterLink} to="/places">{labStatus.placesFree} places free</Link>
        </Badge>
        <Badge colorScheme="orange" fontSize="0.85em" px={3} py={1}>
          <Link as={RouterLink} to="/places">{labStatus.placesHeldByOthers} places held by others</Link>
        </Badge>
        {waitingCount > 0 && (
          <Badge colorScheme="yellow" fontSize="0.85em" px={3} py={1}>
            <Link as={RouterLink} to="/reservations">{waitingCount} waiting reservations</Link>
          </Badge>
        )}
      </HStack>
```

with (note: Exporters now links to `/resources`, the dead `/exporters` is gone; Reservations card always renders):

```tsx
      <SimpleGrid columns={{ base: 1, sm: 2, lg: 4 }} spacing={4}>
        <MetricCard label="Exporters" value={`${labStatus.exportersOnline} of ${exporters.length}`} to="/resources" />
        <MetricCard label="Places" value={`${placesBreakdown.total} total`} to="/places">
          <UtilizationBar
            free={placesBreakdown.free}
            acquired={placesBreakdown.acquired}
            offline={placesBreakdown.offline}
          />
        </MetricCard>
        <MetricCard label="Resources" value={`${resourceCount}`} to="/resources" />
        <MetricCard label="Reservations" value={`${waitingCount} waiting`} to="/reservations" />
      </SimpleGrid>
```

- [ ] **Step 4: Restyle the contextual cards + status badges**

In the same file:
- Replace the three `Box bg={cardBg} borderRadius="lg" p={4} shadow="sm"` wrappers (My places, My reservations, Attention needed, Recently used — lines ~119, 151, 240, 251) with `<Panel p={4}>` (remove the now-unused `cardBg`/`useColorModeValue` if no longer referenced).
- The "My places" exporter badges (line ~133) `<Badge colorScheme={e.online ? "green" : "gray"}>` → keep as exporter chips but route color through tokens: change to `<Badge colorScheme={e.online ? "adi" : "gray"}>` (these are exporter identity chips, not place status — keep them as badges, just on-brand).
- Link colors `color="blue.500"` throughout Dashboard (lines ~70,79,88,105,128,168,224-234,255) → `color="link"`.
- "Attention needed" heading `color="orange.500"` → `color="status.acquired"`.
- The My-reservations state `<Badge colorScheme=...>` (line ~173) → leave the lifecycle mapping but on tokens is optional; minimal change: keep as-is (reservation lifecycle, not place health) — only swap its inner link colors.

- [ ] **Step 5: Restyle `ConceptGlanceCard` in place**

In `src/components/ConceptGlanceCard.tsx`: replace the outer `Box borderWidth="1px" borderRadius="md" p={4}` with `<Panel p={4}>` (import `Panel from "./ui/Panel"`), change the `Text color="gray.500"`/`gray.600` to `text.secondary`, and the uppercase header to use `MicroLabel` (`import { MicroLabel } from "./ui/Labels"`). Keep the same `CONCEPTS` data and the three steps. Do **not** rename the component or its default export.

- [ ] **Step 6: Run suite + build + visual**

Run: `npm test && npm run build`
Expected: PASS + clean build.
Then `npm run dev` → verify Dashboard in both modes: 4 stat cards, the Places card shows the segmented bar, cards are hairline panels, all links are ADI blue. Stop dev server.

- [ ] **Step 7: Commit**

```bash
git add src/pages/Dashboard.tsx src/components/ConceptGlanceCard.tsx
git commit -m "feat(web): Dashboard restyle — MetricCard row, utilization bar, panels"
```

---

### Task 18: Places restyle (StatusPill, spec-sheet foot, density toggle)

**Files:**
- Modify: `src/pages/Places.tsx`
- Test: `src/pages/__tests__/Places.test.tsx` (new — locks the StatusPill strings + foot summary, which nothing covers today)

**Interfaces:**
- Consumes: `StatusPill`, `Panel`.

- [ ] **Step 1: Write the failing test**

```tsx
// src/pages/__tests__/Places.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ChakraProvider } from "@chakra-ui/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import theme from "../../theme";
import Places from "../Places";

vi.mock("../../api/ws", () => ({ useWebSocket: () => {} }));
vi.mock("../../hooks/usePlaces", () => ({
  usePlaces: () => ({
    isLoading: false,
    data: [
      { name: "p-free", tags: {}, matches: [], acquired: null, aliases: [], comment: "", acquired_resources: [] },
      { name: "p-held", tags: {}, matches: [], acquired: "travis", aliases: [], comment: "", acquired_resources: [] },
    ],
  }),
  useDeletePlace: () => ({ mutate: vi.fn() }),
  useAcquirePlace: () => ({ mutateAsync: vi.fn() }),
  useReleasePlace: () => ({ mutateAsync: vi.fn() }),
}));
vi.mock("../../hooks/useRelationships", () => ({
  useRelationships: () => ({
    placeToExporters: new Map([["p-free", [{ name: "exp1", online: true }]], ["p-held", [{ name: "exp1", online: true }]]]),
    placeToMissingMatches: new Map(),
    placeHealth: new Map([["p-free", "ready"], ["p-held", "held"]]),
  }),
}));

const wrap = (ui: React.ReactNode) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <ChakraProvider theme={theme}>
      <QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>
    </ChakraProvider>
  );
};

describe("Places", () => {
  beforeEach(() => localStorage.clear());
  it("renders status pills with the expected labels", () => {
    render(wrap(<Places />));
    expect(screen.getByText("ready")).toBeInTheDocument();
    expect(screen.getByText("held")).toBeInTheDocument();
  });
  it("renders the spec-sheet table foot summary", () => {
    render(wrap(<Places />));
    expect(screen.getByText(/2 of 2 · 1 free · 1 acquired/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/pages/__tests__/Places.test.tsx`
Expected: FAIL — `ready`/`held` strings and the foot summary don't exist yet.

- [ ] **Step 3: Convert `renderHealthBadge` to StatusPill**

In `src/pages/Places.tsx`, add imports:

```tsx
import StatusPill from "../components/ui/StatusPill";
import Panel from "../components/ui/Panel";
import { Tfoot } from "@chakra-ui/react";
```

Replace `renderHealthBadge` (lines 33-38):

```tsx
function renderHealthBadge(health: PlaceHealth | undefined, missingCount: number): React.ReactNode {
  if (health === "held") return <Badge colorScheme="orange">⬤ held</Badge>;
  if (health === "degraded") return <Badge colorScheme="red">⚠ {missingCount} not live</Badge>;
  if (health === "ready") return <Badge colorScheme="green">✓ ready</Badge>;
  return <Badge colorScheme="gray">—</Badge>;
}
```

with:

```tsx
function renderHealthBadge(health: PlaceHealth | undefined, missingCount: number): React.ReactNode {
  if (health === "held") return <StatusPill status="acquired">held</StatusPill>;
  if (health === "degraded") return <StatusPill status="degraded">{missingCount} not live</StatusPill>;
  if (health === "ready") return <StatusPill status="free">ready</StatusPill>;
  return <Text as="span" color="text.secondary">—</Text>;
}
```

Also change the acquired badge (line ~130) `<Badge colorScheme="orange">{place.acquired}</Badge>` → `<StatusPill status="acquired">{place.acquired}</StatusPill>`, and the "Create" button (line ~298) `colorScheme="blue"` → remove the prop.

- [ ] **Step 4: Wrap tables in Panel + add the spec-sheet foot**

Change the `PlacesTable` outer container (line ~68) from `Box bg={tableBg} borderRadius="lg" overflow="hidden" shadow="sm"` to `<Panel overflow="hidden">` (drop the `tableBg`/`shadow`; remove unused `useColorModeValue` lines 63-65 if now unused, replacing `rowHoverBg`/`expandedBg` with `"surface.subtle"`).

Add a `<Tfoot>` inside `<Table>` after `</Tbody>` summarizing the table:

```tsx
        </Tbody>
        <Tfoot>
          <Tr>
            <Td colSpan={7} color="text.secondary" fontSize="xs">
              {places.length} of {places.length} ·{" "}
              {places.filter((p) => !p.acquired).length} free ·{" "}
              {places.filter((p) => p.acquired).length} acquired
            </Td>
          </Tr>
        </Tfoot>
```

> The test uses one combined table (`2 of 2 · 1 free · 1 acquired`); in the live page each of the two tables (live/offline) shows its own foot.

- [ ] **Step 5: Add the density toggle (localStorage, default comfortable)**

In the `Places` component, add state near the other `useState`s (line ~222):

```tsx
  const [density, setDensity] = useState<"comfortable" | "compact">(
    () => (localStorage.getItem("places-density") as "comfortable" | "compact") || "comfortable",
  );
  const toggleDensity = () => {
    setDensity((d) => {
      const next = d === "comfortable" ? "compact" : "comfortable";
      localStorage.setItem("places-density", next);
      return next;
    });
  };
```

Add a toggle button in the header `HStack` (line ~296-301), next to "+ New place":

```tsx
        <Button onClick={toggleDensity} size="sm" variant="outline">
          {density === "comfortable" ? "Compact" : "Comfortable"}
        </Button>
```

Pass `density` into `PlacesTable` (add `density` to `PlacesTableProps` and both call sites), and in the name cell render a subtitle from existing place data when compact:

```tsx
                  <Td>
                    <RouterLink to={`/places/${encodeURIComponent(place.name)}`}>
                      <Text color="link" fontWeight="500">{place.name}</Text>
                    </RouterLink>
                    {density === "compact" && (
                      <Text fontSize="xs" color="text.secondary" fontFamily="mono">
                        {Object.entries(place.tags).map(([k, v]) => `${k}=${v}`).join(" · ") || "—"}
                      </Text>
                    )}
                  </Td>
```

(Note the link color `blue.500` → `link` in that cell as part of the change.)

- [ ] **Step 6: Run the suite + build + visual**

Run: `npx vitest run src/pages/__tests__/Places.test.tsx && npm test && npm run build`
Expected: PASS + clean build.
Then `npm run dev` → verify Places: status pills, hairline table with foot summary, the density toggle flips and persists across reload. Stop dev server.

- [ ] **Step 7: Commit**

```bash
git add src/pages/Places.tsx src/pages/__tests__/Places.test.tsx
git commit -m "feat(web): Places restyle — StatusPill, spec-sheet foot, density toggle"
```

---

### Task 19: PlaceDetail restyle

**Files:**
- Modify: `src/pages/PlaceDetail.tsx`

- [ ] **Step 1: Apply the design system**

In `src/pages/PlaceDetail.tsx`:
- Add `import StatusPill from "../components/ui/StatusPill";`.
- Acquired badge (line 162): `<Badge colorScheme="orange">acquired by <Term name="acquire">{owner}</Term></Badge>` → `<StatusPill status="acquired">acquired by <Term name="acquire">{owner}</Term></StatusPill>`.
- Resource avail badge (line 243): `<Badge colorScheme={r.avail ? "green" : "red"}>{r.avail ? "yes" : "no"}</Badge>` → `<StatusPill status={r.avail ? "free" : "degraded"}>{r.avail ? "yes" : "no"}</StatusPill>`.
- Acquire button (line 168) and "+ Add match" button (line 185) and modal "Add match" button (line 312): remove `colorScheme="blue"` (inherit `adi`).
- Link colors `color="blue.500"` (lines 338, 399) → `color="link"`.
- Faint text `color="gray.500"` (lines 180, 191, 226, 305, 331, 340, 377, 382, 396, 404) → `color="text.secondary"`.
- Reservation state badge (line 392): leave the lifecycle mapping as-is (not place health).

- [ ] **Step 2: Run suite + build**

Run: `npm test && npm run build`
Expected: PASS (PlaceDetail.test asserts the acquire button by role + the mutation call; StatusPill preserves accessible text) + clean build.

- [ ] **Step 3: Visual check**

`npm run dev` → open a place detail in both modes; confirm acquired/avail render as pills, buttons are ADI blue, links on-brand. Stop dev server.

- [ ] **Step 4: Commit**

```bash
git add src/pages/PlaceDetail.tsx
git commit -m "feat(web): PlaceDetail restyle — StatusPill, brand links/buttons, AA text"
```

---

### Task 20: Resources restyle (+ `ExporterStatusBadge`)

**Files:**
- Modify: `src/pages/Resources.tsx`
- Modify: `src/components/ExporterStatusBadge.tsx`

- [ ] **Step 1: Resources page**

In `src/pages/Resources.tsx`:
- Add `import StatusPill from "../components/ui/StatusPill";` and `import Panel from "../components/ui/Panel";`.
- Table container (line 110) `Box bg={tableBg} borderRadius="lg" overflow="hidden" shadow="sm"` → `<Panel overflow="hidden">` (remove `tableBg` and its `useColorModeValue` import if unused; the two `bg={tableBg}` on the `Select`s at lines 72/86 → `bg="surface.bg"`).
- Avail badge (line 135) `<Badge colorScheme={r.avail ? "green" : "red"}>{r.avail ? "Yes" : "No"}</Badge>` → `<StatusPill status={r.avail ? "free" : "degraded"}>{r.avail ? "Yes" : "No"}</StatusPill>`.
- Acquired badge (line 141) `<Badge colorScheme="orange">{r.acquired}</Badge>` → `<StatusPill status="acquired">{r.acquired}</StatusPill>`.
- "Matched by" tags (line 160) `colorScheme={p.acquired ? "orange" : "green"}` → keep as tags but on tokens: `colorScheme={p.acquired ? "orange" : "green"}` is acceptable as identity chips; minimal change — leave, or change the faint `color="gray.400"` (line 153) "—" → `color="text.secondary"`.

- [ ] **Step 2: ExporterStatusBadge**

In `src/components/ExporterStatusBadge.tsx`, keep the three-way semantics but route colors through status tokens for both-mode consistency (it is **not** folded into StatusPill):

```tsx
import { Badge } from "@chakra-ui/react";
import type { Resource } from "../api/client";

export default function ExporterStatusBadge({ resources }: { resources: Resource[] }) {
  if (resources.length === 0) return <Badge colorScheme="gray">No resources</Badge>;
  const availCount = resources.filter((r) => r.avail).length;
  const total = resources.length;
  if (availCount === total) return <Badge colorScheme="green">All available</Badge>;
  if (availCount === 0) return <Badge colorScheme="red">Unavailable</Badge>;
  return <Badge colorScheme="yellow">{availCount}/{total} available</Badge>;
}
```

(Text preserved exactly; only confirm it still renders. No structural change required — leave as-is if already correct.)

- [ ] **Step 3: Run suite + build + visual**

Run: `npm test && npm run build`
Expected: PASS + clean build. Then `npm run dev` → verify Resources in both modes.

- [ ] **Step 4: Commit**

```bash
git add src/pages/Resources.tsx src/components/ExporterStatusBadge.tsx
git commit -m "feat(web): Resources restyle — StatusPill, Panel table, AA text"
```

---

### Task 21: Topology restyle (canvas + legend, preserve strings)

**Files:**
- Modify: `src/pages/Topology.tsx`

**Constraint:** keep the legend strings `"Places (free)"`, `"Places (held)"`, and `"Match rules"` exactly (asserted by `Topology.test`).

- [ ] **Step 1: Tokenize canvas + legend surfaces**

In `src/pages/Topology.tsx`:
- Canvas/minimap background hexes (lines 228-229): update to the new palette —
  `const bgColor = useColorModeValue("#fafbfc", "#0b0f14");`
  `const miniMapBg = useColorModeValue("#e4e8ec", "#161f2a");`
- Legend container background (line 230) `const legendBg = useColorModeValue("gray.50", "gray.700");` → `const legendBg = "surface.subtle";`
- Outer canvas border (line 345) `borderColor={useColorModeValue("gray.200", "gray.600")}` → `borderColor="border.hairline"`.
- Legend `LegendRow` gloss text (line 376) `color="gray.600"` → `color="text.secondary"`; the "Match rules" paragraph `color="gray.500"` (line 307) → `color="text.secondary"`.
- Empty-state text (line 335) `color="gray.500"` → `color="text.secondary"`.

The node/edge colors already use concept hexes (`EXPORTER_COLOR` etc., matching `concepts.ts`) — leave them; they read correctly on both canvas backgrounds.

- [ ] **Step 2: Run the Topology suite + build**

Run: `npx vitest run src/pages/__tests__/Topology.test.tsx && npm run build`
Expected: PASS (legend strings unchanged) + clean build.

- [ ] **Step 3: Visual check**

`npm run dev` → open Topology in both modes; confirm canvas/legend match the new palette and node colors stay legible. Stop dev server.

- [ ] **Step 4: Commit**

```bash
git add src/pages/Topology.tsx
git commit -m "feat(web): Topology restyle — palette canvas + legend, strings preserved"
```

---

# Phase 5 — Final QA

### Task 22: Full verification pass

**Files:** none (verification + any residual fixes).

- [ ] **Step 1: No residual Chakra-blue or faint-text anywhere**

Run: `grep -rn 'color="blue.500"\|colorScheme="blue"\|gray.400' src/ | grep -v '__tests__'`
Expected: no output. (If any remain, fix per the Phase 3 rules and re-run.)

- [ ] **Step 2: Full test suite**

Run: `npm test`
Expected: ALL tests PASS (existing + the new theme/ui/Places tests).

- [ ] **Step 3: Type-check + production build**

Run: `npm run build`
Expected: `tsc -b` + `vite build` succeed, no type errors.

- [ ] **Step 4: Both-mode manual QA**

Run: `npm run dev`. Walk every page (Dashboard, Resources, Places, PlaceDetail, Reservations, Topology, Statistics, Event Log, Recordings, Help, Login, Admin Users, PlaceWizard) in **both** light and dark via the header toggle. Confirm: ADI-blue accents only (no Chakra blue), hairline surfaces, legible text everywhere, status pills/LEDs consistent, no clashing terminal/player surfaces (Console/RecordingPlayer). Stop the dev server.

- [ ] **Step 5: Commit any residual fixes**

```bash
git add -u src/
git commit -m "chore(web): final both-mode QA fixes for dashboard restyle"
```

(If Step 5 found nothing to fix, skip the commit.)

---

## Spec coverage map

| Spec section | Task(s) |
|---|---|
| §5 tokens (palette, status, surface.subtle, link/accent.text alias) | 1, 2 |
| §6 typography + index.html fonts | 1, 5 |
| §7 theme architecture (split, anatomy multipart) | 1–4 |
| §8 primitives (Panel, MetricCard, StatusPill/Dot, UtilizationBar, labels) | 7–11 |
| §8 ConceptGlanceCard restyle-in-place; ExporterStatusBadge stays separate | 17, 20 |
| §9 Layout (lit nav + aria-current, ChipIcon currentColor + call-site color) | 6, 12, 13 |
| §10 Dashboard (MetricCard row, utilization bar, link fix) | 17 |
| §10 Places (StatusPill, spec-sheet foot, density toggle) | 18 |
| §10 PlaceDetail / Resources / Topology | 19, 20, 21 |
| §11 sweep (links, colorScheme="blue", surfaces, accent.text retained) | 15, 16 (+ hero tasks for hero files) |
| §12 testing (PlaceWizard hardening, new primitive/Places tests, reviewed-safe) | 14, 18, + per-task suites |
| §13 rollout phases | Phases 1–5 |
| §4 exceptions (density toggle, /exporters→/resources) | 18, 17 |
