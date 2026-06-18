# Coordinator Dashboard Restyle — Design Spec

- **Date:** 2026-06-18
- **Status:** Approved (design); pending implementation plan
- **Scope target:** `coordinator/web` (React 18 + Vite + TypeScript + Chakra UI v2.8.2)
- **Owner:** Travis Collins

## 1. Summary

Restyle the entire labgrid coordinator dashboard to a single, cohesive, premium aesthetic —
**"Instrument Precision"** (Swiss/technical minimalism) — that honors and elevates the ADI brand,
treats **light and dark as co-equal first-class themes**, and is built for **data-dense daily use** by
hardware/test engineers. This is a **presentation-only** change: no API, routing, data-fetching, or
behavioral changes (two small, explicitly carved-out exceptions are noted in §4). Three selective grafts add
authored personality without compromising the constraints.

The direction was chosen by building three full HTML mockups (Instrument Precision, Signal/Bench Console,
Editorial Datasheet), scoring them with a design critic, and selecting Instrument Precision as the base
because it was the only direction satisfying all three hard constraints simultaneously (ADI-as-structural-accent,
co-equal modes, daily-scan density). Mockups are **kept** under `coordinator/web/design-explorations/` as visual
reference (see §13/§16).

## 2. Decisions locked

| Decision | Choice |
|---|---|
| Scope | Restyle the **whole dashboard**, keep all functionality |
| Brand envelope | **Honor & elevate ADI** — `#0071ba` stays the anchor; bold in craft, conservative in identity |
| Color mode | **Both light and dark first-class** (each fully art-directed, not a lazy invert) |
| Aesthetic | **Instrument Precision** base + grafts (below) |
| Code depth | **Theme + shared shell + hero pages**; non-hero pages get a token-level sweep only |

**Grafts onto the base:**
- From *Signal/Bench Console* (B): a **lit channel-indicator** active-nav treatment, and **one** restrained
  **segmented utilization bar** in a single spotlight stat card (Places: free/acquired/offline proportions from the
  **real instantaneous counts** — no time-series, no fabricated data). Glow dialed way down — no per-element neon.
- From *Editorial Datasheet* (C): a **ruled spec-sheet table foot** summary on the Places table, and an
  optional **density toggle** (comfortable/compact; compact adds a per-row metadata subtitle from existing place data).

> Note on the utilization bar: the original "sparkline" graft was dropped because the dashboard has only
> instantaneous scalar counts and no time-series source; a sparkline would require fabricated or new data,
> violating the no-data-flow non-goal. The segmented utilization bar conveys the same instrument character using
> data already present.

## 3. Current state (what we're working with)

- **Theme:** `src/theme.ts` (Chakra `extendTheme`). Defines the `adi.*` blue palette, `Inter` for heading+body, and
  semantic tokens: `sidebar.bg/text/hover`, `surface.bg`, `text.primary`, `text.secondary`, **`accent.text`**
  (default `#1e9bd7` / `_dark #4db8ff`, consumed by `Statistics.tsx:42`). Button/Badge default to `colorScheme="adi"`.
- **Fonts today:** `coordinator/web/index.html` loads **only Inter** via a Google Fonts `<link>`; there are **no**
  `<link rel="preconnect">` lines yet.
- **Provider:** `src/main.tsx` wraps `<ChakraProvider theme>` + `ColorModeScript` + React Query + Router + Auth.
- **Domain color system:** `src/concepts.ts` — single source of truth mapping each of 8 domain nouns to a fixed
  color + gloss; colors already match the status palette below. **Keep and reuse.**
- **Routing:** `src/App.tsx` renders `<Layout>` around **16 page routes + a `*` catch-all redirect**.
- **Color mode toggle:** **already implemented** in `Layout.tsx` (`useColorMode`/`toggleColorMode`, lines 118/181).
- **Pages (16):** Dashboard, Places, PlaceDetail, PlaceWizard, Resources, Reservations, Topology, Statistics,
  EventLog, ExporterDetail, Console, Recordings, RecordingPlayer, Login, AdminUsers, Help.
- **Hero pages (bespoke):** Dashboard, Places, PlaceDetail, Topology, Resources.
- **Libraries in use** (`package.json`, verified): `@chakra-ui/react@^2.8.2`, `reactflow`, `xterm`, `asciinema-player`,
  `framer-motion`, `@tanstack/react-query`, `react-router-dom`.

