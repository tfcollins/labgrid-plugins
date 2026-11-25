import { Link as RouterLink } from "react-router-dom";
import { Box, HStack, Icon, Text, Tooltip } from "@chakra-ui/react";

/** Sidebar nav row with a lit channel-indicator bar + aria-current on the
 *  active route. When `collapsed`, only the icon is shown; the label moves to
 *  the accessible name and a tooltip. */
export default function NavItem({
  to,
  icon,
  label,
  isActive,
  collapsed = false,
}: {
  to: string;
  icon: React.ElementType;
  label: string;
  isActive: boolean;
  collapsed?: boolean;
}) {
  return (
    <Tooltip label={label} placement="right" isDisabled={!collapsed}>
      <Box
        as={RouterLink}
        to={to}
        aria-current={isActive ? "page" : undefined}
        aria-label={collapsed ? label : undefined}
        position="relative"
        w="full"
        px={collapsed ? 0 : 4}
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
        <HStack spacing={3} justify={collapsed ? "center" : "flex-start"}>
          <Icon as={icon} boxSize={5} color="sidebar.text" />
          {!collapsed && (
            <Text
              color="sidebar.text"
              fontSize="sm"
              fontWeight={isActive ? "600" : "400"}
              whiteSpace="nowrap"
            >
              {label}
            </Text>
          )}
        </HStack>
      </Box>
    </Tooltip>
  );
}
