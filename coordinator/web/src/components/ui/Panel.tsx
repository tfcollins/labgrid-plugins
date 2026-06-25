import { Box, type BoxProps } from "@chakra-ui/react";

/** Hairline-bordered surface container. Replaces the ad-hoc
 *  `Box bg=card borderRadius shadow` pattern across the app. */
export default function Panel(props: BoxProps) {
  return (
    <Box
      bg="surface.bg"
      borderWidth="1px"
      borderColor="border.hairline"
      borderRadius="lg"
      {...props}
    />
  );
}
