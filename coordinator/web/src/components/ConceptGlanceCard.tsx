// coordinator/web/src/components/ConceptGlanceCard.tsx
import { Box, HStack, Text, VStack } from "@chakra-ui/react";
import { MdArrowForward } from "react-icons/md";
import { CONCEPTS, type ConceptName } from "../concepts";
import Panel from "./ui/Panel";
import { MicroLabel } from "./ui/Labels";

/** Three-up "Exporter → Resource → Place" reference card. Permanent;
 * not dismissible. Uses the same colors as the Topology legend. */
export default function ConceptGlanceCard() {
  const steps: ConceptName[] = ["exporter", "resource", "place"];
  return (
    <Panel p={4}>
      <MicroLabel mb={2}>How it fits together</MicroLabel>
      <HStack align="stretch" spacing={4}>
        {steps.map((s, i) => (
          <HStack key={s} spacing={4} flex="1">
            <VStack align="flex-start" spacing={1} flex="1">
              <Box bg={CONCEPTS[s].color} color="white" px={2} py={0.5} borderRadius="sm" fontSize="xs">
                {CONCEPTS[s].label}
              </Box>
              <Text fontSize="xs" color="text.secondary">{CONCEPTS[s].gloss}</Text>
            </VStack>
            {i < steps.length - 1 && <MdArrowForward color="#A0AEC0" />}
          </HStack>
        ))}
      </HStack>
    </Panel>
  );
}
