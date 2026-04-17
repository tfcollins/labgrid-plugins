import { useState, useMemo } from "react";
import {
  Box,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Badge,
  HStack,
  Select,
  Switch,
  FormControl,
  FormLabel,
  Spinner,
  Text,
  Tag,
  TagLabel,
  useColorModeValue,
} from "@chakra-ui/react";
import { Link as RouterLink } from "react-router-dom";
import { useResources } from "../hooks/useResources";
import { useWebSocket } from "../api/ws";
import ConceptHeading from "../components/ConceptHeading";
import { useRelationships } from "../hooks/useRelationships";

export default function Resources() {
  useWebSocket();

  const { data: resources, isLoading } = useResources();
  const { resourceToPlaces } = useRelationships();
  const [exporterFilter, setExporterFilter] = useState("");
  const [clsFilter, setClsFilter] = useState("");
  const [showOnlyAvail, setShowOnlyAvail] = useState(false);
  const tableBg = useColorModeValue("white", "gray.800");

  const exporters = useMemo(() => {
    if (!resources) return [];
    return [...new Set(resources.map((r) => r.exporter))].sort();
  }, [resources]);

  const classes = useMemo(() => {
    if (!resources) return [];
    return [...new Set(resources.map((r) => r.cls))].sort();
  }, [resources]);

  const filtered = useMemo(() => {
    if (!resources) return [];
    return resources.filter((r) => {
      if (exporterFilter && r.exporter !== exporterFilter) return false;
      if (clsFilter && r.cls !== clsFilter) return false;
      if (showOnlyAvail && !r.avail) return false;
      return true;
    });
  }, [resources, exporterFilter, clsFilter, showOnlyAvail]);

  if (isLoading) return <Spinner size="xl" color="adi.500" />;

  return (
    <Box>
      <ConceptHeading name="resource" pageKey="/resources" />

      {/* Filters */}
      <HStack spacing={4} mb={4} flexWrap="wrap">
        <Select
          placeholder="All exporters"
          value={exporterFilter}
          onChange={(e) => setExporterFilter(e.target.value)}
          maxW="200px"
          size="sm"
          bg={tableBg}
        >
          {exporters.map((e) => (
            <option key={e} value={e}>
              {e}
            </option>
          ))}
        </Select>
        <Select
          placeholder="All classes"
          value={clsFilter}
          onChange={(e) => setClsFilter(e.target.value)}
          maxW="200px"
          size="sm"
          bg={tableBg}
        >
          {classes.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </Select>
        <FormControl display="flex" alignItems="center" w="auto">
          <FormLabel htmlFor="avail-toggle" mb="0" fontSize="sm">
            Available only
          </FormLabel>
          <Switch
            id="avail-toggle"
            colorScheme="adi"
            isChecked={showOnlyAvail}
            onChange={(e) => setShowOnlyAvail(e.target.checked)}
          />
        </FormControl>
        <Text fontSize="sm" color="text.secondary">
          {filtered.length} of {resources?.length ?? 0} resources
        </Text>
      </HStack>

      <Box bg={tableBg} borderRadius="lg" overflow="hidden" shadow="sm">
        <Table variant="simple" size="sm">
          <Thead>
            <Tr>
              <Th>Exporter</Th>
              <Th>Group</Th>
              <Th>Class</Th>
              <Th>Name</Th>
              <Th>Available</Th>
              <Th>Acquired By</Th>
              <Th>Matched by</Th>
            </Tr>
          </Thead>
          <Tbody>
            {filtered.map((r, i) => (
              <Tr key={`${r.exporter}-${r.group}-${r.name}-${i}`}>
                <Td>{r.exporter}</Td>
                <Td>{r.group}</Td>
                <Td>
                  <Badge colorScheme="adi" variant="subtle">
                    {r.cls}
                  </Badge>
                </Td>
                <Td>{r.name}</Td>
                <Td>
                  <Badge colorScheme={r.avail ? "green" : "red"}>
                    {r.avail ? "Yes" : "No"}
                  </Badge>
                </Td>
                <Td>
                  {r.acquired ? (
                    <Badge colorScheme="orange">{r.acquired}</Badge>
                  ) : (
                    <Text fontSize="sm" color="text.secondary">
                      -
                    </Text>
                  )}
                </Td>
                <Td>
                  {(() => {
                    const key = `${r.exporter}/${r.group}/${r.cls}/${r.name}`;
                    const places = resourceToPlaces.get(key) ?? [];
                    if (places.length === 0) {
                      return <Text fontSize="xs" color="gray.400">—</Text>;
                    }
                    return (
                      <HStack spacing={1} flexWrap="wrap">
                        {places.map((p) => (
                          <Tag
                            key={p.name} size="sm" variant="subtle"
                            colorScheme={p.acquired ? "orange" : "green"}
                            as={RouterLink} to={`/places/${encodeURIComponent(p.name)}`}
                            cursor="pointer"
                          >
                            <TagLabel>{p.name}</TagLabel>
                          </Tag>
                        ))}
                      </HStack>
                    );
                  })()}
                </Td>
              </Tr>
            ))}
            {filtered.length === 0 && (
              <Tr>
                <Td colSpan={7} textAlign="center" color="text.secondary" py={8}>
                  {resources?.length === 0
                    ? "No resources available. Connect an exporter."
                    : "No resources match the current filters."}
                </Td>
              </Tr>
            )}
          </Tbody>
        </Table>
      </Box>
    </Box>
  );
}
