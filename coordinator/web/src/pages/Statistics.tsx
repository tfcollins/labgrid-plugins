import {
  Box,
  SimpleGrid,
  Stat,
  StatLabel,
  StatNumber,
  Card,
  CardBody,
  Heading,
  Text,
  Spinner,
  useColorModeValue,
  Tabs,
  TabList,
  TabPanels,
  Tab,
  TabPanel,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Select,
  HStack,
} from "@chakra-ui/react";
import { useState } from "react";
import {
  useStatsOverview,
  usePlaceStats,
  useResourceStats,
  useExporterStats,
} from "../hooks/useStats";

function StatCard({ label, value }: { label: string; value: number | string }) {
  const bg = useColorModeValue("white", "gray.800");
  return (
    <Card bg={bg}>
      <CardBody>
        <Stat>
          <StatLabel color="text.secondary">{label}</StatLabel>
          <StatNumber color="accent.text">{value}</StatNumber>
        </Stat>
      </CardBody>
    </Card>
  );
}

function BarCell({ percent }: { percent: number }) {
  const barBg = useColorModeValue("gray.100", "gray.700");
  const barColor =
    percent > 75 ? "green.400" : percent > 40 ? "yellow.400" : "red.400";
  return (
    <HStack spacing={2} minW="140px">
      <Box flex="1" h="8px" bg={barBg} borderRadius="full" overflow="hidden">
        <Box
          h="100%"
          w={`${Math.min(percent, 100)}%`}
          bg={barColor}
          borderRadius="full"
        />
      </Box>
      <Text fontSize="sm" minW="45px" textAlign="right">
        {percent.toFixed(1)}%
      </Text>
    </HStack>
  );
}

function OverviewTab() {
  const { data: overview, isLoading: overviewLoading } = useStatsOverview();
  const { data: exporters, isLoading: exportersLoading } =
    useExporterStats(30);
  const cardBg = useColorModeValue("white", "gray.800");

  if (overviewLoading || exportersLoading) {
    return <Spinner size="xl" color="adi.500" />;
  }

  return (
    <Box>
      <SimpleGrid columns={{ base: 1, md: 2, lg: 3 }} spacing={4} mb={8}>
        <StatCard
          label="Events (24h)"
          value={overview?.total_events_24h ?? 0}
        />
        <StatCard
          label="Avg Acquisition Duration"
          value={
            overview?.avg_acquisition_duration_hours != null
              ? `${overview.avg_acquisition_duration_hours.toFixed(1)}h`
              : "N/A"
          }
        />
        <StatCard
          label="Busiest Hour"
          value={
            overview?.busiest_hour != null
              ? `${overview.busiest_hour}:00`
              : "N/A"
          }
        />
        <StatCard
          label="Most Used Place"
          value={overview?.most_used_place ?? "N/A"}
        />
        <StatCard
          label="Avg Uptime"
          value={
            overview?.avg_uptime_percent != null
              ? `${overview.avg_uptime_percent.toFixed(1)}%`
              : "N/A"
          }
        />
      </SimpleGrid>

      <Heading size="md" mb={4} color="text.primary">
        Exporter Availability
      </Heading>
      {exporters && exporters.length > 0 ? (
        <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
          {exporters.map((exp) => (
            <Card key={exp.exporter} bg={cardBg}>
              <CardBody>
                <HStack justify="space-between" mb={2}>
                  <Text fontWeight="600">{exp.exporter}</Text>
                  <Text fontSize="sm" color="text.secondary">
                    {exp.resource_count} resource
                    {exp.resource_count !== 1 ? "s" : ""}
                  </Text>
                </HStack>
                <BarCell percent={exp.avg_uptime_percent} />
              </CardBody>
            </Card>
          ))}
        </SimpleGrid>
      ) : (
        <Text color="text.secondary">No exporter statistics available.</Text>
      )}
    </Box>
  );
}

function PlacesTab({ days }: { days: number }) {
  const { data: places, isLoading } = usePlaceStats(days);

  if (isLoading) {
    return <Spinner size="xl" color="adi.500" />;
  }

  if (!places || places.length === 0) {
    return <Text color="text.secondary">No place statistics available.</Text>;
  }

  return (
    <Box overflowX="auto">
      <Table variant="simple" size="sm">
        <Thead>
          <Tr>
            <Th>Place</Th>
            <Th isNumeric>Sessions</Th>
            <Th>Utilization</Th>
            <Th>Last Acquired By</Th>
          </Tr>
        </Thead>
        <Tbody>
          {places.map((p) => (
            <Tr key={p.place_name}>
              <Td fontWeight="500">{p.place_name}</Td>
              <Td isNumeric>{p.total_sessions}</Td>
              <Td>
                <BarCell percent={p.utilization_percent} />
              </Td>
              <Td>{p.last_acquired_by ?? "-"}</Td>
            </Tr>
          ))}
        </Tbody>
      </Table>
    </Box>
  );
}

function ResourcesTab({ days }: { days: number }) {
  const { data: resources, isLoading } = useResourceStats(days);

  if (isLoading) {
    return <Spinner size="xl" color="adi.500" />;
  }

  if (!resources || resources.length === 0) {
    return (
      <Text color="text.secondary">No resource statistics available.</Text>
    );
  }

  return (
    <Box overflowX="auto">
      <Table variant="simple" size="sm">
        <Thead>
          <Tr>
            <Th>Resource</Th>
            <Th>Uptime</Th>
            <Th isNumeric>Online (h)</Th>
            <Th isNumeric>Offline (h)</Th>
          </Tr>
        </Thead>
        <Tbody>
          {resources.map((r) => (
            <Tr key={r.resource_key}>
              <Td fontWeight="500">{r.resource_key}</Td>
              <Td>
                <BarCell percent={r.uptime_percent} />
              </Td>
              <Td isNumeric>
                {(r.total_online_seconds / 3600).toFixed(1)}
              </Td>
              <Td isNumeric>
                {(r.total_offline_seconds / 3600).toFixed(1)}
              </Td>
            </Tr>
          ))}
        </Tbody>
      </Table>
    </Box>
  );
}

export default function Statistics() {
  const [days, setDays] = useState(30);

  return (
    <Box>
      <HStack justify="space-between" mb={6}>
        <Heading size="lg" color="text.primary">
          Statistics
        </Heading>
        <Select
          w="140px"
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
        >
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </Select>
      </HStack>

      <Tabs colorScheme="adi" variant="enclosed">
        <TabList>
          <Tab>Overview</Tab>
          <Tab>Places</Tab>
          <Tab>Resources</Tab>
        </TabList>
        <TabPanels>
          <TabPanel px={0}>
            <OverviewTab />
          </TabPanel>
          <TabPanel px={0}>
            <PlacesTab days={days} />
          </TabPanel>
          <TabPanel px={0}>
            <ResourcesTab days={days} />
          </TabPanel>
        </TabPanels>
      </Tabs>
    </Box>
  );
}
