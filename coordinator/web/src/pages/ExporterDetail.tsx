import { useState, useMemo } from "react";
import { useParams, Link as RouterLink } from "react-router-dom";
import { Link as RLink } from "react-router-dom";
import {
  Box,
  Heading,
  Text,
  HStack,
  Badge,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Spinner,
  Button,
  IconButton,
  VStack,
  Code,
  Flex,
  Stack,
} from "@chakra-ui/react";
import Panel from "../components/ui/Panel";
import { MdArrowBack, MdExpandMore, MdExpandLess } from "react-icons/md";
import { useExporters } from "../hooks/useResources";
import { useWebSocket } from "../api/ws";
import ExporterStatusBadge from "../components/ExporterStatusBadge";
import RelatedPanel from "../components/RelatedPanel";
import { useRelationships } from "../hooks/useRelationships";

export default function ExporterDetail() {
  useWebSocket();

  const { exporterName } = useParams<{ exporterName: string }>();
  const { data: exporters, isLoading } = useExporters();
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const { exporterToPlaces, resourceToPlaces } = useRelationships();

  if (isLoading) return <Spinner size="xl" color="adi.500" />;

  const exporter = exporters?.find((e) => e.name === exporterName);

  if (!exporter) {
    return (
      <Box>
        <Button
          as={RouterLink}
          to="/"
          leftIcon={<MdArrowBack />}
          variant="ghost"
          size="sm"
          mb={4}
        >
          Back to Dashboard
        </Button>
        <Heading size="lg" color="text.primary">
          Exporter not found
        </Heading>
        <Text color="text.secondary" mt={2}>
          No exporter named "{exporterName}" is currently connected.
        </Text>
      </Box>
    );
  }

  const allResources = Object.values(exporter.groups).flat();

  const placesHere = exporterToPlaces.get(exporterName!) ?? [];

  // "Orphan resources" = live resources on this exporter that no place matches.
  const orphanResources = useMemo(() => {
    if (!exporter) return [];
    const orphans: { group: string; cls: string; name: string }[] = [];
    for (const [group, list] of Object.entries(exporter.groups)) {
      for (const r of list) {
        if (!r.avail) continue;
        const key = `${exporterName}/${group}/${r.cls}/${r.name}`;
        if ((resourceToPlaces.get(key) ?? []).length === 0) {
          orphans.push({ group, cls: r.cls, name: r.name });
        }
      }
    }
    return orphans;
  }, [exporter, exporterName, resourceToPlaces]);

  return (
    <Flex gap={6} align="flex-start" direction={{ base: "column", md: "row" }}>
      <Box flex="1" minW={0}>
      <Button
        as={RouterLink}
        to="/"
        leftIcon={<MdArrowBack />}
        variant="ghost"
        size="sm"
        mb={4}
      >
        Back to Dashboard
      </Button>

      <HStack mb={6} spacing={4}>
        <Heading size="lg" color="text.primary">
          {exporter.name}
        </Heading>
        <ExporterStatusBadge resources={allResources} />
      </HStack>

      <Text fontSize="sm" color="text.secondary" mb={6}>
        {Object.keys(exporter.groups).length} group
        {Object.keys(exporter.groups).length !== 1 ? "s" : ""},{" "}
        {allResources.length} resource
        {allResources.length !== 1 ? "s" : ""}
      </Text>

      {Object.entries(exporter.groups).map(([groupName, resources]) => (
        <Box key={groupName} mb={8}>
          <Heading size="sm" mb={3} color="text.primary">
            {groupName}
          </Heading>

          <Panel overflow="hidden">
            <Table variant="simple" size="sm">
              <Thead>
                <Tr>
                  <Th w="30px"></Th>
                  <Th>Name</Th>
                  <Th>Class</Th>
                  <Th>Available</Th>
                  <Th>Acquired By</Th>
                </Tr>
              </Thead>
              <Tbody>
                {resources.map((res) => {
                  const rowKey = `${groupName}/${res.name}`;
                  const isExpanded = expandedRow === rowKey;
                  const paramEntries = Object.entries(res.params).filter(
                    ([k]) =>
                      k !== "extra" &&
                      !k.toLowerCase().includes("password")
                  );

                  return (
                    <>
                      <Tr
                        key={rowKey}
                        cursor={paramEntries.length > 0 ? "pointer" : undefined}
                        _hover={
                          paramEntries.length > 0
                            ? { bg: "surface.subtle" }
                            : undefined
                        }
                        onClick={() =>
                          paramEntries.length > 0 &&
                          setExpandedRow(isExpanded ? null : rowKey)
                        }
                      >
                        <Td>
                          {paramEntries.length > 0 && (
                            <IconButton
                              aria-label="Expand"
                              icon={
                                isExpanded ? (
                                  <MdExpandLess />
                                ) : (
                                  <MdExpandMore />
                                )
                              }
                              size="xs"
                              variant="ghost"
                            />
                          )}
                        </Td>
                        <Td fontWeight="500">{res.name}</Td>
                        <Td>
                          <Badge colorScheme="adi" variant="subtle">
                            {res.cls}
                          </Badge>
                        </Td>
                        <Td>
                          <Badge colorScheme={res.avail ? "green" : "red"}>
                            {res.avail ? "Yes" : "No"}
                          </Badge>
                        </Td>
                        <Td>
                          {res.acquired ? (
                            <Badge colorScheme="orange">{res.acquired}</Badge>
                          ) : (
                            <Text
                              fontSize="sm"
                              color="text.secondary"
                              as="span"
                            >
                              —
                            </Text>
                          )}
                        </Td>
                      </Tr>
                      {isExpanded && (
                        <Tr key={`${rowKey}-params`}>
                          <Td
                            colSpan={5}
                            bg="surface.subtle"
                            p={4}
                          >
                            <Text
                              fontSize="xs"
                              fontWeight="600"
                              color="text.secondary"
                              mb={2}
                            >
                              Parameters
                            </Text>
                            <VStack align="stretch" spacing={1}>
                              {paramEntries.map(([key, value]) => (
                                <HStack key={key} fontSize="sm">
                                  <Code fontSize="xs" colorScheme="adi">
                                    {key}
                                  </Code>
                                  <Text fontSize="sm">
                                    {typeof value === "object"
                                      ? JSON.stringify(value)
                                      : String(value)}
                                  </Text>
                                </HStack>
                              ))}
                            </VStack>
                          </Td>
                        </Tr>
                      )}
                    </>
                  );
                })}
              </Tbody>
            </Table>
          </Panel>
        </Box>
      ))}
      </Box>

      {/* ===== Related sidebar ===== */}
      <RelatedPanel>
        <RelatedPanel.Section title="Places using this exporter">
          {placesHere.length === 0 ? (
            <Text color="text.secondary">No places reference this exporter yet.</Text>
          ) : (
            <Stack spacing={1}>
              {placesHere.map((p) => (
                <HStack key={p.name}>
                  <RLink to={`/places/${encodeURIComponent(p.name)}`}>
                    <Text color="link">{p.name}</Text>
                  </RLink>
                  {p.acquired && (
                    <Text fontSize="xs" color="orange.500">(held by {p.acquired})</Text>
                  )}
                </HStack>
              ))}
            </Stack>
          )}
        </RelatedPanel.Section>

        <RelatedPanel.Section title="Orphan resources">
          {orphanResources.length === 0 ? (
            <Text color="text.secondary">None — every live resource is matched.</Text>
          ) : (
            <Stack spacing={1}>
              {orphanResources.map((r) => (
                <Text key={`${r.group}/${r.cls}/${r.name}`} fontFamily="mono" fontSize="xs">
                  {r.group}/{r.cls}/{r.name}
                </Text>
              ))}
              <Text color="text.secondary" fontSize="xs">
                Published here but no place matches. Add a match to a place, or create one.
              </Text>
            </Stack>
          )}
        </RelatedPanel.Section>

        <RelatedPanel.Footer to={`/topology?focus=exporter:${encodeURIComponent(exporterName!)}`}>
          Show in Topology →
        </RelatedPanel.Footer>
      </RelatedPanel>
    </Flex>
  );
}
