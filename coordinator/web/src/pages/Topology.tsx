import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Box,
  Collapse,
  HStack,
  Heading,
  IconButton,
  Input,
  Spinner,
  Switch,
  Text,
  VStack,
  useColorModeValue,
} from "@chakra-ui/react";
import { MdExpandLess, MdExpandMore } from "react-icons/md";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  Position,
  useNodesState,
  useEdgesState,
} from "reactflow";
import "reactflow/dist/style.css";
import { usePlaces } from "../hooks/usePlaces";
import { useExporters } from "../hooks/useResources";
import { useWebSocket } from "../api/ws";
import { useAuth } from "../auth/AuthContext";
import { CONCEPTS } from "../concepts";
import type { Place, Exporter } from "../api/client";

const EXPORTER_COLOR = "#0071ba";
const PLACE_FREE_COLOR = "#38a169";
const PLACE_ACQUIRED_COLOR = "#dd6b20";
const GROUP_COLOR = "#1e9bd7";

function buildGraph(
  places: Place[],
  exporters: Exporter[]
): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];

  // Layout: exporters on the left, places on the right
  const exporterX = 0;
  const groupX = 300;
  const placeX = 650;

  // Exporter nodes + group sub-nodes
  let ey = 0;
  const groupPositions: Record<string, { x: number; y: number }> = {};

  exporters.forEach((exp) => {
    const groupNames = Object.keys(exp.groups);
    const exporterY = ey;

    nodes.push({
      id: `exp:${exp.name}`,
      type: "default",
      position: { x: exporterX, y: exporterY },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      data: {
        label: exp.name,
      },
      style: {
        background: EXPORTER_COLOR,
        color: "white",
        border: "none",
        borderRadius: 8,
        fontWeight: 600,
        fontSize: 13,
        padding: "8px 16px",
        minWidth: 140,
        textAlign: "center" as const,
      },
    });

    groupNames.forEach((groupName, gi) => {
      const gy = exporterY + gi * 80;
      const groupId = `group:${exp.name}/${groupName}`;
      groupPositions[`${exp.name}/${groupName}`] = { x: groupX, y: gy };

      const resources = exp.groups[groupName];
      const availCount = resources.filter((r) => r.avail).length;
      const total = resources.length;

      nodes.push({
        id: groupId,
        type: "default",
        position: { x: groupX, y: gy },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        data: {
          label: `${groupName}\n${availCount}/${total} avail`,
        },
        style: {
          background: GROUP_COLOR,
          color: "white",
          border: "none",
          borderRadius: 6,
          fontSize: 11,
          padding: "6px 12px",
          minWidth: 160,
          textAlign: "center" as const,
          whiteSpace: "pre-line" as const,
        },
      });

      edges.push({
        id: `e:${exp.name}->${groupId}`,
        source: `exp:${exp.name}`,
        target: groupId,
        type: "smoothstep",
        style: { stroke: EXPORTER_COLOR, strokeWidth: 2 },
        animated: false,
      });

      ey = Math.max(ey, gy + 80);
    });

    if (groupNames.length === 0) {
      ey += 100;
    }
  });

  // Place nodes
  let py = 0;
  places.forEach((place) => {
    const isAcquired = !!place.acquired;
    const placeId = `place:${place.name}`;

    nodes.push({
      id: placeId,
      type: "default",
      position: { x: placeX, y: py },
      sourcePosition: Position.Left,
      targetPosition: Position.Left,
      data: {
        label: isAcquired
          ? `${place.name}\n⬤ ${place.acquired}`
          : place.name,
      },
      style: {
        background: isAcquired ? PLACE_ACQUIRED_COLOR : PLACE_FREE_COLOR,
        color: "white",
        border: "none",
        borderRadius: 8,
        fontWeight: 600,
        fontSize: 13,
        padding: "8px 16px",
        minWidth: 140,
        textAlign: "center" as const,
        whiteSpace: "pre-line" as const,
      },
    });

    // Edges from place matches to exporter groups
    place.matches.forEach((match, mi) => {
      // Find matching groups (supports wildcards with simple check)
      exporters.forEach((exp) => {
        const expMatch =
          match.exporter === "*" || match.exporter === exp.name;
        if (!expMatch) return;

        Object.keys(exp.groups).forEach((groupName) => {
          const groupMatch =
            match.group === "*" || match.group === groupName;
          if (!groupMatch) return;

          const groupId = `group:${exp.name}/${groupName}`;
          const edgeId = `e:${placeId}->${groupId}:${mi}`;

          // Check if this is an active allocation
          const isAllocated = place.acquired_resources.some(
            (path) => path[0] === exp.name && path[1] === groupName
          );

          edges.push({
            id: edgeId,
            source: groupId,
            target: placeId,
            type: "smoothstep",
            style: {
              stroke: isAllocated ? PLACE_ACQUIRED_COLOR : "#a0aec0",
              strokeWidth: isAllocated ? 2.5 : 1.5,
              strokeDasharray: isAllocated ? undefined : "6 3",
            },
            animated: isAllocated,
          });
        });
      });
    });

    py += 100;
  });

  return { nodes, edges };
}

