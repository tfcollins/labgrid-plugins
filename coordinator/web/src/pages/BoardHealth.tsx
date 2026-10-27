import { useState } from "react";
import {
  Alert,
  AlertIcon,
  Badge,
  Box,
  Button,
  ButtonGroup,
  Checkbox,
  Flex,
  FormControl,
  FormHelperText,
  FormLabel,
  HStack,
  Heading,
  Icon,
  IconButton,
  Input,
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalOverlay,
  Select,
  SimpleGrid,
  Spinner,
  Switch,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Table,
  Tabs,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tooltip,
  Tr,
  VStack,
  useDisclosure,
  useToast,
} from "@chakra-ui/react";
import {
  MdPlayArrow,
  MdRefresh,
  MdStop,
  MdDelete,
  MdAdd,
  MdVisibility,
} from "react-icons/md";
import type {
  BoardHealthPlace,
  HealthCheckSchedule,
  HealthStatus,
} from "../api/boardHealth";
import MetricCard from "../components/ui/MetricCard";
import Panel from "../components/ui/Panel";
import { formatAge } from "../lib/formatAge";
import {
  useBoardHealthRun,
  useBoardHealthRuns,
  useBoardHealthSchedules,
  useBoardHealthSummary,
  useCancelHealthCheck,
  useCreateSchedule,
  useDeleteSchedule,
  useTriggerHealthCheck,
  useTriggerSchedule,
  useUpdateSchedule,
} from "../hooks/useBoardHealth";

const STATUS_COLOR_SCHEME: Record<HealthStatus, string> = {
  passed: "green",
  failed: "red",
  busy: "yellow",
  running: "blue",
  pending: "purple",
  cancelled: "orange",
  untested: "gray",
};

const CRON_PRESETS = [
  { label: "Every 6 Hours (0 */6 * * *)", value: "0 */6 * * *" },
  { label: "Every 12 Hours (0 */12 * * *)", value: "0 */12 * * *" },
  { label: "Daily at 2:00 AM (0 2 * * *)", value: "0 2 * * *" },
  { label: "Weekly on Sunday at 2:00 AM (0 2 * * 0)", value: "0 2 * * 0" },
  { label: "Custom Expression", value: "custom" },
];

