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
