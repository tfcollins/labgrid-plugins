import { extendTheme, type ThemeConfig } from "@chakra-ui/react";

const config: ThemeConfig = {
  initialColorMode: "light",
  useSystemColorMode: true,
};

const theme = extendTheme({
  config,
  colors: {
    // ADI brand blue palette derived from analog.com branding
    // Primary: #0071ba (--adi-blue from docs/source/_static/custom.css)
    // Dark: #003d71 (--adi-dark-blue)
    // Accent: #1e9bd7 (from lg_adi_light.svg)
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
  },
  fonts: {
    heading: '"Inter", system-ui, sans-serif',
    body: '"Inter", system-ui, sans-serif',
  },
  semanticTokens: {
    colors: {
      "sidebar.bg": { default: "#003d71", _dark: "#001f3d" },
      "sidebar.text": { default: "#e6edf3", _dark: "#e6edf3" },
      "sidebar.hover": { default: "#004d85", _dark: "#003d71" },
      "surface.bg": { default: "white", _dark: "gray.800" },
      "text.primary": { default: "#2f3e46", _dark: "#e6edf3" },
      "text.secondary": { default: "gray.600", _dark: "gray.400" },
      "accent.text": { default: "#1e9bd7", _dark: "#4db8ff" },
    },
  },
  components: {
    Button: {
      defaultProps: { colorScheme: "adi" },
    },
    Badge: {
      defaultProps: { colorScheme: "adi" },
    },
  },
});

export default theme;
