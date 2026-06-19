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
