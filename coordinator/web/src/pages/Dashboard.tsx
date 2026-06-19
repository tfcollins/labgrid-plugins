// coordinator/web/src/pages/Dashboard.tsx
import { useMemo } from "react";
import { Link as RouterLink } from "react-router-dom";
import {
  Badge, Button, Code, Heading, HStack, Link, SimpleGrid, Stack, Table, Tag, TagLabel, Tbody, Td, Th, Thead, Tr,
  Text, VStack,
} from "@chakra-ui/react";
import { useAuth } from "../auth/AuthContext";
import { usePlaces, useReleasePlace } from "../hooks/usePlaces";
import { useExporters } from "../hooks/useResources";
import { useRelationships } from "../hooks/useRelationships";
import { useRecentPlaces } from "../hooks/useRecentPlaces";
import { useWebSocket } from "../api/ws";
import { useReservationsLive, useCancelReservation } from "../hooks/useReservations";
import { formatAge } from "../lib/formatAge";
import ConceptGlanceCard from "../components/ConceptGlanceCard";
import MetricCard from "../components/ui/MetricCard";
import UtilizationBar from "../components/ui/UtilizationBar";
import Panel from "../components/ui/Panel";

const MILLIS_PER_HOUR = 1000 * 60 * 60;

function elapsed(seconds: number): string {
  const h = Math.floor((Date.now() - seconds * 1000) / MILLIS_PER_HOUR);
  if (h < 1) return "<1h";
  if (h < 48) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

export default function Dashboard() {
  useWebSocket();
  const { user } = useAuth();
  const { data: places = [] } = usePlaces();
  const { data: exporters = [] } = useExporters();
  const { placeToMissingMatches, placeToExporters } = useRelationships();
  const release = useReleasePlace();
  const { recent } = useRecentPlaces();

  const myPlaces = useMemo(() => places.filter((p) => p.acquired_username === user?.username), [places, user]);

  const existingPlaceNames = useMemo(() => new Set(places.map((p) => p.name)), [places]);
  const recentExisting = useMemo(
    () => recent.filter((name) => existingPlaceNames.has(name)),
    [recent, existingPlaceNames],
  );

  const { data: reservations = [] } = useReservationsLive();
  const cancelReservation = useCancelReservation();

  const myReservations = useMemo(() => {
    const u = user?.username;
    if (!u) return [];
    return reservations.filter((r) => r.owner === u || r.owner.endsWith(`/${u}`));
  }, [reservations, user]);

  const waitingCount = reservations.filter((r) => r.state === "waiting").length;

  const labStatus = {
    exportersOnline: exporters.filter((e) => Object.keys(e.groups).length > 0).length,
    placesFree: places.filter((p) => !p.acquired).length,
    placesHeldByOthers: places.filter((p) => p.acquired && p.acquired_username !== user?.username).length,
  };

  const placesBreakdown = useMemo(() => {
    let free = 0, acquired = 0, offline = 0;
    for (const p of places) {
      const live = (placeToExporters.get(p.name) ?? []).length > 0;
      if (!live) offline += 1;
      else if (p.acquired) acquired += 1;
      else free += 1;
    }
    return { free, acquired, offline, total: places.length };
  }, [places, placeToExporters]);

  const resourceCount = useMemo(
    () => exporters.reduce((n, e) => n + Object.values(e.groups).reduce((m, rs) => m + rs.length, 0), 0),
    [exporters],
  );

  const attention = useMemo(() => {
    const items: Array<{ key: string; message: React.ReactNode }> = [];
    // Exporters offline that any place references.
    const offlineRefs = exporters.filter((e) => Object.keys(e.groups).length === 0);
    for (const e of offlineRefs) {
      if (places.some((p) => p.matches.some((m) => m.exporter === e.name || m.exporter === "*"))) {
        items.push({
          key: `offline:${e.name}`,
          message: <Text><Link as={RouterLink} to={`/exporters/${e.name}`} color="link">{e.name}</Link> is offline but referenced by a place.</Text>,
        });
      }
    }
    // Places with broken matches.
    for (const [name, missing] of placeToMissingMatches.entries()) {
      if (missing.length === 0) continue;
      items.push({
        key: `broken:${name}`,
        message: <Text><Link as={RouterLink} to={`/places/${name}`} color="link">{name}</Link> has {missing.length} match rule(s) with no live resource.</Text>,
      });
    }
    // Places I've held > 24h.
    const now = Date.now() / 1000;
    for (const p of myPlaces) {
      if (now - p.changed > 24 * 60 * 60) {
        items.push({
          key: `stale:${p.name}`,
          message: <Text>You've been holding <Link as={RouterLink} to={`/places/${p.name}`} color="link">{p.name}</Link> for {elapsed(p.changed)} — release if you're done.</Text>,
        });
      }
    }
    // My reservations stuck waiting > 10 minutes.
    for (const r of myReservations) {
      if (r.state !== "waiting") continue;
      const age = Math.floor(Date.now() / 1000 - r.created);
      if (age > 600) {
        const filtSummary = Object.entries(r.filters)
          .map(([name, f]) => `${name}: ${Object.entries(f.filter).map(([k, v]) => `${k}=${v}`).join(",")}`)
          .join("; ");
        items.push({
          key: `waitres:${r.token}`,
          message: (
            <Text>
              Reservation waiting longer than 10 min —{" "}
              <Link as={RouterLink} to="/reservations" color="link">{filtSummary}</Link>.
            </Text>
          ),
        });
      }
    }
    return items;
  }, [exporters, places, placeToMissingMatches, myPlaces, myReservations]);

  return (
    <VStack align="stretch" spacing={6}>
      <Heading size="lg">Dashboard</Heading>

      {myPlaces.length > 0 && (
        <Panel p={4}>
          <Heading size="sm" mb={3}>My places</Heading>
          <Table size="sm">
            <Thead>
              <Tr><Th>Name</Th><Th>Held for</Th><Th>Hosted by</Th><Th></Th></Tr>
            </Thead>
            <Tbody>
              {myPlaces.map((p) => (
                <Tr key={p.name}>
                  <Td><Link as={RouterLink} to={`/places/${p.name}`} color="link">{p.name}</Link></Td>
                  <Td>{elapsed(p.changed)}</Td>
                  <Td>
                    <HStack spacing={1}>
                      {(placeToExporters.get(p.name) ?? []).map((e) => (
                        <Badge key={e.name} colorScheme={e.online ? "adi" : "gray"} fontSize="0.7em">{e.name}</Badge>
                      ))}
                    </HStack>
                  </Td>
                  <Td>
                    <Button size="xs" colorScheme="orange" variant="outline"
                            onClick={() => release.mutate(p.name)} isLoading={release.isPending}>
                      Release
                    </Button>
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </Panel>
      )}

      {myReservations.length > 0 && (
        <Panel p={4}>
          <Heading size="sm" mb={3}>My reservations</Heading>
          <Table size="sm">
            <Thead>
              <Tr>
                <Th>Token</Th>
                <Th>State</Th>
                <Th>Filters</Th>
                <Th>Allocated to</Th>
                <Th>Age</Th>
                <Th></Th>
              </Tr>
            </Thead>
            <Tbody>
              {myReservations.map((r) => (
                <Tr key={r.token}>
                  <Td>
                    <Link as={RouterLink} to="/reservations" color="link">
                      <Code fontSize="xs">{r.token.slice(0, 8)}</Code>
                    </Link>
                  </Td>
                  <Td>
                    <Badge colorScheme={r.state === "waiting" ? "yellow" : r.state === "allocated" ? "adi" : r.state === "acquired" ? "green" : "gray"}>
                      {r.state}
                    </Badge>
                  </Td>
                  <Td>
                    <HStack spacing={1} flexWrap="wrap">
                      {Object.entries(r.filters).map(([name, f]) => (
                        <Tag key={name} size="sm" variant="subtle">
                          <TagLabel>
                            {name}: {Object.entries(f.filter).map(([k, v]) => `${k}=${v}`).join(", ")}
                          </TagLabel>
                        </Tag>
                      ))}
                    </HStack>
                  </Td>
                  <Td>
                    {Object.entries(r.allocations).length === 0 ? (
                      <Text fontSize="xs" color="text.secondary">—</Text>
                    ) : (
                      <HStack spacing={1} flexWrap="wrap">
                        {Object.entries(r.allocations).map(([group, place]) => (
                          <Tag
                            key={group} size="sm" variant="subtle" colorScheme="adi"
                            as={RouterLink} to={`/places/${encodeURIComponent(place)}`}
                            cursor="pointer"
                          >
                            <TagLabel>{place}</TagLabel>
                          </Tag>
                        ))}
                      </HStack>
                    )}
                  </Td>
                  <Td><Text fontSize="xs">{formatAge(r.created)}</Text></Td>
                  <Td>
                    <Button
                      size="xs" colorScheme="red" variant="outline"
                      onClick={() => cancelReservation.mutate(r.token)}
                      isDisabled={r.state === "expired" || r.state === "invalid"}
                    >
                      Cancel
                    </Button>
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </Panel>
      )}

      <SimpleGrid columns={{ base: 1, sm: 2, lg: 4 }} spacing={4}>
        <MetricCard label="Exporters" value={`${labStatus.exportersOnline} of ${exporters.length}`} to="/resources" />
        <MetricCard label="Places" value={`${placesBreakdown.total} total`} to="/places">
          <UtilizationBar
            free={placesBreakdown.free}
            acquired={placesBreakdown.acquired}
            offline={placesBreakdown.offline}
          />
        </MetricCard>
        <MetricCard label="Resources" value={`${resourceCount}`} to="/resources" />
        <MetricCard label="Reservations" value={`${waitingCount} waiting`} to="/reservations" />
      </SimpleGrid>

      {attention.length > 0 && (
        <Panel p={4}>
          <Heading size="sm" mb={3} color="status.acquired">Attention needed</Heading>
          <Stack spacing={2}>
            {attention.map((a) => (
              <div key={a.key}>{a.message}</div>
            ))}
          </Stack>
        </Panel>
      )}

      {recentExisting.length > 0 && (
        <Panel p={4}>
          <Heading size="sm" mb={3}>Recently used places</Heading>
          <HStack spacing={2} flexWrap="wrap">
            {recentExisting.map((name) => (
              <Link key={name} as={RouterLink} to={`/places/${encodeURIComponent(name)}`} color="link" fontSize="sm">
                {name}
              </Link>
            ))}
          </HStack>
        </Panel>
      )}

      <ConceptGlanceCard />
    </VStack>
  );
}
