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
