import { HStack, Text } from "@chakra-ui/react";
import { type PlaceStatus, STATUS_LABEL, STATUS_TOKEN } from "./status";
import StatusDot from "./StatusDot";

/** Outlined status pill: color lives on the dot + border, label stays in
 *  text.primary for AA legibility in both modes. */
export default function StatusPill({
  status,
  children,
}: {
  status: PlaceStatus;
  children?: React.ReactNode;
}) {
  return (
    <HStack
      as="span"
      display="inline-flex"
      spacing={1.5}
      px={2}
      py={0.5}
      borderWidth="1px"
      borderColor={STATUS_TOKEN[status]}
      borderRadius="sm"
      bg="transparent"
    >
      <StatusDot status={status} size={7} />
      <Text as="span" fontSize="xs" fontWeight="600" color="text.primary" lineHeight="1.2">
        {children ?? STATUS_LABEL[status]}
      </Text>
    </HStack>
  );
}
