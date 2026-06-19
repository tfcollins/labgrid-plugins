import { useMemo, useState } from "react";
import React from "react";
import {
  Box,
  Table,
  Thead,
  Tbody,
  Tfoot,
  Tr,
  Th,
  Td,
  Button,
  Heading,
  HStack,
  Tag,
  TagLabel,
  Spinner,
  Text,
  IconButton,
  VStack,
  useToast,
} from "@chakra-ui/react";
import { MdExpandMore, MdExpandLess, MdDelete } from "react-icons/md";
import { Link as RouterLink, useNavigate } from "react-router-dom";
import type { Place } from "../api/client";
import { usePlaces, useDeletePlace, useAcquirePlace, useReleasePlace } from "../hooks/usePlaces";
import { useWebSocket } from "../api/ws";
import ConceptHeading from "../components/ConceptHeading";
import { useRelationships } from "../hooks/useRelationships";
import type { ExporterSummary, PlaceHealth } from "../hooks/useRelationships";
import StatusPill from "../components/ui/StatusPill";
import Panel from "../components/ui/Panel";

function renderHealthBadge(health: PlaceHealth | undefined, missingCount: number): React.ReactNode {
  if (health === "held") return <StatusPill status="acquired">held</StatusPill>;
  if (health === "degraded") return <StatusPill status="degraded">{missingCount} not live</StatusPill>;
  if (health === "ready") return <StatusPill status="free">ready</StatusPill>;
  return <Text as="span" color="text.secondary">—</Text>;
}

interface PlacesTableProps {
  places: Place[];
  placeToExporters: Map<string, ExporterSummary[]>;
  placeToMissingMatches: Map<string, import("../api/client").ResourceMatch[]>;
  placeHealth: Map<string, PlaceHealth>;
  expandedPlace: string | null;
  onToggleExpand: (name: string) => void;
  onToggleAcquire: (name: string, isAcquired: boolean) => void;
  onDelete: (name: string) => void;
  emptyMessage: string;
  density: "comfortable" | "compact";
}

