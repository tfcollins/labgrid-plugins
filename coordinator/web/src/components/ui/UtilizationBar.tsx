import { Box, Flex } from "@chakra-ui/react";

/** Thin segmented proportion bar built from real instantaneous counts.
 *  Conveys the bench-instrument feel without any time-series data. */
export default function UtilizationBar({
  free,
  acquired,
  offline,
}: {
  free: number;
  acquired: number;
  offline: number;
}) {
  const total = free + acquired + offline;
  const segs = [
    { key: "free", value: free, token: "status.free" },
    { key: "acquired", value: acquired, token: "status.acquired" },
    { key: "offline", value: offline, token: "status.offline" },
  ];
  return (
    <Flex
      role="img"
      aria-label={`${total} places: ${free} free, ${acquired} acquired, ${offline} offline`}
      h="6px"
      borderRadius="full"
      overflow="hidden"
      bg="surface.subtle"
      w="full"
    >
      {segs.map((s) => (
        <Box
          key={s.key}
          data-seg={s.key}
          bg={s.token}
          w={total === 0 ? "0%" : `${(s.value / total) * 100}%`}
        />
      ))}
    </Flex>
  );
}
