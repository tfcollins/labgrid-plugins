import { useState } from "react";
import {
  Box,
  Table, Thead, Tbody, Tr, Th, Td,
  Badge, Button, HStack, Spinner, Text,
  useDisclosure,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody, ModalFooter, ModalCloseButton,
  Input, VStack, FormControl, FormLabel,
  NumberInput, NumberInputField,
  useToast,
  Code, Tag, TagLabel, Stack,
} from "@chakra-ui/react";
import Panel from "../components/ui/Panel";
import { Link as RouterLink } from "react-router-dom";
import {
  useReservationsLive,
  useCreateReservation,
  useCancelReservation,
} from "../hooks/useReservations";
import ConceptHeading from "../components/ConceptHeading";
import Term from "../components/Term";
import { formatAge } from "../lib/formatAge";

const stateColors: Record<string, string> = {
  waiting: "yellow",
  allocated: "adi",
  acquired: "green",
  expired: "gray",
  invalid: "red",
};

function formatDuration(secs: number): string {
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h`;
  return `${Math.floor(secs / 86400)}d`;
}

export default function Reservations() {
  const { data: reservations, isLoading } = useReservationsLive();
  const createReservation = useCreateReservation();
  const cancelReservation = useCancelReservation();
  const { isOpen, onOpen, onClose } = useDisclosure();
  const [filterKey, setFilterKey] = useState("main");
  const [filterTag, setFilterTag] = useState("");
  const [filterValue, setFilterValue] = useState("");
  const [prio, setPrio] = useState(0);
  const toast = useToast();
  const handleCreate = async () => {
    if (!filterTag.trim() || !filterValue.trim()) return;
    try {
      await createReservation.mutateAsync({
        filters: { [filterKey]: { [filterTag]: filterValue } },
        prio,
      });
      setFilterTag("");
      setFilterValue("");
      setPrio(0);
      onClose();
      toast({ title: "Reservation created", status: "success", duration: 2000 });
    } catch (e) {
      toast({ title: "Failed to create reservation", status: "error", duration: 3000 });
    }
  };

  if (isLoading) return <Spinner size="xl" color="adi.500" />;

  return (
    <Box>
      <HStack justify="space-between" mb={6} align="flex-start">
        <ConceptHeading name="reservation" pageKey="/reservations" size="lg" />
        <Button onClick={onOpen} size="sm">
          Create Reservation
        </Button>
      </HStack>

      <Panel overflow="hidden">
        <Table variant="simple" size="sm">
          <Thead>
            <Tr>
              <Th>Token</Th>
              <Th>Owner</Th>
              <Th>State</Th>
              <Th>Priority</Th>
              <Th>Filters</Th>
              <Th>Allocations</Th>
              <Th>Age</Th>
              <Th>Expires</Th>
              <Th>Actions</Th>
            </Tr>
          </Thead>
          <Tbody>
            {reservations?.map((r) => {
              const expiresIn = r.timeout > 0 ? Math.max(0, Math.floor(r.created + r.timeout - Date.now() / 1000)) : null;
              return (
                <Tr key={r.token}>
                  <Td><Code fontSize="xs">{r.token.slice(0, 8)}</Code></Td>
                  <Td>{r.owner}</Td>
                  <Td>
                    <Badge colorScheme={stateColors[r.state] || "gray"}>{r.state}</Badge>
                  </Td>
                  <Td>{r.prio}</Td>
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
                            key={group}
                            size="sm"
                            variant="subtle"
                            colorScheme="adi"
                            as={RouterLink}
                            to={`/places/${encodeURIComponent(place)}`}
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
                    {expiresIn === null ? (
                      <Text fontSize="xs">—</Text>
                    ) : (
                      <Text fontSize="xs" color={expiresIn < 60 ? "orange.500" : undefined}>
                        {formatDuration(expiresIn)}
                      </Text>
                    )}
                  </Td>
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
              );
            })}
            {(!reservations || reservations.length === 0) && (
              <Tr>
                <Td colSpan={9} textAlign="center" color="text.secondary" py={8}>
                  <Stack spacing={2} align="center">
                    <Text>No active reservations yet.</Text>
                    <Text fontSize="sm" color="text.secondary" maxW="md">
                      A <Term name="reservation">reservation</Term> queues a claim on a place by tag — for example, reserve any place with <Code fontSize="xs">board=vcu118</Code> without knowing which specific place.
                    </Text>
                  </Stack>
                </Td>
              </Tr>
            )}
          </Tbody>
        </Table>
      </Panel>

      {/* Create Reservation Modal */}
      <Modal isOpen={isOpen} onClose={onClose} isCentered>
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Create Reservation</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={4}>
              <FormControl>
                <FormLabel fontSize="sm">Filter group name</FormLabel>
                <Input
                  size="sm"
                  placeholder="main"
                  value={filterKey}
                  onChange={(e) => setFilterKey(e.target.value)}
                />
              </FormControl>
              <FormControl>
                <FormLabel fontSize="sm">Tag key</FormLabel>
                <Input
                  size="sm"
                  placeholder="e.g., board"
                  value={filterTag}
                  onChange={(e) => setFilterTag(e.target.value)}
                />
              </FormControl>
              <FormControl>
                <FormLabel fontSize="sm">Tag value</FormLabel>
                <Input
                  size="sm"
                  placeholder="e.g., vcu118"
                  value={filterValue}
                  onChange={(e) => setFilterValue(e.target.value)}
                />
              </FormControl>
              <FormControl>
                <FormLabel fontSize="sm">Priority</FormLabel>
                <NumberInput
                  size="sm"
                  value={prio}
                  onChange={(_, val) => setPrio(val || 0)}
                >
                  <NumberInputField />
                </NumberInput>
              </FormControl>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={onClose}>
              Cancel
            </Button>
            <Button onClick={handleCreate} isLoading={createReservation.isPending}>
              Create
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </Box>
  );
}