function PlacesTable({
  places,
  placeToExporters,
  placeToMissingMatches,
  placeHealth,
  expandedPlace,
  onToggleExpand,
  onToggleAcquire,
  onDelete,
  emptyMessage,
  density,
}: PlacesTableProps) {
  return (
    <Panel overflow="hidden">
      <Table variant="simple" size="sm">
        <Thead>
          <Tr>
            <Th w="30px"></Th>
            <Th>Name</Th>
            <Th>Tags</Th>
            <Th>Health</Th>
            <Th>Hosted by</Th>
            <Th>Acquired By</Th>
            <Th>Actions</Th>
          </Tr>
        </Thead>
        <Tbody>
          {places.map((place) => {
            const isExpanded = expandedPlace === place.name;
            return (
              <React.Fragment key={place.name}>
                <Tr cursor="pointer" _hover={{ bg: "surface.subtle" }}>
                  <Td>
                    <IconButton
                      aria-label="Expand"
                      icon={isExpanded ? <MdExpandLess /> : <MdExpandMore />}
                      size="xs"
                      variant="ghost"
                      onClick={() => onToggleExpand(place.name)}
                    />
                  </Td>
                  <Td>
                    <RouterLink to={`/places/${encodeURIComponent(place.name)}`}>
                      <Text color="link" fontWeight="500">{place.name}</Text>
                    </RouterLink>
                    {density === "compact" && (
                      <Text fontSize="xs" color="text.secondary" fontFamily="mono">
                        {Object.entries(place.tags).map(([k, v]) => `${k}=${v}`).join(" · ") || "—"}
                      </Text>
                    )}
                  </Td>
                  <Td>
                    <HStack spacing={1} flexWrap="wrap">
                      {Object.entries(place.tags).map(([k, v]) => (
                        <Tag key={k} size="sm" colorScheme="adi" variant="subtle">
                          <TagLabel>{k}={v}</TagLabel>
                        </Tag>
                      ))}
                    </HStack>
                  </Td>
                  <Td>{renderHealthBadge(placeHealth.get(place.name), placeToMissingMatches.get(place.name)?.length ?? 0)}</Td>
                  <Td>
                    <HStack spacing={1} flexWrap="wrap">
                      {(placeToExporters.get(place.name) ?? []).map((e) => (
                        <Tag
                          key={e.name} size="sm" variant="subtle"
                          colorScheme={e.online ? "adi" : "gray"}
                          as={RouterLink} to={`/exporters/${encodeURIComponent(e.name)}`}
                          cursor="pointer"
                        >
                          <TagLabel>{e.name}</TagLabel>
                        </Tag>
                      ))}
                      {(placeToExporters.get(place.name) ?? []).length === 0 && (
                        <Text fontSize="xs" color="text.secondary">—</Text>
                      )}
                    </HStack>
                  </Td>
                  <Td>
                    {place.acquired ? (
                      <StatusPill status="acquired">{place.acquired}</StatusPill>
                    ) : (
                      <Text fontSize="sm" color="text.secondary">-</Text>
                    )}
                  </Td>
                  <Td>
                    <HStack spacing={2}>
                      <Button
                        size="xs"
                        colorScheme={place.acquired ? "orange" : "green"}
                        variant="outline"
                        onClick={() => onToggleAcquire(place.name, !!place.acquired)}
                      >
                        {place.acquired ? "Release" : "Acquire"}
                      </Button>
                      <IconButton
                        aria-label="Delete"
                        icon={<MdDelete />}
                        size="xs"
                        colorScheme="red"
                        variant="ghost"
                        onClick={() => onDelete(place.name)}
                      />
                    </HStack>
                  </Td>
                </Tr>
                {isExpanded && (
                  <Tr>
                    <Td colSpan={7} bg="surface.subtle" p={4}>
                      <VStack align="stretch" spacing={3}>
                        {place.comment && (
                          <Box>
                            <Text fontSize="xs" fontWeight="600" color="text.secondary">Comment</Text>
                            <Text fontSize="sm">{place.comment}</Text>
                          </Box>
                        )}
                        {place.aliases.length > 0 && (
                          <Box>
                            <Text fontSize="xs" fontWeight="600" color="text.secondary">Aliases</Text>
                            <Text fontSize="sm">{place.aliases.join(", ")}</Text>
                          </Box>
                        )}
                        <Box>
                          <Text fontSize="xs" fontWeight="600" color="text.secondary">Matches</Text>
                          {place.matches.map((m, i) => (
                            <Text key={i} fontSize="sm" fontFamily="mono">
                              {m.exporter}/{m.group}/{m.cls}
                              {m.name ? `/${m.name}` : ""}
                              {m.rename ? ` -> ${m.rename}` : ""}
                            </Text>
                          ))}
                          {place.matches.length === 0 && (
                            <Text fontSize="sm" color="text.secondary">No matches</Text>
                          )}
                        </Box>
                        {place.acquired_resources.length > 0 && (
                          <Box>
                            <Text fontSize="xs" fontWeight="600" color="text.secondary">Acquired Resources</Text>
                            {place.acquired_resources.map((r, i) => (
                              <Text key={i} fontSize="sm" fontFamily="mono">
                                {r.join("/")}
                              </Text>
                            ))}
                          </Box>
                        )}
                      </VStack>
                    </Td>
                  </Tr>
                )}
              </React.Fragment>
            );
          })}
          {places.length === 0 && (
            <Tr>
              <Td colSpan={7} textAlign="center" color="text.secondary" py={8}>
                {emptyMessage}
              </Td>
            </Tr>
          )}
        </Tbody>
        <Tfoot>
          <Tr>
            <Td colSpan={7} color="text.secondary" fontSize="xs">
              {places.length} of {places.length} ·{" "}
              {places.filter((p) => !p.acquired).length} free ·{" "}
              {places.filter((p) => p.acquired).length} acquired
            </Td>
          </Tr>
        </Tfoot>
      </Table>
    </Panel>
  );
}

