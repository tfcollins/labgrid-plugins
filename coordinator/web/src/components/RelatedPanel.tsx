import { Box, Heading, Link, VStack } from "@chakra-ui/react";
import { Link as RouterLink } from "react-router-dom";

/** Compound presentational shell used by detail pages to render the "other
 * side" of a relationship. Call sites pass pre-computed content; the panel
 * only lays out the sections and a footer link. */
function RelatedPanel({ children }: { children: React.ReactNode }) {
  return (
    <Box
      as="aside"
      borderWidth="1px"
      borderRadius="md"
      p={4}
      minW={{ base: "full", md: "280px" }}
      alignSelf="flex-start"
    >
      <VStack align="stretch" spacing={5}>
        {children}
      </VStack>
    </Box>
  );
}

interface SectionProps {
  title: string;
  tone?: "default" | "warning";
  children: React.ReactNode;
}

function Section({ title, tone = "default", children }: SectionProps) {
  const color = tone === "warning" ? "status.acquired" : "text.secondary";
  return (
    <VStack align="stretch" spacing={2}>
      <Heading
        size="xs"
        textTransform="uppercase"
        letterSpacing="wider"
        color={color}
        data-tone={tone}
      >
        {title}
      </Heading>
      <Box fontSize="sm">{children}</Box>
    </VStack>
  );
}

function Footer({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <Box pt={2} borderTopWidth="1px">
      <Link as={RouterLink} to={to} color="link" fontSize="sm" fontWeight={500}>
        {children}
      </Link>
    </Box>
  );
}

RelatedPanel.Section = Section;
RelatedPanel.Footer = Footer;
export default RelatedPanel;