### Off-brand / ad-hoc usages found (the sweep must address these — counts verified by grep)

- **Chakra-blue links:** `color="blue.500"` (`#3182ce`, **13 occurrences**) for links — off-brand vs `adi.500`
  (`#0071ba`). (`blue.400`/`blue.600` do **not** appear anywhere — earlier draft was wrong.)
- **Chakra-blue components:** `colorScheme="blue"` (**17 occurrences**) — mostly primary `<Button>` (PlaceDetail
  acquire/match, AdminUsers, Login, PlaceWizard submit, Places "Create", DownloadEnvModal, Reservations) plus a few
  Tags (PlaceWizard, Dashboard reservation chip) and a Badge (Dashboard "places free"). These **override** the
  theme's `colorScheme:"adi"` default, so without a sweep every primary button stays Chakra-blue — defeating the
  "unmistakably ADI" goal.
- **Ad-hoc cards:** `Box bg={useColorModeValue("white","gray.800")} borderRadius="lg" shadow="sm"` repeated inline.
- **Ad-hoc status:** `<Badge colorScheme="green|orange|red|yellow|gray">` and glyph badges (`✓ ready`, `⬤ held`,
  `⚠ N not live`, `—`) scattered (see §8 for the mapping). **These status glyphs are NOT covered by any test today**
  (no Places/Dashboard/Resources test exists), so they are unverified — treat as regression-prone, not test-protected.
- **Row-hover backgrounds:** `useColorModeValue("gray.50","gray.700")` (Places, PlaceWizard, Topology legend,
  ExporterDetail) — a *subtle surface*, distinct from page background.
- **Page background:** the `useColorModeValue("gray.50","gray.900")` page pattern exists in exactly **one** place,
  `Layout.tsx:190`.
- **`ChipIcon`** hardcodes stroke `#e6edf3` across ~16 attributes (built for the dark sidebar); must use
  `currentColor`, and its call site must supply a color context (see §9).

## 4. Goals / Non-goals

**Goals**
- A cohesive, distinctive, premium look across the whole app, unmistakably ADI.
- Light and dark both fully art-directed and AA-accessible.
- Centralize design decisions (tokens + primitives) so future pages inherit the look for free.
- Preserve user-facing behavior, text, routes, and ARIA (except the two carve-outs below).

**Non-goals (with two explicit, bounded exceptions)**
- No API, backend (`coordinator/api`), data-fetching, or routing changes.
- No new pages.
- No layout redesign of non-hero pages (token-level restyle only).
- No deep reskin of terminal (xterm) / player (asciinema) internals beyond a matching theme so they don't clash.
- **Exception 1 — density toggle:** the Places density toggle (comfortable/compact) is an intentional, in-scope
  micro-feature. Local UI state only, default **comfortable**, persisted to `localStorage`. No data fetching.
- **Exception 2 — dead-link fix:** the Dashboard "exporters online" figure currently links to `/exporters`, which is
  not a registered route (only `/exporters/:name` exists) and silently redirects to `/`. The restyle repoints it to a
  valid target (`/resources`). This is a deliberate, documented correction, not a silent behavior change.

## 5. Design language (tokens)

### Palette (both modes)

| Token | Light | Dark |
|---|---|---|
| `page.bg` | `#fafbfc` | `#0b0f14` |
| `surface.bg` (cards) | `#ffffff` | `#0e141b` |
| `surface.raised` | `#ffffff` | `#121a24` |
| `surface.subtle` (row hover / inset) | `#f3f5f7` | `#161f2a` |
| `border.hairline` | `#e4e8ec` | `#1c2530` |
| `text.primary` | `#1a2430` | `#e6edf3` |
| `text.secondary` (≥4.5:1) | `#52606d` | `#9fb0c0` |
| `accent` (ADI) | `adi.500 #0071ba` | `adi.400 #1e9bd7` |
| `link` | → references `accent` | → references `accent` |
| `accent.text` (retained alias) | → references `accent` | → references `accent` |

- ADI blue is the **single structural accent** (active nav, key figures, focus rings, the utilization bar).
- `link` and `accent.text` are defined in `semanticTokens.ts` as **references to the `accent` token** so they resolve
  per-mode automatically. `accent.text` is **retained as an alias** (not dropped) so `Statistics.tsx:42` keeps working.

