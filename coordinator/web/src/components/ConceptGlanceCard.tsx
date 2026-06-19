// coordinator/web/src/components/ConceptGlanceCard.tsx
import { Box, HStack, Text, VStack } from "@chakra-ui/react";
import { MdArrowForward } from "react-icons/md";
import { CONCEPTS, type ConceptName } from "../concepts";

/** Three-up "Exporter → Resource → Place" reference card. Permanent;
 * not dismissible. Uses the same colors as the Topology legend. */
export default function ConceptGlanceCard() {
  const steps: ConceptName[] = ["exporter", "resource", "place"];
  return (
    <Box borderWidth="1px" borderRadius="md" p={4}>
      <Text fontSize="xs" color="text.secondary" mb={2} textTransform="uppercase" letterSpacing="wider">
        How it fits together
      </Text>
      <HStack align="stretch" spacing={4}>
        {steps.map((s, i) => (
          <HStack key={s} spacing={4} flex="1">
            <VStack align="flex-start" spacing={1} flex="1">
              <Box bg={CONCEPTS[s].color} color="white" px={2} py={0.5} borderRadius="sm" fontSize="xs">
                {CONCEPTS[s].label}
              </Box>
              <Text fontSize="xs" color="gray.600">{CONCEPTS[s].gloss}</Text>
            </VStack>
            {i < steps.length - 1 && <MdArrowForward color="#A0AEC0" />}
          </HStack>
        ))}
      </HStack>
    </Box>
  );
}
