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
