import { useEffect, useRef, useState } from "react";
import { Box, Heading, IconButton, Text, VStack } from "@chakra-ui/react";
import { MdInfoOutline } from "react-icons/md";
import { CONCEPTS, type ConceptName } from "../concepts";

interface ConceptHeadingProps {
  /** Which concept key to teach (headline text is taken from CONCEPTS[name].label + "s"). */
  name: ConceptName;
  /** Stable key for the page — used in the localStorage visit counter. */
  pageKey: string;
  /** Override the rendered heading text (defaults to `${label}s`, e.g. "Places"). */
  headingText?: string;
  /** Chakra heading size. */
  size?: "sm" | "md" | "lg" | "xl";
}

const VISIT_THRESHOLD = 5;
const visitsKey = (pageKey: string) => `concept-visits:${pageKey}`;

/** Shows the heading + gloss for the first VISIT_THRESHOLD mounts of `pageKey`;
 * afterwards renders an info icon that expands the gloss on click. The visit
 * counter increments exactly once per mount (via a ref guard) so strict-mode
 * double-mount in dev doesn't skew it. */
export default function ConceptHeading({
  name,
  pageKey,
  headingText,
  size = "lg",
}: ConceptHeadingProps) {
  const bumpedRef = useRef(false);
  const [visits, setVisits] = useState<number>(() => {
    if (typeof window === "undefined") return 0;
    return parseInt(localStorage.getItem(visitsKey(pageKey)) ?? "0", 10);
  });
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (bumpedRef.current) return;
    bumpedRef.current = true;
    const next = visits + 1;
    localStorage.setItem(visitsKey(pageKey), String(next));
    setVisits(next);
  }, [pageKey, visits]);

  const concept = CONCEPTS[name];
  const showGloss = visits < VISIT_THRESHOLD || expanded;
  const heading = headingText ?? `${concept.label}s`;

  return (
    <VStack align="stretch" spacing={1} mb={4}>
      <Box display="flex" alignItems="center" gap={2}>
        <Heading size={size}>{heading}</Heading>
        {!showGloss && (
          <IconButton
            aria-label={`Show concept gloss for ${concept.label}`}
            size="xs"
            variant="ghost"
            icon={<MdInfoOutline />}
            onClick={() => setExpanded(true)}
          />
        )}
      </Box>
      {showGloss && (
        <Text fontSize="sm" color="gray.500">
          {concept.gloss}
        </Text>
      )}
    </VStack>
  );
}
