import { Text, type TextProps, Heading, type HeadingProps } from "@chakra-ui/react";

/** Tiny uppercase tracked label (instrument micro-label). */
export function MicroLabel({ children, ...rest }: TextProps) {
  return (
    <Text
      fontSize="11px"
      fontWeight="600"
      textTransform="uppercase"
      letterSpacing="0.14em"
      color="text.secondary"
      {...rest}
    >
      {children}
    </Text>
  );
}

/** Section heading in the tracked instrument style. */
export function SectionLabel({ children, ...rest }: HeadingProps) {
  return (
    <Heading size="sm" color="text.primary" letterSpacing="-0.01em" {...rest}>
      {children}
    </Heading>
  );
}
