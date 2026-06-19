import {
  Box,
  Heading,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Badge,
  Select,
  HStack,
  Button,
  Text,
  Spinner,
} from "@chakra-ui/react";
import { useState } from "react";
import { useEvents } from "../hooks/useStats";

const PAGE_SIZE = 50;

function eventBadgeColor(eventType: string): string {
  if (eventType.includes("acquired") || eventType.includes("online")) {
    return "green";
  }
  if (eventType.includes("released") || eventType.includes("offline")) {
    return "red";
  }
  if (eventType.includes("created") || eventType.includes("deleted")) {
    return "purple";
  }
  if (
    eventType.includes("resource_acquired") ||
    eventType.includes("resource_released")
  ) {
    return "adi";
  }
  if (eventType.includes("reservation")) {
    return "yellow";
  }
  return "gray";
}

function formatTimestamp(ts: number): string {
  return new Date(ts * 1000).toLocaleString();
}

export default function EventLog() {
  const [page, setPage] = useState(0);
  const [eventType, setEventType] = useState("");

  const { data, isLoading } = useEvents({
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
    event_type: eventType || undefined,
  });

  const events = data?.events ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <Box>
      <Heading size="lg" mb={6} color="text.primary">
        Event Log
      </Heading>

      <HStack mb={4} spacing={4}>
        <Select
          w="200px"
          placeholder="All event types"
          value={eventType}
          onChange={(e) => {
            setEventType(e.target.value);
            setPage(0);
          }}
        >
          <option value="place_acquired">Place Acquired</option>
          <option value="place_released">Place Released</option>
          <option value="place_created">Place Created</option>
          <option value="place_deleted">Place Deleted</option>
          <option value="resource_online">Resource Online</option>
          <option value="resource_offline">Resource Offline</option>
          <option value="resource_acquired">Resource Acquired</option>
          <option value="resource_released">Resource Released</option>
          <option value="reservation_created">Reservation Created</option>
          <option value="reservation_cancelled">Reservation Cancelled</option>
        </Select>
      </HStack>

      {isLoading ? (
        <Spinner size="xl" color="adi.500" />
      ) : events.length === 0 ? (
        <Text color="text.secondary">No events found.</Text>
      ) : (
        <>
          <Box overflowX="auto">
            <Table variant="simple" size="sm">
              <Thead>
                <Tr>
                  <Th>Time</Th>
                  <Th>Type</Th>
                  <Th>Details</Th>
                  <Th>User</Th>
                </Tr>
              </Thead>
              <Tbody>
                {events.map((evt) => (
                  <Tr key={evt.id}>
                    <Td whiteSpace="nowrap">
                      {formatTimestamp(evt.timestamp)}
                    </Td>
                    <Td>
                      <Badge colorScheme={eventBadgeColor(evt.event_type)}>
                        {evt.event_type}
                      </Badge>
                    </Td>
                    <Td>
                      {evt.place_name ?? evt.resource_key ?? evt.details ?? "-"}
                    </Td>
                    <Td>{evt.user ?? "-"}</Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          </Box>

          <HStack justify="center" mt={4} spacing={4}>
            <Button
              size="sm"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              isDisabled={page === 0}
            >
              Previous
            </Button>
            <Text fontSize="sm">
              Page {page + 1} of {totalPages}
            </Text>
            <Button
              size="sm"
              onClick={() => setPage((p) => p + 1)}
              isDisabled={page + 1 >= totalPages}
            >
              Next
            </Button>
          </HStack>
        </>
      )}
    </Box>
  );
}
