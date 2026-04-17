import { Link as RLink } from "react-router-dom";
import {
  Box, Heading, Table, Tbody, Td, Th, Thead, Tr, Button, Spinner, Badge,
} from "@chakra-ui/react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { recordingsApi } from "../api/recordings";
import { useAuth } from "../auth/AuthContext";

function fmtTs(t: number) {
  return new Date(t * 1000).toISOString().replace("T", " ").slice(0, 19);
}
function fmtDuration(s: number, e: number | null) {
  if (e == null) return "—";
  const d = Math.round(e - s);
  const m = Math.floor(d / 60); const r = d % 60;
  return `${m}m ${r}s`;
}
function fmtBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1048576).toFixed(1)} MB`;
}

export default function Recordings() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const { data: items = [], isLoading } = useQuery({
    queryKey: ["recordings"],
    queryFn: () => recordingsApi.list(),
  });
  const deleteM = useMutation({
    mutationFn: (id: string) => recordingsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recordings"] }),
  });

  if (isLoading) return <Spinner />;

  return (
    <Box p={4}>
      <Heading size="md" mb={4}>Console recordings</Heading>
      <Table size="sm">
        <Thead>
          <Tr>
            <Th>Started</Th><Th>Place</Th><Th>Resource</Th>
            <Th>Duration</Th><Th>Size</Th><Th>End</Th><Th></Th>
          </Tr>
        </Thead>
        <Tbody>
          {items.map((r) => (
            <Tr key={r.id}>
              <Td>{fmtTs(r.started_at)}</Td>
              <Td>{r.place_name}</Td>
              <Td>{r.resource_name}</Td>
              <Td>{fmtDuration(r.started_at, r.ended_at)}</Td>
              <Td>{fmtBytes(r.byte_count)}</Td>
              <Td>{r.terminated_reason && <Badge>{r.terminated_reason}</Badge>}</Td>
              <Td>
                <Button as={RLink} size="xs" mr={2} to={`/recordings/${r.id}`}>Play</Button>
                {user?.role === "admin" && (
                  <Button size="xs" colorScheme="red" onClick={() => deleteM.mutate(r.id)}>
                    Delete
                  </Button>
                )}
              </Td>
            </Tr>
          ))}
        </Tbody>
      </Table>
    </Box>
  );
}
