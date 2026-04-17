import { useEffect, useMemo, useState } from "react";
import { Link as RLink, useParams } from "react-router-dom";
import {
  Box, Code, Heading, HStack, Button, Badge, Table, Tbody, Td, Th, Thead, Tr,
  Text, Spinner, Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalFooter, ModalCloseButton, FormControl, FormLabel, Select,
  useDisclosure, useToast, IconButton, Tag, Flex, Link, Stack,
} from "@chakra-ui/react";
import { MdDelete } from "react-icons/md";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { isPowerResource } from "../api/power";
import { isSDMuxResource } from "../api/sdmux";
import PowerControls from "../components/PowerControls";
import SDMuxControls from "../components/SDMuxControls";
import DownloadEnvModal from "../components/DownloadEnvModal";
import RelatedPanel from "../components/RelatedPanel";
import Term from "../components/Term";
import { useRelationships } from "../hooks/useRelationships";
import { useRecentPlaces } from "../hooks/useRecentPlaces";
import { useReservationsLive } from "../hooks/useReservations";
import { formatAge } from "../lib/formatAge";

/** Group class names with counts: ["a","a","b"] -> "2 a, 1 b". */
function summarizeByClass(classes: string[]): string {
  const counts = new Map<string, number>();
  for (const c of classes) counts.set(c, (counts.get(c) ?? 0) + 1);
  return [...counts.entries()]
    .sort()
    .map(([cls, n]) => `${n} ${cls}`)
    .join(", ");
}

