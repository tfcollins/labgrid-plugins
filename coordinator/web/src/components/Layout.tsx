import { ReactNode } from "react";
import { Link as RouterLink, useLocation } from "react-router-dom";
import {
  Box,
  Flex,
  VStack,
  HStack,
  Text,
  Icon,
  IconButton,
  Spacer,
  useColorMode,
  useColorModeValue,
} from "@chakra-ui/react";
import AccountMenu from "./AccountMenu";
import {
  MdDashboard,
  MdPlace,
  MdStorage,
  MdBookmarkBorder,
  MdBarChart,
  MdHistory,
  MdAccountTree,
  MdHelpOutline,
  MdLightMode,
  MdDarkMode,
  MdMovie,
  MdOpenInNew,
} from "react-icons/md";
import ChipIcon from "./ChipIcon";

interface NavItemProps {
  to: string;
  icon: React.ElementType;
  label: string;
  isActive: boolean;
}

function NavItem({ to, icon, label, isActive }: NavItemProps) {
  return (
    <Box
      as={RouterLink}
      to={to}
      w="full"
      px={4}
      py={3}
      borderRadius="md"
      bg={isActive ? "whiteAlpha.200" : "transparent"}
      _hover={{ bg: "whiteAlpha.100" }}
      transition="background 0.15s"
    >
      <HStack spacing={3}>
        <Icon as={icon} boxSize={5} color="sidebar.text" />
        <Text color="sidebar.text" fontSize="sm" fontWeight={isActive ? "600" : "400"}>
          {label}
        </Text>
      </HStack>
    </Box>
  );
}

const navItems = [
  { to: "/", icon: MdDashboard, label: "Dashboard" },
  { to: "/resources", icon: MdStorage, label: "Resources" },
  { to: "/places", icon: MdPlace, label: "Places" },
  { to: "/reservations", icon: MdBookmarkBorder, label: "Reservations" },
  { to: "/topology", icon: MdAccountTree, label: "Topology" },
  { to: "/statistics", icon: MdBarChart, label: "Statistics" },
  { to: "/events", icon: MdHistory, label: "Event Log" },
  { to: "/recordings", icon: MdMovie, label: "Recordings" },
  { to: "/help", icon: MdHelpOutline, label: "Help" },
];

const externalNavItems = [
  {
    href: "https://tfcollins.github.io/labgrid-plugins/",
    icon: MdOpenInNew,
    label: "labgrid-plugins docs",
  },
];

interface ExternalNavItemProps {
  href: string;
  icon: React.ElementType;
  label: string;
}

function ExternalNavItem({ href, icon, label }: ExternalNavItemProps) {
  return (
    <Box
      as="a"
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      w="full"
      px={4}
      py={3}
      borderRadius="md"
      _hover={{ bg: "whiteAlpha.100" }}
      transition="background 0.15s"
    >
      <HStack spacing={3}>
        <Icon as={icon} boxSize={5} color="sidebar.text" />
        <Text color="sidebar.text" fontSize="sm">
          {label}
        </Text>
      </HStack>
    </Box>
  );
}

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const location = useLocation();
  const { colorMode, toggleColorMode } = useColorMode();
  const headerBg = useColorModeValue("white", "gray.800");
  const borderColor = useColorModeValue("gray.200", "gray.700");

  return (
    <Flex h="100vh">
      {/* Sidebar */}
      <Box
        w="240px"
        bg="sidebar.bg"
        py={6}
        px={3}
        flexShrink={0}
        display="flex"
        flexDirection="column"
      >
        {/* Logo */}
        <Box px={4} mb={8}>
          <ChipIcon size={36} />
          <Text color="white" fontSize="lg" fontWeight="700" mt={2}>
            Labgrid
          </Text>
          <Text color="whiteAlpha.700" fontSize="xs">
            Coordinator Dashboard
          </Text>
        </Box>

        {/* Navigation */}
        <VStack spacing={1} align="stretch" flex={1}>
          {navItems.map((item) => (
            <NavItem
              key={item.to}
              {...item}
              isActive={location.pathname === item.to}
            />
          ))}
        </VStack>

        {/* External links */}
        <VStack spacing={1} align="stretch" mt={2}>
          {externalNavItems.map((item) => (
            <ExternalNavItem key={item.href} {...item} />
          ))}
        </VStack>
      </Box>

      {/* Main content */}
      <Flex flex={1} direction="column" overflow="hidden">
        {/* Header */}
        <Flex
          h="56px"
          align="center"
          px={6}
          bg={headerBg}
          borderBottomWidth="1px"
          borderColor={borderColor}
          flexShrink={0}
        >
          <Spacer />
          <HStack spacing={2}>
            <IconButton
              aria-label="Toggle color mode"
              icon={colorMode === "light" ? <MdDarkMode /> : <MdLightMode />}
              onClick={toggleColorMode}
              variant="ghost"
              size="sm"
            />
            <AccountMenu />
          </HStack>
        </Flex>

        {/* Page content */}
        <Box flex={1} overflow="auto" p={6} bg={useColorModeValue("gray.50", "gray.900")}>
          {children}
        </Box>
      </Flex>
    </Flex>
  );
}