### Status tokens (new — single source of truth)

| Token | Color | Meaning |
|---|---|---|
| `status.free` | `#38a169` | free / ready / available |
| `status.acquired` | `#dd6b20` | acquired / held |
| `status.offline` | `#718096` | offline / unavailable / none |
| `status.degraded` | `#e53e3e` | degraded / broken matches |
| `status.reservation` | `#ecc94b` | reservation waiting/queued |

Concept colors remain sourced from `concepts.ts` (used by Topology, the concepts card, etc.).

### Shape & rhythm
- Small consistent radii (~4–6px); near-square data containers.
- **Hairline 1px borders instead of drop shadows** (shadows reserved for overlays/menus only).
- Tiny uppercase tracked micro-labels: `~11px`, `letter-spacing ~0.14em`, `text.secondary`.
- 8px spacing rhythm.

### Accessibility (hard requirement)
- All text-bearing foreground ≥ **4.5:1** (body) / **3:1** (large text & UI affordances), in **both** modes.
- The faint gray `#97a2ad` (2.6:1) and any sub-AA value must **never** carry status text, column headers, or labels.
  Decorative-only hairlines/rulers may be faint.

## 6. Typography

- **Display / headings / stat values:** **Hanken Grotesk** (700/800).
- **Body / UI text:** **Public Sans**.
- **Data (place names, IDs, uptimes, counts, micro-labels):** **IBM Plex Mono** with `tabular-nums`.
- **Inter is removed.**
- In `coordinator/web/index.html`: **replace** the existing Inter `<link>` with the three new families (don't leave
  Inter as dead weight), and **add** `<link rel="preconnect">` for `fonts.googleapis.com` and `fonts.gstatic.com`
  (none exist today). Use `display=swap`. Update theme `fonts.heading/body/mono`.

## 7. Theme architecture

Split the growing single-file theme into a folder:

```
src/theme/
  index.ts          # extendTheme() assembled from the parts; default export
  tokens.ts         # raw scales: adi.*, neutral grays, status.* raw values, radii, fonts
  semanticTokens.ts # page.bg, surface.bg/raised/subtle, border.hairline, text.*, accent, link, accent.text, status.*
  components.ts      # Chakra component overrides (below)
```

`src/main.tsx` import path stays `./theme` (resolves to the folder `index.ts`).

**Component overrides** (`components.ts`): Button, Badge, Tag, Table, Heading, Link, Code, Input, Menu, Card.
For built-in **multipart** components (Table, Menu) use `createMultiStyleConfigHelpers(<anatomy>.keys)` with the
anatomy part keys imported from `@chakra-ui/anatomy` (`tableAnatomy.keys`, `menuAnatomy.keys`) — not an arbitrary
parts array. Buttons/badges keep `colorScheme="adi"` default and adopt the new shape language (square-ish, hairline
outline variants). **Keep `accent.text` defined** in `semanticTokens.ts` (alias of `accent`).

## 8. Shared primitives (new `src/components/ui/`)

| Component | Purpose | Replaces / relationship |
|---|---|---|
| `Panel` | Hairline-bordered surface container | inline `Box bg=card borderRadius shadow` (with carve-outs, §11) |
| `MetricCard` | Tracked label + large value + optional utilization bar + link | Dashboard badge row. **Named `MetricCard`** to avoid colliding with the unrelated local `StatCard` inside `Statistics.tsx` |
| `StatusPill` | Pill for place/resource health from `status.*` tokens | scattered `<Badge colorScheme=...>` health badges |
| `StatusDot` (LED) | Small status indicator; subtle pulse on `free`/`acquired` only, low glow | glyph badges (`⬤`, `✓`) |
| `UtilizationBar` | Thin segmented proportion bar from counts | the (dropped) sparkline; used in one spotlight MetricCard |
| `MicroLabel` / `SectionLabel` | Uppercase tracked label helpers | ad-hoc `Text textTransform=uppercase` |

**Status mapping & exact labels** (StatusPill/StatusDot; preserve the dynamic count):