export default function Topology() {
  useWebSocket();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const { user } = useAuth();
  const [filter, setFilter] = useState(() => params.get("focus")?.split(":")[1] ?? "");
  const [mineOnly, setMineOnly] = useState(false);
  const [hideOffline, setHideOffline] = useState(false);
  const [hideBroken, setHideBroken] = useState(false);
  const [legendOpen, setLegendOpen] = useState(() => localStorage.getItem("topology-legend-open") !== "0");

  useEffect(() => {
    localStorage.setItem("topology-legend-open", legendOpen ? "1" : "0");
  }, [legendOpen]);

  // When ?focus=<kind>:<name> is present, prefill the filter.
  useEffect(() => {
    const focus = params.get("focus");
    if (focus) setFilter(focus.split(":")[1] ?? "");
  }, [params]);

  const { data: places, isLoading: placesLoading } = usePlaces();
  const { data: exporters, isLoading: exportersLoading } = useExporters();

  const bgColor = useColorModeValue("#fafbfc", "#0b0f14");
  const miniMapBg = useColorModeValue("#e4e8ec", "#161f2a");
  const legendBg = "surface.subtle";

  const filteredPlaces = useMemo(() => {
    let ps = places ?? [];
    if (mineOnly && user) ps = ps.filter((p) => p.acquired === user.username);
    if (filter) ps = ps.filter((p) => p.name.toLowerCase().includes(filter.toLowerCase()));
    if (hideBroken) {
      // Local "has at least one live match" check; deliberately duplicated
      // here to avoid a cycle between this page and useRelationships(), which
      // itself reads the same places/exporters data.
      const liveNames = new Set<string>(
        (exporters ?? []).flatMap((e) =>
          Object.entries(e.groups).flatMap(([g, rs]) => rs.filter((r) => r.avail).map((r) => `${e.name}/${g}/${r.cls}`)),
        ),
      );
      ps = ps.filter((p) =>
        p.matches.some((m) =>
          [...liveNames].some((k) => {
            const [en, gn, cn] = k.split("/");
            return (m.exporter === "*" || m.exporter === en)
              && (m.group === "*" || m.group === gn)
              && (m.cls === "*" || m.cls === cn);
          }),
        ),
      );
    }
    return ps;
  }, [places, exporters, mineOnly, filter, hideBroken, user]);

  const filteredExporters = useMemo(() => {
    let es = exporters ?? [];
    if (hideOffline) es = es.filter((e) => Object.keys(e.groups).length > 0);
    if (filter) es = es.filter((e) => e.name.toLowerCase().includes(filter.toLowerCase()));
    return es;
  }, [exporters, hideOffline, filter]);

  const { initialNodes, initialEdges } = useMemo(() => {
    if (!filteredPlaces || !filteredExporters) return { initialNodes: [], initialEdges: [] };
    const { nodes, edges } = buildGraph(filteredPlaces, filteredExporters);
    return { initialNodes: nodes, initialEdges: edges };
  }, [filteredPlaces, filteredExporters]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Keep ReactFlow state in sync when filter changes rebuild the graph.
  useEffect(() => { setNodes(initialNodes); }, [initialNodes, setNodes]);
  useEffect(() => { setEdges(initialEdges); }, [initialEdges, setEdges]);

  const onNodeClick = useCallback((_: unknown, node: { id: string }) => {
    if (node.id.startsWith("exp:")) navigate(`/exporters/${encodeURIComponent(node.id.slice(4))}`);
    else if (node.id.startsWith("place:")) navigate(`/places/${encodeURIComponent(node.id.slice(6))}`);
  }, [navigate]);

  if (placesLoading || exportersLoading) {
    return <Spinner size="xl" color="adi.500" />;
  }

  return (
    <Box>
      <VStack align="stretch" spacing={2} mb={3}>
        <HStack>
          <Heading size="lg" color="text.primary">Topology</Heading>
          <IconButton
            aria-label={legendOpen ? "Collapse legend" : "Expand legend"}
            size="xs" variant="ghost"
            icon={legendOpen ? <MdExpandLess /> : <MdExpandMore />}
            onClick={() => setLegendOpen(!legendOpen)}
          />
        </HStack>

        <Collapse in={legendOpen}>
          <VStack align="stretch" spacing={1} fontSize="sm" bg={legendBg} p={3} borderRadius="md">
            <LegendRow color={CONCEPTS.exporter.color} label="Exporters" gloss={CONCEPTS.exporter.gloss} />
            <LegendRow color={CONCEPTS.group.color} label="Groups" gloss={CONCEPTS.group.gloss} />
            <LegendRow color={CONCEPTS.place.color} label="Places (free)" gloss={CONCEPTS.place.gloss} />
            <LegendRow color={CONCEPTS.acquire.color} label="Places (held)" gloss="Someone's currently holding this place." />
            <Text color="text.secondary">
              <Text as="span" fontWeight={600}>Match rules</Text> — solid animated edge = live match. Dashed = rule exists but nothing currently matches.
            </Text>
          </VStack>
        </Collapse>

        <HStack>
          <Input
            size="sm" maxW="260px"
            placeholder="Filter by name"
            value={filter}
            onChange={(e) => {
              setFilter(e.target.value);
              const p = new URLSearchParams(params);
              if (e.target.value) p.set("focus", `all:${e.target.value}`);
              else p.delete("focus");
              setParams(p, { replace: true });
            }}
          />
          <HStack pl={3} spacing={4}>
            <HStack><Switch isChecked={mineOnly} onChange={(e) => setMineOnly(e.target.checked)} size="sm" /><Text fontSize="sm">Mine only</Text></HStack>
            <HStack><Switch isChecked={hideOffline} onChange={(e) => setHideOffline(e.target.checked)} size="sm" /><Text fontSize="sm">Hide offline exporters</Text></HStack>
            <HStack><Switch isChecked={hideBroken} onChange={(e) => setHideBroken(e.target.checked)} size="sm" /><Text fontSize="sm">Hide places without live matches</Text></HStack>
          </HStack>
        </HStack>
      </VStack>

      {(filteredPlaces.length === 0 && filteredExporters.length === 0) && (
        <Box p={8} textAlign="center" color="text.secondary">
          Nothing to show yet. Add an exporter or a place — this view lights up as soon as either appears.
        </Box>
      )}

      <Box
        h="calc(100vh - 260px)"
        borderRadius="lg"
        overflow="hidden"
        border="1px solid"
        borderColor="border.hairline"
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          fitView
          fitViewOptions={{ padding: 0.3 }}
          proOptions={{ hideAttribution: true }}
          style={{ background: bgColor }}
        >
          <Background gap={20} size={1} />
          <Controls />
          <MiniMap
            nodeStrokeWidth={3}
            style={{ background: miniMapBg }}
            maskColor="rgba(0,0,0,0.1)"
          />
        </ReactFlow>
      </Box>
    </Box>
  );
}

function LegendRow({ color, label, gloss }: { color: string; label: string; gloss: string }) {
  return (
    <HStack>
      <Box w="14px" h="14px" borderRadius="4px" bg={color} />
      <Text fontWeight={600} w="130px">{label}</Text>
      <Text color="text.secondary">{gloss}</Text>
    </HStack>
  );
}