export default function Places() {
  useWebSocket();

  const { data: places, isLoading } = usePlaces();
  const deletePlace = useDeletePlace();
  const acquirePlace = useAcquirePlace();
  const releasePlace = useReleasePlace();
  const [expandedPlace, setExpandedPlace] = useState<string | null>(null);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const { placeToExporters, placeToMissingMatches, placeHealth } = useRelationships();
  const toast = useToast();
  const nav = useNavigate();
  const [density, setDensity] = useState<"comfortable" | "compact">(
    () => (localStorage.getItem("places-density") as "comfortable" | "compact") || "comfortable",
  );
  const toggleDensity = () => {
    setDensity((d) => {
      const next = d === "comfortable" ? "compact" : "comfortable";
      localStorage.setItem("places-density", next);
      return next;
    });
  };

  const { livePlaces, offlinePlaces } = useMemo(() => {
    const live: Place[] = [];
    const offline: Place[] = [];
    for (const p of places ?? []) {
      const contributing = placeToExporters.get(p.name) ?? [];
      if (contributing.length === 0) offline.push(p);
      else live.push(p);
    }
    return { livePlaces: live, offlinePlaces: offline };
  }, [places, placeToExporters]);

  const handleToggleAcquire = async (name: string, isAcquired: boolean) => {
    try {
      if (isAcquired) {
        await releasePlace.mutateAsync(name);
      } else {
        await acquirePlace.mutateAsync(name);
      }
    } catch (e) {
      toast({ title: "Operation failed", status: "error", duration: 3000 });
    }
  };

  const handleToggleExpand = (name: string) => {
    setExpandedPlace((cur) => (cur === name ? null : name));
  };

  const handleDeleteAllOffline = async () => {
    if (offlinePlaces.length === 0) return;
    const confirmed = window.confirm(
      `Delete ${offlinePlaces.length} offline place${offlinePlaces.length === 1 ? "" : "s"}? ` +
        `This removes them from the coordinator. It cannot be undone.`,
    );
    if (!confirmed) return;

    setBulkDeleting(true);
    let deleted = 0;
    const failed: string[] = [];
    for (const p of offlinePlaces) {
      try {
        await deletePlace.mutateAsync(p.name);
        deleted += 1;
      } catch (e) {
        failed.push(p.name);
      }
    }
    setBulkDeleting(false);

    if (failed.length === 0) {
      toast({
        title: `Deleted ${deleted} offline place${deleted === 1 ? "" : "s"}`,
        status: "success",
        duration: 3000,
      });
    } else {
      toast({
        title: `Deleted ${deleted}, failed to delete ${failed.length}`,
        description: failed.join(", "),
        status: "warning",
        duration: 5000,
      });
    }
  };

  if (isLoading) return <Spinner size="xl" color="adi.500" />;

  return (
    <Box>
      <HStack justify="space-between" mb={6} align="flex-start">
        <ConceptHeading name="place" pageKey="/places" size="lg" />
        <HStack spacing={2}>
          <Button onClick={toggleDensity} size="sm" variant="outline">
            {density === "comfortable" ? "Compact" : "Comfortable"}
          </Button>
          <Button onClick={() => nav("/places/new")} size="sm">
            + New place
          </Button>
        </HStack>
      </HStack>

      <VStack spacing={6} align="stretch">
        <Box>
          <HStack justify="space-between" mb={2} align="baseline">
            <Heading size="sm" color="text.primary">
              Live places{" "}
              <Text as="span" color="text.secondary" fontWeight="400">
                ({livePlaces.length})
              </Text>
            </Heading>
            <Text fontSize="xs" color="text.secondary">
              At least one backing exporter is online.
            </Text>
          </HStack>
          <PlacesTable
            places={livePlaces}
            placeToExporters={placeToExporters}
            placeToMissingMatches={placeToMissingMatches}
            placeHealth={placeHealth}
            expandedPlace={expandedPlace}
            onToggleExpand={handleToggleExpand}
            onToggleAcquire={handleToggleAcquire}
            onDelete={(name) => deletePlace.mutate(name)}
            emptyMessage="No live places. When an exporter comes online that matches a place, it moves here."
            density={density}
          />
        </Box>

        <Box>
          <HStack justify="space-between" mb={2} align="baseline">
            <Heading size="sm" color="text.primary">
              Offline places{" "}
              <Text as="span" color="text.secondary" fontWeight="400">
                ({offlinePlaces.length})
              </Text>
            </Heading>
            <HStack spacing={3}>
              <Text fontSize="xs" color="text.secondary">
                No backing exporter is currently contributing resources.
              </Text>
              <Button
                size="xs"
                colorScheme="red"
                variant="outline"
                leftIcon={<MdDelete />}
                isDisabled={offlinePlaces.length === 0 || bulkDeleting}
                isLoading={bulkDeleting}
                onClick={handleDeleteAllOffline}
              >
                Delete all offline
              </Button>
            </HStack>
          </HStack>
          <PlacesTable
            places={offlinePlaces}
            placeToExporters={placeToExporters}
            placeToMissingMatches={placeToMissingMatches}
            placeHealth={placeHealth}
            expandedPlace={expandedPlace}
            onToggleExpand={handleToggleExpand}
            onToggleAcquire={handleToggleAcquire}
            onDelete={(name) => deletePlace.mutate(name)}
            emptyMessage="No offline places."
            density={density}
          />
        </Box>
      </VStack>
    </Box>
  );
}
