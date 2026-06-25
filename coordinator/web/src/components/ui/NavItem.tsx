import { Link as RouterLink } from "react-router-dom";
import { Box, HStack, Icon, Text } from "@chakra-ui/react";

/** Sidebar nav row with a lit channel-indicator bar + aria-current on the
 *  active route. */
export default function NavItem({
  to,
  icon,
  label,
  isActive,
}: {
  to: string;
  icon: React.ElementType;
  label: string;
  isActive: boolean;
}) {
  return (
    <Box
      as={RouterLink}
      to={to}
      aria-current={isActive ? "page" : undefined}
      position="relative"
      w="full"
      px={4}
      py={3}
      borderRadius="md"
      bg={isActive ? "whiteAlpha.200" : "transparent"}
      _hover={{ bg: "sidebar.hover" }}
      transition="background 0.15s"
    >
      {isActive && (
        <Box
          position="absolute"
          left="0"
          top="20%"
          bottom="20%"
          w="3px"
          borderRadius="full"
          bg="accent"
        />
      )}
      <HStack spacing={3}>
        <Icon as={icon} boxSize={5} color="sidebar.text" />
        <Text color="sidebar.text" fontSize="sm" fontWeight={isActive ? "600" : "400"}>
          {label}
        </Text>
      </HStack>
    </Box>
  );
}