export default function BoardHealth() {
  const toast = useToast();
  const { data: summary, isLoading: summaryLoading, refetch: refetchSummary } = useBoardHealthSummary();
  const { data: schedules = [], isLoading: schedulesLoading } = useBoardHealthSchedules();
  const { data: runs = [], isLoading: runsLoading, refetch: refetchRuns } = useBoardHealthRuns({ limit: 50 });

  const triggerMutation = useTriggerHealthCheck();
  const cancelMutation = useCancelHealthCheck();
  const createScheduleMutation = useCreateSchedule();
  const updateScheduleMutation = useUpdateSchedule();
  const deleteScheduleMutation = useDeleteSchedule();
  const triggerScheduleMutation = useTriggerSchedule();

  // Modals state
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const { isOpen: isLogOpen, onOpen: onOpenLog, onClose: onCloseLog } = useDisclosure();
  const { isOpen: isSchedOpen, onOpen: onOpenSched, onClose: onCloseSched } = useDisclosure();
  const { isOpen: isCheckOpen, onOpen: onOpenCheck, onClose: onCloseCheck } = useDisclosure();

  // Manual Check Form State
  const [checkPlaces, setCheckPlaces] = useState<string[]>([]);
  const [checkImage, setCheckImage] = useState<string>("");
  const [checkPowerDown, setCheckPowerDown] = useState<boolean>(true);

  // Schedule Form State
  const [schedName, setSchedName] = useState("");
  const [schedDesc, setSchedDesc] = useState("");
  const [schedPreset, setSchedPreset] = useState("0 2 * * *");
  const [schedCron, setSchedCron] = useState("0 2 * * *");
  const [schedTargetAll, setSchedTargetAll] = useState(true);
  const [schedPlaces, setSchedPlaces] = useState<string[]>([]);
  const [schedImage, setSchedImage] = useState("");
  const [schedPowerDown, setSchedPowerDown] = useState(true);

  // Active run query for log modal
  const { data: selectedRun, isLoading: logLoading } = useBoardHealthRun(selectedRunId);

  const handleOpenLog = (runId: number) => {
    setSelectedRunId(runId);
    onOpenLog();
  };

  const handleQuickCheck = (placeName: string) => {
    setCheckPlaces([placeName]);
    setCheckImage("");
    setCheckPowerDown(true);
    onOpenCheck();
  };

  const handleCheckAll = () => {
    if (!summary?.places) return;
    setCheckPlaces(summary.places.map((p) => p.name));
    setCheckImage("");
    setCheckPowerDown(true);
    onOpenCheck();
  };

  const handleExecuteCheck = async () => {
    if (checkPlaces.length === 0) return;
    try {
      await triggerMutation.mutateAsync({
        places: checkPlaces,
        image: checkImage.trim() || null,
        power_down: checkPowerDown,
      });
      toast({
        title: "Health Check Triggered",
        description: `Started checks on ${checkPlaces.length} board(s).`,
        status: "success",
        duration: 4000,
        isClosable: true,
      });
      onCloseCheck();
    } catch (err: any) {
      toast({
        title: "Failed to trigger health check",
        description: err.message,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    }
  };

  const handleSaveSchedule = async () => {
    if (!schedName.trim()) {
      toast({ title: "Schedule name is required", status: "warning" });
      return;
    }
    const finalCron = schedPreset === "custom" ? schedCron.trim() : schedPreset;
    if (!finalCron) {
      toast({ title: "Cron expression is required", status: "warning" });
      return;
    }
    const finalPlaces = schedTargetAll ? ["*"] : schedPlaces;
    if (finalPlaces.length === 0) {
      toast({ title: "Select at least one place or target all", status: "warning" });
      return;
    }

    try {
      await createScheduleMutation.mutateAsync({
        name: schedName.trim(),
        description: schedDesc.trim() || null,
        cron_expression: finalCron,
        places: finalPlaces,
        image: schedImage.trim() || null,
        power_down: schedPowerDown,
        enabled: true,
      });
      toast({ title: "Schedule created", status: "success" });
      onCloseSched();
      // Reset form
      setSchedName("");
      setSchedDesc("");
      setSchedPreset("0 2 * * *");
      setSchedCron("0 2 * * *");
      setSchedTargetAll(true);
      setSchedPlaces([]);
      setSchedImage("");
    } catch (err: any) {
      toast({ title: "Failed to create schedule", description: err.message, status: "error" });
    }
  };

  const handleToggleSchedule = async (s: HealthCheckSchedule) => {
    try {
      await updateScheduleMutation.mutateAsync({
        id: s.id,
        input: { enabled: !s.enabled },
      });
      toast({
        title: s.enabled ? "Schedule Disabled" : "Schedule Enabled",
        status: "info",
        duration: 2000,
      });
    } catch (err: any) {
      toast({ title: "Failed to update schedule", description: err.message, status: "error" });
    }
  };

  const handleDeleteSchedule = async (id: number) => {
    if (!confirm("Are you sure you want to delete this schedule?")) return;
    try {
      await deleteScheduleMutation.mutateAsync(id);
      toast({ title: "Schedule deleted", status: "info" });
    } catch (err: any) {
      toast({ title: "Failed to delete schedule", description: err.message, status: "error" });
    }
  };

  const handleTriggerScheduleNow = async (id: number) => {
    try {
      const res = await triggerScheduleMutation.mutateAsync(id);
      toast({
        title: "Schedule Triggered",
        description: `Queued ${res.run_ids.length} health check(s).`,
        status: "success",
      });
    } catch (err: any) {
      toast({ title: "Failed to trigger schedule", description: err.message, status: "error" });
    }
  };

  const handleCancelRun = async (runId: number) => {
    try {
      await cancelMutation.mutateAsync(runId);
      toast({ title: "Run Cancelled", status: "info" });
    } catch (err: any) {
      toast({ title: "Failed to cancel run", description: err.message, status: "error" });
    }
  };

  const activeSchedulesCount = schedules.filter((s) => s.enabled).length;

  return (
    <VStack align="stretch" spacing={6} p={{ base: 4, md: 8 }}>
      {/* Header */}
      <Flex justify="space-between" align="center" wrap="wrap" gap={4}>
        <Box>
          <Heading as="h1" size="lg" color="text.primary">
            Board Health
          </Heading>
          <Text fontSize="sm" color="text.secondary">
            Automated boot sanity verification with golden boot files and scheduled fleet checks.
          </Text>
        </Box>
        <HStack spacing={3}>
          <Button
            leftIcon={<Icon as={MdRefresh} />}
            variant="outline"
            size="sm"
            onClick={() => {
              refetchSummary();
              refetchRuns();
            }}
          >
            Refresh
          </Button>
          <Button
            leftIcon={<Icon as={MdPlayArrow} />}
            colorScheme="blue"
            size="sm"
            onClick={handleCheckAll}
            isLoading={triggerMutation.isPending}
          >
            Check All Boards
          </Button>
        </HStack>
      </Flex>

      {/* KPI Cards */}
      <SimpleGrid columns={{ base: 1, sm: 2, lg: 4 }} spacing={4}>
        <MetricCard label="Deployed Boards" value={summaryLoading ? "..." : String(summary?.total_places ?? 0)} />
        <MetricCard
          label="Healthy Boards"
          value={summaryLoading ? "..." : String(summary?.healthy_count ?? 0)}
        />
        <MetricCard
          label="Failing / Busy"
          value={summaryLoading ? "..." : String(summary?.failing_count ?? 0)}
        />
        <MetricCard
          label="Active Schedules"
          value={schedulesLoading ? "..." : String(activeSchedulesCount)}
        />
      </SimpleGrid>

      {/* Main Tabs */}
      <Tabs variant="enclosed" colorScheme="blue">
        <TabList>
          <Tab fontWeight="600">Board Status ({summary?.places?.length ?? 0})</Tab>
          <Tab fontWeight="600">Schedules ({schedules.length})</Tab>
          <Tab fontWeight="600">Run History & Logs ({runs.length})</Tab>
        </TabList>

        <TabPanels>
          {/* TAB 1: BOARD STATUS */}
          <TabPanel px={0} pt={4}>
            <Panel p={0} overflowX="auto">
              {summaryLoading ? (
                <Flex justify="center" p={8}>
                  <Spinner color="blue.500" />
                </Flex>
              ) : !summary || !summary.places || summary.places.length === 0 ? (
                <Box p={8} textAlign="center" color="text.secondary">
                  No deployed boards found on this coordinator.
                </Box>
              ) : (
                <Table variant="simple" size="sm">
                  <Thead bg="blackAlpha.50">
                    <Tr>
                      <Th>Place Name</Th>
                      <Th>Daughter Board</Th>
                      <Th>Carrier</Th>
                      <Th>Strategy</Th>
                      <Th>Golden Boot Image</Th>
                      <Th>Health Status</Th>
                      <Th>Last Checked</Th>
                      <Th>DUT IP</Th>
                      <Th textAlign="right">Actions</Th>
                    </Tr>
                  </Thead>
                  <Tbody>
                    {summary?.places.map((p: BoardHealthPlace) => {
                      const status: HealthStatus = p.last_run ? p.last_run.status : "untested";
                      return (
                        <Tr key={p.name} _hover={{ bg: "whiteAlpha.50" }}>
                          <Td fontWeight="700">{p.name}</Td>
                          <Td>{p.daughter_board || "—"}</Td>
                          <Td>{p.carrier || "—"}</Td>
                          <Td fontSize="xs" color="text.secondary">
                            {p.boot_strategy || "—"}
                          </Td>
                          <Td>
                            <Badge variant="subtle" colorScheme="gray">
                              {p.last_run?.image || p.default_image || "(default)"}
                            </Badge>
                          </Td>
                          <Td>
                            <Badge colorScheme={STATUS_COLOR_SCHEME[status]}>
                              {status.toUpperCase()}
                            </Badge>
                          </Td>
                          <Td fontSize="xs" color="text.secondary">
                            {p.last_run ? `${formatAge(p.last_run.started_at)} ago` : "Never"}
                          </Td>
                          <Td fontSize="xs">
                            {p.last_run?.ip_address ? (
                              <HStack spacing={1}>
                                <Text>{p.last_run.ip_address}</Text>
                                {p.last_run.iiod_reachable && (
                                  <Badge colorScheme="green" fontSize="xx-small">
                                    IIOD
                                  </Badge>
                                )}
                              </HStack>
                            ) : (
                              "—"
                            )}
                          </Td>
                          <Td textAlign="right">
                            <ButtonGroup size="xs" variant="outline">
                              <Button
                                leftIcon={<Icon as={MdPlayArrow} />}
                                onClick={() => handleQuickCheck(p.name)}
                                colorScheme="blue"
                              >
                                Check
                              </Button>
                              {p.last_run && (
                                <IconButton
                                  aria-label="View Log"
                                  icon={<Icon as={MdVisibility} />}
                                  onClick={() => handleOpenLog(p.last_run!.id)}
                                />
                              )}
                            </ButtonGroup>
                          </Td>
                        </Tr>
                      );
                    })}
                  </Tbody>
                </Table>
              )}
            </Panel>
          </TabPanel>

          {/* TAB 2: SCHEDULES */}
          <TabPanel px={0} pt={4}>
            <VStack align="stretch" spacing={4}>
              <Flex justify="space-between" align="center">
                <Text fontSize="sm" color="text.secondary">
                  Configure automated recurring health checks across deployed boards.
                </Text>
                <Button
                  leftIcon={<Icon as={MdAdd} />}
                  colorScheme="blue"
                  size="sm"
                  onClick={onOpenSched}
                >
                  Create Schedule
                </Button>
              </Flex>

              <Panel p={0} overflowX="auto">
                {schedulesLoading ? (
                  <Flex justify="center" p={8}>
                    <Spinner color="blue.500" />
                  </Flex>
                ) : schedules.length === 0 ? (
                  <Box p={8} textAlign="center" color="text.secondary">
                    No recurring schedules created yet. Click "Create Schedule" to set up automated health checks.
                  </Box>
                ) : (
                  <Table variant="simple" size="sm">
                    <Thead bg="blackAlpha.50">
                      <Tr>
                        <Th>Status</Th>
                        <Th>Schedule Name</Th>
                        <Th>Frequency (Cron)</Th>
                        <Th>Target Boards</Th>
                        <Th>Next Run</Th>
                        <Th>Last Run</Th>
                        <Th textAlign="right">Actions</Th>
                      </Tr>
                    </Thead>
                    <Tbody>
                      {schedules.map((s) => (
                        <Tr key={s.id}>
                          <Td>
                            <Switch
                              isChecked={s.enabled}
                              onChange={() => handleToggleSchedule(s)}
                              size="sm"
                              colorScheme="green"
                            />
                          </Td>
                          <Td>
                            <VStack align="start" spacing={0}>
                              <Text fontWeight="600">{s.name}</Text>
                              {s.description && (
                                <Text fontSize="xs" color="text.secondary">
                                  {s.description}
                                </Text>
                              )}
                            </VStack>
                          </Td>
                          <Td>
                            <Badge variant="subtle" colorScheme="purple">
                              {s.cron_expression}
                            </Badge>
                          </Td>
                          <Td>
                            {s.places.includes("*") ? (
                              <Badge colorScheme="blue">All Deployed Boards</Badge>
                            ) : (
                              <Text fontSize="xs">{s.places.join(", ")}</Text>
                            )}
                          </Td>
                          <Td fontSize="xs">
                            {s.next_run_at ? new Date(s.next_run_at * 1000).toLocaleString() : "Disabled"}
                          </Td>
                          <Td fontSize="xs" color="text.secondary">
                            {s.last_run_at ? `${formatAge(s.last_run_at)} ago` : "Never"}
                          </Td>
                          <Td textAlign="right">
                            <ButtonGroup size="xs" variant="ghost">
                              <Tooltip label="Trigger Schedule Now">
                                <IconButton
                                  aria-label="Run Now"
                                  icon={<Icon as={MdPlayArrow} />}
                                  onClick={() => handleTriggerScheduleNow(s.id)}
                                />
                              </Tooltip>
                              <Tooltip label="Delete Schedule">
                                <IconButton
                                  aria-label="Delete"
                                  icon={<Icon as={MdDelete} />}
                                  colorScheme="red"
                                  onClick={() => handleDeleteSchedule(s.id)}
                                />
                              </Tooltip>
                            </ButtonGroup>
                          </Td>
                        </Tr>
                      ))}
                    </Tbody>
                  </Table>
                )}
              </Panel>
            </VStack>
          </TabPanel>

          {/* TAB 3: RUN HISTORY & LOGS */}
          <TabPanel px={0} pt={4}>
            <Panel p={0} overflowX="auto">
              {runsLoading ? (
                <Flex justify="center" p={8}>
                  <Spinner color="blue.500" />
                </Flex>
              ) : runs.length === 0 ? (
                <Box p={8} textAlign="center" color="text.secondary">
                  No health check runs recorded yet.
                </Box>
              ) : (
                <Table variant="simple" size="sm">
                  <Thead bg="blackAlpha.50">
                    <Tr>
                      <Th>Run ID</Th>
                      <Th>Place</Th>
                      <Th>Status</Th>
                      <Th>Trigger</Th>
                      <Th>Duration</Th>
                      <Th>IP Address</Th>
                      <Th>Started At</Th>
                      <Th textAlign="right">Actions</Th>
                    </Tr>
                  </Thead>
                  <Tbody>
                    {runs.map((r) => (
                      <Tr key={r.id} _hover={{ bg: "whiteAlpha.50" }}>
                        <Td fontSize="xs" color="text.secondary">
                          #{r.id}
                        </Td>
                        <Td fontWeight="600">{r.place_name}</Td>
                        <Td>
                          <Badge colorScheme={STATUS_COLOR_SCHEME[r.status]}>
                            {r.status.toUpperCase()}
                          </Badge>
                        </Td>
                        <Td fontSize="xs">
                          <HStack spacing={1}>
                            <Badge variant="outline">{r.trigger}</Badge>
                            {r.triggered_by && (
                              <Text color="text.secondary">by {r.triggered_by}</Text>
                            )}
                          </HStack>
                        </Td>
                        <Td fontSize="xs">
                          {r.duration !== null ? `${r.duration.toFixed(1)}s` : "—"}
                        </Td>
                        <Td fontSize="xs">{r.ip_address || "—"}</Td>
                        <Td fontSize="xs" color="text.secondary">
                          {new Date(r.started_at * 1000).toLocaleString()}
                        </Td>
                        <Td textAlign="right">
                          <ButtonGroup size="xs">
                            <Button
                              variant="outline"
                              leftIcon={<Icon as={MdVisibility} />}
                              onClick={() => handleOpenLog(r.id)}
                            >
                              Log
                            </Button>
                            {r.status === "running" && (
                              <Button
                                variant="ghost"
                                colorScheme="red"
                                leftIcon={<Icon as={MdStop} />}
                                onClick={() => handleCancelRun(r.id)}
                              >
                                Cancel
                              </Button>
                            )}
                          </ButtonGroup>
                        </Td>
                      </Tr>
                    ))}
                  </Tbody>
                </Table>
              )}
            </Panel>
          </TabPanel>
        </TabPanels>
      </Tabs>

      {/* MODAL: Execution Log Viewer */}
      <Modal isOpen={isLogOpen} onClose={onCloseLog} size="4xl" scrollBehavior="inside">
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>
            <HStack spacing={3}>
              <Text>Health Check Run #{selectedRun?.id}</Text>
              {selectedRun && (
                <Badge colorScheme={STATUS_COLOR_SCHEME[selectedRun.status]}>
                  {selectedRun.status.toUpperCase()}
                </Badge>
              )}
            </HStack>
          </ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            {logLoading ? (
              <Flex justify="center" p={8}>
                <Spinner color="blue.500" />
              </Flex>
            ) : selectedRun ? (
              <VStack align="stretch" spacing={4}>
                <SimpleGrid columns={{ base: 2, md: 4 }} spacing={3} bg="blackAlpha.50" p={3} borderRadius="md">
                  <Box>
                    <Text fontSize="xs" color="text.secondary">Place</Text>
                    <Text fontWeight="600">{selectedRun.place_name}</Text>
                  </Box>
                  <Box>
                    <Text fontSize="xs" color="text.secondary">Duration</Text>
                    <Text fontWeight="600">
                      {selectedRun.duration ? `${selectedRun.duration.toFixed(1)}s` : "In progress"}
                    </Text>
                  </Box>
                  <Box>
                    <Text fontSize="xs" color="text.secondary">IP Address</Text>
                    <Text fontWeight="600">{selectedRun.ip_address || "—"}</Text>
                  </Box>
                  <Box>
                    <Text fontSize="xs" color="text.secondary">IIOD Reachable</Text>
                    <Badge colorScheme={selectedRun.iiod_reachable ? "green" : "red"}>
                      {selectedRun.iiod_reachable ? "YES" : "NO"}
                    </Badge>
                  </Box>
                </SimpleGrid>

                {selectedRun.error_message && (
                  <Alert status="error" borderRadius="md" size="sm">
                    <AlertIcon />
                    {selectedRun.error_message}
                  </Alert>
                )}

                <Box>
                  <Text fontSize="xs" fontWeight="700" color="text.secondary" mb={2} textTransform="uppercase">
                    Execution Log
                  </Text>
                  <Box
                    as="pre"
                    p={4}
                    bg="gray.900"
                    color="green.200"
                    fontFamily="mono"
                    fontSize="xs"
                    borderRadius="md"
                    maxH="450px"
                    overflowY="auto"
                    whiteSpace="pre-wrap"
                    wordBreak="break-all"
                  >
                    {selectedRun.log_output || "(No log output recorded yet)"}
                  </Box>
                </Box>
              </VStack>
            ) : null}
          </ModalBody>
          <ModalFooter>
            <Button onClick={onCloseLog}>Close</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* MODAL: Trigger Check Options */}
      <Modal isOpen={isCheckOpen} onClose={onCloseCheck}>
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Run Health Check</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={4} align="stretch">
              <Box>
                <Text fontSize="sm" fontWeight="600">
                  Target Place(s):
                </Text>
                <Text fontSize="sm" color="blue.500">
                  {checkPlaces.join(", ")}
                </Text>
              </Box>

              <FormControl>
                <FormLabel fontSize="sm">Golden Boot Image Version (Optional)</FormLabel>
                <Input
                  placeholder="Leave empty to use catalog default"
                  value={checkImage}
                  onChange={(e) => setCheckImage(e.target.value)}
                  size="sm"
                />
                <FormHelperText fontSize="xs">
                  Defaults to the catalog's assigned golden release (e.g., 2023_R2_P1).
                </FormHelperText>
              </FormControl>

              <Checkbox
                isChecked={checkPowerDown}
                onChange={(e) => setCheckPowerDown(e.target.checked)}
                size="sm"
                colorScheme="blue"
              >
                Power down DUT after health check completes
              </Checkbox>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={onCloseCheck}>
              Cancel
            </Button>
            <Button colorScheme="blue" onClick={handleExecuteCheck} isLoading={triggerMutation.isPending}>
              Start Check
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* MODAL: Create Schedule */}
      <Modal isOpen={isSchedOpen} onClose={onCloseSched} size="lg">
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Create Recurring Health Check Schedule</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={4} align="stretch">
              <FormControl isRequired>
                <FormLabel fontSize="sm">Schedule Name</FormLabel>
                <Input
                  placeholder="e.g. Daily Fleet Health Check"
                  value={schedName}
                  onChange={(e) => setSchedName(e.target.value)}
                  size="sm"
                />
              </FormControl>

              <FormControl>
                <FormLabel fontSize="sm">Description</FormLabel>
                <Input
                  placeholder="Optional brief description"
                  value={schedDesc}
                  onChange={(e) => setSchedDesc(e.target.value)}
                  size="sm"
                />
              </FormControl>

              <FormControl isRequired>
                <FormLabel fontSize="sm">Frequency Preset</FormLabel>
                <Select
                  value={schedPreset}
                  onChange={(e) => {
                    setSchedPreset(e.target.value);
                    if (e.target.value !== "custom") {
                      setSchedCron(e.target.value);
                    }
                  }}
                  size="sm"
                >
                  {CRON_PRESETS.map((p) => (
                    <option key={p.value} value={p.value}>
                      {p.label}
                    </option>
                  ))}
                </Select>
              </FormControl>

              {schedPreset === "custom" && (
                <FormControl isRequired>
                  <FormLabel fontSize="sm">Custom Cron Expression</FormLabel>
                  <Input
                    placeholder="e.g. 0 4 * * *"
                    value={schedCron}
                    onChange={(e) => setSchedCron(e.target.value)}
                    size="sm"
                    fontFamily="mono"
                  />
                  <FormHelperText fontSize="xs">
                    Standard 5-field cron syntax: minute hour day-of-month month day-of-week
                  </FormHelperText>
                </FormControl>
              )}

              <FormControl>
                <FormLabel fontSize="sm">Target Boards</FormLabel>
                <Checkbox
                  isChecked={schedTargetAll}
                  onChange={(e) => setSchedTargetAll(e.target.checked)}
                  size="sm"
                  mb={2}
                >
                  All Deployed Boards (Fleet-wide)
                </Checkbox>

                {!schedTargetAll && summary?.places && (
                  <Box maxH="120px" overflowY="auto" borderWidth="1px" p={2} borderRadius="md">
                    {summary.places.map((p) => (
                      <Checkbox
                        key={p.name}
                        isChecked={schedPlaces.includes(p.name)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setSchedPlaces([...schedPlaces, p.name]);
                          } else {
                            setSchedPlaces(schedPlaces.filter((name) => name !== p.name));
                          }
                        }}
                        size="sm"
                        display="block"
                      >
                        {p.name} ({p.daughter_board})
                      </Checkbox>
                    ))}
                  </Box>
                )}
              </FormControl>

              <FormControl>
                <FormLabel fontSize="sm">Golden Boot Image Override (Optional)</FormLabel>
                <Input
                  placeholder="Leave blank to use catalog golden image"
                  value={schedImage}
                  onChange={(e) => setSchedImage(e.target.value)}
                  size="sm"
                />
              </FormControl>

              <Checkbox
                isChecked={schedPowerDown}
                onChange={(e) => setSchedPowerDown(e.target.checked)}
                size="sm"
              >
                Power down boards after health check finishes
              </Checkbox>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={onCloseSched}>
              Cancel
            </Button>
            <Button
              colorScheme="blue"
              onClick={handleSaveSchedule}
              isLoading={createScheduleMutation.isPending}
            >
              Create Schedule
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </VStack>
  );
}