export default function PlaceDetail() {
  const { name = "" } = useParams();
  const { user } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();

  const { placeToExporters, placeToMissingMatches } = useRelationships();
  const { record } = useRecentPlaces();
  useEffect(() => {
    if (name) record(name);
  }, [name, record]);

  const { data: place, isLoading } = useQuery({
    queryKey: ["place", name],
    queryFn: () => api.getPlace(name),
  });
  const { data: allResources = [] } = useQuery({
    queryKey: ["resources"],
    queryFn: () => api.getResources(),
  });

  const { data: reservations = [] } = useReservationsLive();

  const myReservation = useMemo(
    () => place?.reservation ? reservations.find((r) => r.token === place.reservation) : null,
    [place, reservations],
  );

  const acquireM = useMutation({
    mutationFn: () => api.acquirePlace(name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["place", name] }),
  });
  const releaseM = useMutation({
    mutationFn: () => api.releasePlace(name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["place", name] }),
  });

  const addMatchM = useMutation({
    mutationFn: (pattern: string) => api.addPlaceMatch(name, pattern),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["place", name] });
      toast({ status: "success", title: "Match added", duration: 2000 });
    },
    onError: (e: unknown) =>
      toast({ status: "error", title: e instanceof Error ? e.message : String(e) }),
  });
  const deleteMatchM = useMutation({
    mutationFn: (pattern: string) => api.deletePlaceMatch(name, pattern),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["place", name] }),
  });

  const matchModal = useDisclosure();
  const downloadModal = useDisclosure();
  const [exporter, setExporter] = useState("");
  const [group, setGroup] = useState("");
  const [cls, setCls] = useState("*");

  // For dropdowns
  const exporters = useMemo(
    () => Array.from(new Set(allResources.map((r) => r.exporter))).sort(),
    [allResources]
  );
  const groups = useMemo(
    () =>
      Array.from(
        new Set(allResources.filter((r) => r.exporter === exporter).map((r) => r.group))
      ).sort(),
    [allResources, exporter]
  );
  const classes = useMemo(
    () =>
      Array.from(
        new Set(
          allResources
            .filter((r) => r.exporter === exporter && (group === "" || r.group === group))
            .map((r) => r.cls)
        )
      ).sort(),
    [allResources, exporter, group]
  );

  const placeResources = useMemo(
    () => {
      if (!place) return [];
      return allResources.filter((r) =>
        place.matches.some(
          (m) =>
            m.exporter === r.exporter &&
            m.group === r.group &&
            (m.cls === "*" || m.cls === r.cls)
        )
      );
    },
    [allResources, place]
  );

  const resourceClasses = useMemo(
    () => new Set(placeResources.map((r) => r.cls)),
    [placeResources],
  );

  if (isLoading || !place) return <Spinner />;

  const owner = place.acquired_username;
  const isOwner = owner != null && user?.username === owner;
  const canAcquire = owner == null && user != null;
  const canEdit = user != null && (owner == null || isOwner || user.role === "admin");

  const submitMatch = () => {
    if (!exporter || !group) {
      toast({ status: "warning", title: "Pick exporter + group" });
      return;
    }
    const pattern = `${exporter}/${group}/${cls || "*"}`;
    addMatchM.mutate(pattern, {
      onSettled: () => {
        matchModal.onClose();
        setExporter(""); setGroup(""); setCls("*");
      },
    });
  };

  return (
    <Flex gap={6} align="flex-start" direction={{ base: "column", md: "row" }}>
      <Box flex="1" minW={0}>
        <HStack mb={4}>
          <Heading size="md">{place.name}</Heading>
          {owner && <Badge colorScheme="orange">acquired by <Term name="acquire">{owner}</Term></Badge>}
          <Box ml="auto">
            <Button size="sm" variant="outline" onClick={downloadModal.onOpen}>
              Download env yaml
            </Button>
            {canAcquire && (
              <Button colorScheme="blue" onClick={() => acquireM.mutate()} isLoading={acquireM.isPending}>
                Acquire
              </Button>
            )}
            {isOwner && (
              <Button colorScheme="red" onClick={() => releaseM.mutate()} isLoading={releaseM.isPending}>
                Release
              </Button>
            )}
          </Box>
        </HStack>

        {place.comment && <Text mb={4} color="gray.500">{place.comment}</Text>}

        <HStack mb={2}>
          <Heading size="sm">Resource matches</Heading>
          {canEdit && (
            <Button ml="auto" size="xs" colorScheme="blue" onClick={matchModal.onOpen}>
              + Add match
            </Button>
          )}
        </HStack>
        {place.matches.length === 0 ? (
          <Text color="gray.500" mb={4} fontSize="sm">
            No matches yet — add one to attach exporter resources to this place.
          </Text>
        ) : (
          <Table size="sm" mb={4}>
            <Thead>
              <Tr>
                <Th>Pattern</Th><Th>Rename</Th><Th></Th>
              </Tr>
            </Thead>
            <Tbody>
              {place.matches.map((m, i) => {
                const pattern = `${m.exporter}/${m.group}/${m.cls}${m.name ? "/" + m.name : ""}`;
                return (
                  <Tr key={i}>
                    <Td><Tag>{pattern}</Tag></Td>
                    <Td>{m.rename ?? ""}</Td>
                    <Td>
                      {canEdit && (
                        <IconButton
                          aria-label="Delete match" size="xs" variant="ghost"
                          icon={<MdDelete />}
                          onClick={() => deleteMatchM.mutate(pattern)}
                        />
                      )}
                    </Td>
                  </Tr>
                );
              })}
            </Tbody>
          </Table>
        )}

        <Heading size="sm" mb={2}>Resources</Heading>
        {placeResources.length === 0 ? (
          <Text color="gray.500" fontSize="sm">
            No resources match. Add a resource match above (or check that the
            exporter is online).
          </Text>
        ) : (
          <Table size="sm">
            <Thead>
              <Tr>
                <Th>Class</Th><Th>Name</Th><Th>Exporter</Th><Th>Avail</Th><Th></Th>
              </Tr>
            </Thead>
            <Tbody>
              {placeResources.map((r) => (
                <Tr key={`${r.exporter}/${r.group}/${r.cls}/${r.name}`}>
                  <Td>{r.cls}</Td>
                  <Td>{r.name}</Td>
                  <Td>{r.exporter}</Td>
                  <Td><Badge colorScheme={r.avail ? "green" : "red"}>{r.avail ? "yes" : "no"}</Badge></Td>
                  <Td>
                    {r.cls === "NetworkSerialPort" && isOwner && (
                      <Button
                        as={RLink}
                        size="xs"
                        to={`/places/${encodeURIComponent(name)}/console/${encodeURIComponent(r.name)}`}
                      >
                        Open Console
                      </Button>
                    )}
                    {isPowerResource(r.cls) && (
                      <PowerControls place={name} resource={r.name} enabled={isOwner} />
                    )}
                    {isSDMuxResource(r.cls) && (
                      <SDMuxControls place={name} resource={r.name} enabled={isOwner} />
                    )}
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        )}

        {/* Add match modal */}
        <Modal isOpen={matchModal.isOpen} onClose={matchModal.onClose}>
          <ModalOverlay />
          <ModalContent>
            <ModalHeader>Add resource match</ModalHeader>
            <ModalCloseButton />
            <ModalBody>
              <FormControl mb={3}>
                <FormLabel htmlFor="exporter">Exporter</FormLabel>
                <Select
                  id="exporter" value={exporter}
                  onChange={(e) => { setExporter(e.target.value); setGroup(""); setCls("*"); }}
                  placeholder="Select an exporter"
                >
                  {exporters.map((e) => <option key={e} value={e}>{e}</option>)}
                </Select>
              </FormControl>
              <FormControl mb={3}>
                <FormLabel htmlFor="group">Group</FormLabel>
                <Select
                  id="group" value={group}
                  onChange={(e) => { setGroup(e.target.value); setCls("*"); }}
                  placeholder="Select a group" isDisabled={!exporter}
                >
                  {groups.map((g) => <option key={g} value={g}>{g}</option>)}
                </Select>
              </FormControl>
              <FormControl>
                <FormLabel htmlFor="cls">Resource class</FormLabel>
                <Select
                  id="cls" value={cls}
                  onChange={(e) => setCls(e.target.value)}
                  isDisabled={!group}
                >
                  <option value="*">* (all classes)</option>
                  {classes.map((c) => <option key={c} value={c}>{c}</option>)}
                </Select>
              </FormControl>
              <Text fontSize="xs" color="gray.500" mt={3}>
                Pattern preview:{" "}
                <code>{exporter && group ? `${exporter}/${group}/${cls || "*"}` : "—"}</code>
              </Text>
            </ModalBody>
            <ModalFooter>
              <Button mr={2} onClick={matchModal.onClose}>Cancel</Button>
              <Button colorScheme="blue" onClick={submitMatch} isLoading={addMatchM.isPending}>
                Add match
              </Button>
            </ModalFooter>
          </ModalContent>
        </Modal>

        <DownloadEnvModal
          isOpen={downloadModal.isOpen}
          onClose={downloadModal.onClose}
          placeName={name}
          resourceClasses={resourceClasses}
        />
      </Box>

      {/* ===== new right-hand Related sidebar ===== */}
      <RelatedPanel>
        <RelatedPanel.Section title="Exporters contributing">
          {(placeToExporters.get(name) ?? []).length === 0 ? (
            <Text color="gray.500">None online</Text>
          ) : (
            <Stack spacing={1}>
              {(placeToExporters.get(name) ?? []).map((e) => (
                <HStack key={e.name}>
                  <Box w="8px" h="8px" borderRadius="full" bg={e.online ? "green.400" : "gray.400"} />
                  <RLink to={`/exporters/${encodeURIComponent(e.name)}`}>
                    <Text color="blue.500">{e.name}</Text>
                  </RLink>
                  {!e.online && <Text fontSize="xs" color="gray.500">offline</Text>}
                </HStack>
              ))}
            </Stack>
          )}
        </RelatedPanel.Section>

        <RelatedPanel.Section title="Live resources">
          {placeResources.length === 0 ? (
            <Text color="gray.500">None</Text>
          ) : (
            <Text>
              {summarizeByClass(placeResources.map((r) => r.cls))}
            </Text>
          )}
        </RelatedPanel.Section>

        {(placeToMissingMatches.get(name) ?? []).length > 0 && (
          <RelatedPanel.Section title="Missing matches" tone="warning">
            <Stack spacing={1}>
              {(placeToMissingMatches.get(name) ?? []).map((m, i) => (
                <Text key={i} fontFamily="mono" fontSize="xs">
                  {m.exporter}/{m.group}/{m.cls}
                  {m.name ? `/${m.name}` : ""}
                </Text>
              ))}
              <Text color="orange.500" fontSize="xs">
                ⚠ no matching resource online right now
              </Text>
            </Stack>
          </RelatedPanel.Section>
        )}

        <RelatedPanel.Section title="Acquired by">
          {owner ? (
            <Stack spacing={1}>
              <Text>{owner}</Text>
              <Text color="gray.500" fontSize="xs">
                This place is reserved — only this user can use its resources until released.
              </Text>
            </Stack>
          ) : (
            <Text color="gray.500">Not reserved — press Acquire to reserve.</Text>
          )}
        </RelatedPanel.Section>

        {place?.reservation && (
          <RelatedPanel.Section title="Reservation">
            {myReservation ? (
              <Stack spacing={1}>
                <HStack>
                  <Code fontSize="xs">{myReservation.token.slice(0, 8)}</Code>
                  <Badge colorScheme={myReservation.state === "waiting" ? "yellow" : myReservation.state === "allocated" ? "blue" : myReservation.state === "acquired" ? "green" : "gray"}>
                    {myReservation.state}
                  </Badge>
                </HStack>
                <Text color="gray.500" fontSize="xs">
                  Owner: {myReservation.owner} · Age: {formatAge(myReservation.created)}
                </Text>
                <Link as={RLink} to="/reservations" color="blue.500" fontSize="xs">Open in Reservations →</Link>
              </Stack>
            ) : (
              <Stack spacing={1}>
                <Code fontSize="xs">{place.reservation.slice(0, 8)}</Code>
                <Text color="gray.500" fontSize="xs">Reservation details not available (may have expired).</Text>
              </Stack>
            )}
          </RelatedPanel.Section>
        )}

        <RelatedPanel.Footer to={`/topology?focus=place:${encodeURIComponent(name)}`}>
          Show in Topology →
        </RelatedPanel.Footer>
      </RelatedPanel>
    </Flex>
  );
}
