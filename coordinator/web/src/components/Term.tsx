import { useState, useCallback } from "react";
import { Box, Tooltip } from "@chakra-ui/react";
import { CONCEPTS, type ConceptName } from "../concepts";

interface TermProps {
  name: ConceptName;
  children: React.ReactNode;
}

const storageKey = (name: ConceptName) => `concept-term-seen:${name}`;

/** Inline vocabulary teaching. First render shows a dotted-underline with a
 * one-sentence tooltip; after the user hovers or focuses it once, the
 * localStorage flag suppresses the underline on every future render of that
 * term (user is considered to have "learned" it). */
export default function Term({ name, children }: TermProps) {
  const [seen, setSeen] = useState(
    () => typeof window !== "undefined" && !!localStorage.getItem(storageKey(name))
  );

  const markSeen = useCallback(() => {
    if (!seen) {
      localStorage.setItem(storageKey(name), "1");
      setSeen(true);
    }
  }, [name, seen]);

  const gloss = CONCEPTS[name].gloss;

  const underlineStyle = seen
    ? {}
    : {
        textDecorationLine: "underline",
        textDecorationStyle: "dotted" as const,
        textDecorationColor: "var(--chakra-colors-gray-400)",
        textUnderlineOffset: "3px",
        cursor: "help",
      };

  return (
    <Tooltip label={gloss} placement="top" hasArrow openDelay={150}>
      <Box
        as="span"
        style={underlineStyle}
        onMouseEnter={markSeen}
        onFocus={markSeen}
        // Remove from tab order after first interaction — once the user has
        // "learned" the term, we don't keep pulling keyboard focus back to it
        // on every page. Escape hatch: Help page has a "Reset concept tooltips"
        // button that re-enables underlines (and thus tabIndex=0) for everyone.
        tabIndex={seen ? -1 : 0}
      >
        {children}
      </Box>
    </Tooltip>
  );
}

/** Clear every `concept-term-seen:*` localStorage key. Called from the Help
 * page and the ConceptHeading info-icon reset action. */
export function resetTermsSeen() {
  if (typeof window === "undefined") return;
  for (let i = localStorage.length - 1; i >= 0; i--) {
    const k = localStorage.key(i);
    if (k && k.startsWith("concept-term-seen:")) {
      localStorage.removeItem(k);
    }
  }
}