| Current | New | Visible label |
|---|---|---|
| `✓ ready` (green) | StatusPill `status=free` | `ready` |
| `⬤ held` (orange) | StatusPill `status=acquired` | `held` |
| `⚠ {missingCount} not live` (red) | StatusPill `status=degraded` | `{missingCount} not live` (count preserved) |
| `—` (none) | plain em-dash text (not a pill) | `—` |

- **StatusPill enum:** `free | acquired | offline | degraded | reservation`. New tests must lock the visible strings
  above (no existing test does).
- **Reservation lifecycle badges** (Dashboard My-reservations: `waiting/allocated/acquired/expired/invalid`) are
  **not** folded into StatusPill (different axis); they are restyled to tokens (`waiting → status.reservation`,
  `allocated → accent`, `acquired → status.free`, `expired/invalid → status.offline`).
- **`ExporterStatusBadge` stays a separate component** (its `All available / N/total / Unavailable` semantics don't
  map onto the place enum). It is restyled to use status tokens; it is **not** replaced by StatusPill.
- **`ConceptGlanceCard` is restyled in place** (keep the file name and export; it's imported by **both** `Dashboard.tsx`
  and `Help.tsx`, so renaming would force a change to non-hero `Help.tsx`). No second "ConceptLegend" component exists.

**Testability contracts** (so the new tests in §12 are reliable):
- `UtilizationBar` renders with `role="img"` + an `aria-label` (also an a11y win); segments are assertable.
- `MetricCard` renders its link target as an actual `RouterLink`/`<a>` (assertable via `getByRole("link")`) and its
  value in a stable element.
- The active nav item exposes `aria-current="page"` (see §9).

## 9. Shell — `Layout.tsx`

