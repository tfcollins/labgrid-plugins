import { ReactNode, useEffect } from "react";
import { useLocation } from "react-router-dom";
import {
  Box,
  Drawer,
  DrawerCloseButton,
  DrawerContent,
  DrawerOverlay,
  Flex,
  VStack,
  HStack,
  Text,
  Icon,
  IconButton,
  Spacer,
  Tooltip,
  useColorMode,
  useDisclosure,
  useMediaQuery,
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
  MdSystemUpdateAlt,
  MdHealthAndSafety,
  MdMenu,
  MdMenuOpen,
} from "react-icons/md";
import ChipIcon from "./ChipIcon";
import NavItem from "./ui/NavItem";
import { useSidebarCollapsed } from "../hooks/useSidebarCollapsed";

const SIDEBAR_ID = "app-sidebar";
const SIDEBAR_WIDTH = "240px";
const SIDEBAR_RAIL_WIDTH = "64px";
// Below Chakra's `md` breakpoint (48em) the sidebar leaves the page flow and
// opens as an overlay drawer instead, so it never squeezes the content.
const NARROW_QUERY = "(max-width: 47.99em)";

const navItems = [
  { to: "/", icon: MdDashboard, label: "Dashboard" },
  { to: "/resources", icon: MdStorage, label: "Resources" },
  { to: "/deployments", icon: MdSystemUpdateAlt, label: "Deployments" },
  { to: "/board-health", icon: MdHealthAndSafety, label: "Board Health" },
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
  collapsed: boolean;
}

function ExternalNavItem({ href, icon, label, collapsed }: ExternalNavItemProps) {
  return (
    <Tooltip label={label} placement="right" isDisabled={!collapsed}>
      <Box
        as="a"
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={collapsed ? label : undefined}
        w="full"
        px={collapsed ? 0 : 4}
        py={3}
        borderRadius="md"
        _hover={{ bg: "whiteAlpha.100" }}
        transition="background 0.15s"
      >
        <HStack spacing={3} justify={collapsed ? "center" : "flex-start"}>
          <Icon as={icon} boxSize={5} color="sidebar.text" />
          {!collapsed && (
            <Text color="sidebar.text" fontSize="sm" whiteSpace="nowrap">
              {label}
            </Text>
          )}
        </HStack>
      </Box>
    </Tooltip>
  );
}

/** Logo + nav links, shared by the in-flow sidebar and the narrow-screen drawer. */
function SidebarContent({ collapsed, pathname }: { collapsed: boolean; pathname: string }) {
  return (
    <>
      {/* Logo */}
      <Flex
        direction="column"
        align={collapsed ? "center" : "flex-start"}
        px={collapsed ? 0 : 4}
        mb={8}
        color="sidebar.text"
      >
        <ChipIcon size={36} />
        {!collapsed && (
          <>
            <Text color="white" fontSize="lg" fontWeight="700" mt={2} whiteSpace="nowrap">
              Labgrid
            </Text>
            <Text color="whiteAlpha.700" fontSize="xs" whiteSpace="nowrap">
              Coordinator Dashboard
            </Text>
          </>
        )}
      </Flex>

      {/* Navigation */}
      <VStack spacing={1} align="stretch" flex={1}>
        {navItems.map((item) => (
          <NavItem
            key={item.to}
            {...item}
            isActive={pathname === item.to}
            collapsed={collapsed}
          />
        ))}
      </VStack>

      {/* External links */}
      <VStack spacing={1} align="stretch" mt={2}>
        {externalNavItems.map((item) => (
          <ExternalNavItem key={item.href} {...item} collapsed={collapsed} />
        ))}
      </VStack>
    </>
  );
}

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const location = useLocation();
  const { colorMode, toggleColorMode } = useColorMode();
  const { collapsed, toggle: toggleCollapsed } = useSidebarCollapsed();
  const [isNarrow] = useMediaQuery(NARROW_QUERY, { ssr: false });
  const drawer = useDisclosure();
  const closeDrawer = drawer.onClose;
  const headerBg = "surface.bg";
  const borderColor = "border.hairline";

  // The drawer is transient: dismiss it after navigating or once the viewport
  // is wide enough for the in-flow sidebar to return.
  useEffect(() => {
    closeDrawer();
  }, [location.pathname, isNarrow, closeDrawer]);

  const expanded = isNarrow ? drawer.isOpen : !collapsed;
  const toggleLabel = isNarrow
    ? "Open navigation menu"
    : collapsed
      ? "Expand sidebar"
      : "Collapse sidebar";

  return (
    <Flex h="100vh">
      {/* Sidebar */}
      {!isNarrow && (
        <Box
          as="nav"
          id={SIDEBAR_ID}
          aria-label="Main"
          w={collapsed ? SIDEBAR_RAIL_WIDTH : SIDEBAR_WIDTH}
          bg="sidebar.bg"
          py={6}
          px={3}
          flexShrink={0}
          display="flex"
          flexDirection="column"
          overflowX="hidden"
          overflowY="auto"
          transition="width 0.2s ease"
          sx={{ "@media (prefers-reduced-motion: reduce)": { transition: "none" } }}
        >
          <SidebarContent collapsed={collapsed} pathname={location.pathname} />
        </Box>
      )}

      {/* Sidebar as an overlay drawer on narrow screens */}
      <Drawer isOpen={isNarrow && drawer.isOpen} placement="left" onClose={closeDrawer}>
        <DrawerOverlay />
        <DrawerContent aria-label="Navigation menu" bg="sidebar.bg" maxW={SIDEBAR_WIDTH}>
          <DrawerCloseButton aria-label="Close navigation menu" color="sidebar.text" />
          <Box
            as="nav"
            aria-label="Main"
            h="full"
            py={6}
            px={3}
            display="flex"
            flexDirection="column"
            overflowY="auto"
            onClick={(e: React.MouseEvent<HTMLElement>) => {
              // Also covers re-selecting the current route, which changes no pathname.
              if ((e.target as HTMLElement).closest("a")) closeDrawer();
            }}
          >
            <SidebarContent collapsed={false} pathname={location.pathname} />
          </Box>
        </DrawerContent>
      </Drawer>

      {/* Main content */}
      <Flex flex={1} minW={0} direction="column" overflow="hidden">
        {/* Header */}
        <Flex
          h="56px"
          align="center"
          px={{ base: 4, md: 6 }}
          bg={headerBg}
          borderBottomWidth="1px"
          borderColor={borderColor}
          flexShrink={0}
        >
          <IconButton
            aria-label={toggleLabel}
            aria-expanded={expanded}
            aria-controls={isNarrow ? undefined : SIDEBAR_ID}
            aria-haspopup={isNarrow ? "dialog" : undefined}
            icon={expanded ? <MdMenuOpen /> : <MdMenu />}
            onClick={isNarrow ? drawer.onOpen : toggleCollapsed}
            variant="ghost"
            size="sm"
            fontSize="xl"
            ml={-2}
          />
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
        <Box flex={1} overflow="auto" p={{ base: 4, md: 6 }} bg="page.bg">
          {children}
        </Box>
      </Flex>
    </Flex>
  );
}