- **Color-mode toggle already exists** (`Layout.tsx:118/181) — it is **retained, not added**. The real work is moving
  the sidebar/header colors onto semantic tokens so **dark mode is fully art-directed** (today the sidebar is a fixed
  navy regardless of mode).
- **Sidebar:** active nav item gets a **lit channel-indicator** (vertical `accent` bar + subtle lit/raised state;
  glow minimal) **and** exposes **`aria-current="page"`** when active (a11y win + stable test hook; mirrors the
  existing `data-tone` convention used by `RelatedPanel`).
- **`ChipIcon`:** change hardcoded `#e6edf3` strokes to `currentColor`, **and** have the call site
  (`Layout.tsx:136`) supply the color context (e.g. wrap in a `Box color="sidebar.text"` or pass a `color` prop) —
  otherwise `currentColor` resolves to the default text color, not the sidebar foreground.
- **Header:** page title (left) + the retained light/dark toggle + `AccountMenu` chip (right).
- **Optional signature:** a thin "calibration ruler" footer strip (1px ticks) — decorative-only, low-cost.

## 10. Hero pages (bespoke layout polish)

- **Dashboard** — Replace the top status-badge row with a fixed **4-up `MetricCard` row**, all four always rendered
  (the Reservations card shows `0` rather than disappearing, for a stable grid). Values derive **only** from the
  Dashboard's already-fetched hooks (`usePlaces`, `useExporters`, `useReservationsLive`, `useRelationships`) — no new
  fetch:
  - **Exporters** — `{online}/{total}` → links to `/resources` (replaces the dead `/exporters` link, §4 Exception 2).
  - **Places** — total, carrying the **`UtilizationBar`** (free `status.free` / acquired `status.acquired` /
    offline `status.offline`) → links to `/places`. This card supersedes the old separate "places free" /
    "places held by others" badges; per-user "my places" remains in the My-places table.
  - **Resources** — count (from existing resource data in the above hooks) → links to `/resources`.
  - **Reservations** — waiting count (always shown) → links to `/reservations`.
  Restyle the existing My-places / My-reservations tables, Attention-needed, Recently-used, and the
  (restyled-in-place) `ConceptGlanceCard`. **All existing logic, conditionals, and data hooks are preserved** — only
  presentation and which existing values are surfaced as cards changes.
- **Places** — `StatusPill`/`StatusDot` for health/acquired; hairline **spec-sheet table**; a **table-foot summary**
  with the exact format **`{N} of {M} · {X} free · {Y} acquired`**, where `M = livePlaces.length + offlinePlaces.length`,
  `N` = rows shown in that table, `X`/`Y` computed from the existing `places` data (no new fetch); an optional
  **density toggle** (default **comfortable**, persisted to `localStorage`; **compact** adds a per-row subtitle built
  from the place's **existing** `tags`/backing-group data — no new fetch). Keep live/offline split, expand rows,
  bulk-delete, acquire/release behavior. **Carve-out:** do **not** wrap the PlaceWizard-style per-row containers in
  `Panel` if doing so changes DOM nesting that tests query (see §11/§12).
- **PlaceDetail** — restyle to `Panel`/`StatusPill`/mono data; behavior unchanged.
- **Resources** — restyle to `Panel`/`StatusPill` (and restyled `ExporterStatusBadge`); behavior unchanged.
- **Topology** — theme the `reactflow` nodes/edges/canvas to the concept colors and both modes; restyle the legend
  **but keep the exact legend strings** `"Places (free)"`, `"Places (held)"`, and `"Match rules"` (asserted by
  `Topology.test`).

## 11. Global token sweep (semantic, not blind grep — all pages)

Grep is used to **find candidates**; each replacement requires per-site judgment so buttons/info-badges aren't
miscolored. Rules:

1. **Links:** `color="blue.500"` (13 sites) → `link` token. (No `blue.400/.600` exist.)
2. **Cards:** inline `Box bg={useColorModeValue("white","gray.800")} …` → `<Panel>` — **except** per-row selection
   containers whose DOM nesting is queried by tests (PlaceWizard per-group rows; see §12). Those get token-level color
   only, preserving structure.
3. **Status badges → StatusPill (allowlist only):** convert **only** badges that denote place/resource health/state:
   `Places.tsx` `renderHealthBadge` (ready/held/degraded/none) and acquired badge; `Resources`/`ExporterDetail`
   acquired/availability badges (via restyled `ExporterStatusBadge`); Dashboard My-places exporter online/offline
   badges. **Exclude** (do not convert): destructive `colorScheme="red"` **Buttons** (delete/release in AdminUsers,
   Recordings, Reservations, Dashboard, PlaceDetail) and **informational** badges (e.g. DownloadEnvModal
   `Strategy: {…}`, AdminUsers `disabled`). `colorScheme` on `Button` is never touched by this rule.
4. **Chakra-blue components:** `colorScheme="blue"` (17 sites) → on **Buttons**, remove the prop (inherit the `adi`
   default); on **Tags/Badges**, change to `adi` (the Dashboard "places free" badge instead moves into the Places
   MetricCard with `status.free`).
5. **Surfaces:** `useColorModeValue("gray.50","gray.700")` row-hover/inset usages (Places:64-65, PlaceWizard:62,
   Topology:230, ExporterDetail:151/204) → `surface.subtle`. The single page-bg pattern
   `useColorModeValue("gray.50","gray.900")` at `Layout.tsx:190` → `page.bg`. `Help.tsx` `gray.800/gray.900` code
   block is left as-is (out of scope).
6. **`accent.text`:** keep the token (alias of `accent`); `Statistics.tsx:42` is **not** touched.

**Grep seed (candidates, expect false positives):**
`grep -rn 'blue\.500\|colorScheme="blue"\|colorScheme="green"\|colorScheme="orange"\|colorScheme="yellow"\|colorScheme="red"\|gray\.800\|gray\.50\|gray\.700\|gray\.900' coordinator/web/src/`
After the sweep, the diff must contain **no** residual `blue.500` or `colorScheme="blue"`.

## 12. Testing strategy

**Constraint:** preserve all user-facing text, ARIA labels, roles, routes, and behavior. `npm test` (vitest) is the
gate and must stay green at every checkpoint.

- **Reviewed-safe** (assert only on behavior/data-text/role — the restyle does not touch what they assert):
  `PlaceDetail.test`, `Topology.test` (safe **iff** the legend keeps the exact strings in §10), `Recordings.test`,
  `AdminUsers.test`, `Login.test`, `ConceptHeading.test`, `RelatedPanel.test` (preserve its `data-tone` attribute on
  the section heading), `DownloadEnvModal.test`.
- **Genuinely at-risk:**
  - **`PlaceWizard.test`** — three tests select the group checkbox by DOM walk
    (`findByText(...).closest("div")?.parentElement?.querySelector('input[type=checkbox]')`). The §11 rule-2 carve-out
    (don't re-nest those rows) protects them. *Preferred hardening:* give each Checkbox an `aria-label`
    (`Select group ${exporter}/${group}`) and switch the tests to `getByRole("checkbox",{name})`, after which the row
    may be freely restyled.
  - **`Term.test`** — the only CSS assertion in the suite (`text-decoration-style: dotted`). `Term.tsx` is **out of
    scope**; leave it untouched.
- **Coverage gap to note:** the hero pages most affected (Dashboard, Places, Resources) have **no existing tests**, and
  the status glyphs are asserted nowhere — so the status changes are currently unverified. New tests below add coverage.
- **New tests:**
  - `StatusPill` — correct color + exact label per enum value, including degraded `{n} not live` count.
  - `MetricCard` — renders label/value and its link target as a `RouterLink` (`getByRole("link")`).
  - `UtilizationBar` — `role="img"` present; segment count/proportions for a given counts input.
  - `Layout` active-nav — the active route's NavItem exposes `aria-current="page"`.
- **Manual verification:** run the Vite dev server; exercise both light and dark on every hero page; confirm no
  contrast regressions and no clashing terminal/player surfaces.

## 13. Rollout (incremental, reviewable checkpoints)

Each phase ends green (build + `npm test`) and is visually verified in both modes before the next. Primitives
(Phase 2) are a hard prerequisite for the hero pages (Phase 4).

1. **Theme foundation + fonts** — `src/theme/` split; palette/status/semantic tokens (incl. `surface.subtle`,
   `link`, retained `accent.text`); component overrides (anatomy-based for Table/Menu); replace Inter + add preconnect
   in `index.html`; `ChipIcon` → `currentColor` + call-site color context. App restyles globally, no structural change.
2. **Primitives + Layout shell** — build `src/components/ui/*` (`Panel`, `MetricCard`, `StatusPill`, `StatusDot`,
   `UtilizationBar`, label helpers); rebuild `Layout` (lit nav + `aria-current`, header, optional footer).
3. **Global token sweep** — apply the §11 rules (links, blue components, status allowlist, surfaces), with the
   PlaceWizard carve-out (or test hardening) done first.
4. **Hero pages** — Dashboard → Places → PlaceDetail → Resources → Topology, one at a time.
5. **Final QA** — both-mode pass across all pages; `design-explorations/` is **kept** as reference.

## 14. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Status/blue sweep needs per-site semantic judgment (not pure grep) | §11 uses an explicit allow/exclude list; review diff for residual `blue.500`/`colorScheme="blue"` |
| PlaceWizard structural DOM-walk tests break on re-nesting | Carve-out in §11 rule 2, or harden tests with `aria-label` + `getByRole` first |
| `accent.text` dropped would break `Statistics.tsx:42` | Retain as alias of `accent` (§5/§7/§11) |
| Chakra v2 multipart theming (Table, Menu) | Use `createMultiStyleConfigHelpers` with `@chakra-ui/anatomy` part keys |
| `reactflow` themes via its own props/CSS vars | Pass node/edge styles from concept tokens; set canvas bg per mode |
| xterm / asciinema separate theming surfaces | Matching theme object only; no internal reskin (out of scope) |
| FOUT on first paint | `display=swap` + preconnect |
| Sub-AA contrast (the B/C failure modes) | Enforce AA in both modes; ADI blue only as accent; no faint text |

## 15. Out of scope

API/backend (`coordinator/api`)/route/data-fetching changes; new pages; non-hero page layout redesigns;
terminal/player internal reskins; `Term.tsx`, `Statistics.tsx` local `StatCard`, and `Help.tsx` code block.

## 16. References

- Mockups (kept): `coordinator/web/design-explorations/{01-instrument-precision,02-signal-bench-console,03-editorial-datasheet}.html`
- Critic scorecard (1–10): A Instrument Precision 7/9/9/9 · B Signal Bench 8/7/6/6 · C Editorial 9/6/5/5
  (distinctiveness / ADI-credibility / both-mode quality / engineer-fit).
- Domain color source of truth: `coordinator/web/src/concepts.ts`.
- Spec adversarial review (2026-06-18): consistency / codebase-feasibility / test-risk / planning-readiness — all
  accepted findings folded into this revision.
