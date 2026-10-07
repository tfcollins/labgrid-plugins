import { Fragment, useState, type ReactNode } from "react";
import {
  Alert,
  AlertIcon,
  Badge,
  Box,
  Collapse,
  HStack,
  IconButton,
  Progress,
  SimpleGrid,
  Spinner,
  Table,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
  VStack,
} from "@chakra-ui/react";
import { MdExpandLess, MdExpandMore } from "react-icons/md";
import type {
  DeploymentStatus,
  DeploymentSummary,
} from "../api/deployments";
import ConceptHeading from "../components/ConceptHeading";
import Panel from "../components/ui/Panel";
import { useDeployment, useDeployments } from "../hooks/useDeployments";

const STATUS_COLORS: Record<DeploymentStatus, string> = {
  pending: "gray",
  in_progress: "blue",
  succeeded: "green",
  failed: "red",
  cancelled: "orange",
  offline: "gray",
};

function formatStatus(status: DeploymentStatus) {
  return status.replace(/_/g, " ");
}

function formatTimestamp(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function Value({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Box>
      <Text
        fontSize="xs"
        color="text.secondary"
        fontWeight="600"
        textTransform="uppercase"
      >
        {label}
      </Text>
      <Text fontSize="sm">{children}</Text>
    </Box>
  );
}

function DeploymentDetails({ hostname }: { hostname: string }) {
  const { data, isLoading, error } = useDeployment(hostname);

  if (isLoading) return <Spinner size="sm" color="adi.500" />;
  if (error) {
    return (
      <Alert status="error" size="sm">
        <AlertIcon />
        Could not load deployment details: {error.message}
      </Alert>
    );
  }
  if (!data) return null;

  return (
    <VStack align="stretch" spacing={5}>
      <SimpleGrid columns={{ base: 2, lg: 4 }} spacing={4}>
        <Value label="First seen">{formatTimestamp(data.first_seen)}</Value>
        <Value label="Last seen">{formatTimestamp(data.last_seen)}</Value>
        <Value label="IP addresses">{data.ip_addresses.join(", ") || "—"}</Value>
        <Value label="MAC addresses">{data.mac_addresses.join(", ") || "—"}</Value>
      </SimpleGrid>

      <Box>
        <Text fontSize="sm" fontWeight="700" mb={2}>
          Errors
        </Text>
        {data.errors.length === 0 ? (
          <Text fontSize="sm" color="text.secondary">
            No errors reported.
          </Text>
        ) : (
          <VStack align="stretch" spacing={1}>
            {data.errors.map((message, index) => (
              <Text key={`${index}-${message}`} fontSize="sm" color="red.500">
                {message}
              </Text>
            ))}
          </VStack>
        )}
      </Box>

      <Box>
        <Text fontSize="sm" fontWeight="700" mb={2}>
          Timeline
        </Text>
        {data.timeline.length === 0 ? (
          <Text fontSize="sm" color="text.secondary">
            No timeline events reported.
          </Text>
        ) : (
          <VStack align="stretch" spacing={0}>
            {data.timeline.map((event, index) => (
              <HStack
                key={`${event.timestamp}-${index}`}
                align="start"
                spacing={3}
                py={2}
                borderTopWidth={index === 0 ? "0" : "1px"}
                borderColor="border.hairline"
              >
                <Text
                  minW="170px"
                  fontSize="xs"
                  color="text.secondary"
                  fontFamily="mono"
                >
                  {formatTimestamp(event.timestamp)}
                </Text>
                <Badge colorScheme={STATUS_COLORS[event.status]}>
                  {formatStatus(event.status)}
                </Badge>
                <Text minW="100px" fontSize="sm" fontWeight="600">
                  {event.stage}
                </Text>
                <Text flex="1" fontSize="sm">
                  {event.message}
                </Text>
                <Text minW="42px" textAlign="right" fontSize="xs">
                  {event.progress == null ? "—" : `${event.progress}%`}
                </Text>
              </HStack>
            ))}
          </VStack>
        )}
      </Box>
    </VStack>
  );
}

function DeploymentRow({ deployment }: { deployment: DeploymentSummary }) {
  const [expanded, setExpanded] = useState(false);
  const errorText = deployment.errors[deployment.errors.length - 1];

  return (
    <Fragment>
      <Tr>
        <Td>
          <HStack spacing={1}>
            <IconButton
              aria-label={`${expanded ? "Hide" : "Show"} details for ${deployment.hostname}`}
              aria-expanded={expanded}
              aria-controls={`deployment-details-${deployment.hostname}`}
              icon={expanded ? <MdExpandLess /> : <MdExpandMore />}
              onClick={() => setExpanded((value) => !value)}
              size="xs"
              variant="ghost"
            />
            <Text fontWeight="600">{deployment.hostname}</Text>
          </HStack>
        </Td>
        <Td fontFamily="mono" whiteSpace="nowrap">
          {deployment.attempt}
        </Td>
        <Td>{deployment.stage}</Td>
        <Td>
          <Badge colorScheme={STATUS_COLORS[deployment.status]}>
            {formatStatus(deployment.status)}
          </Badge>
        </Td>
        <Td minW="130px">
          <HStack spacing={2}>
            <Progress
              aria-label={`${deployment.hostname} deployment progress`}
              value={deployment.progress}
              colorScheme={STATUS_COLORS[deployment.status]}
              size="sm"
              flex="1"
              borderRadius="sm"
            />
            <Text fontSize="xs" minW="34px">
              {deployment.progress}%
            </Text>
          </HStack>
        </Td>
        <Td whiteSpace="nowrap">{deployment.ip_addresses.join(", ") || "—"}</Td>
        <Td fontFamily="mono" whiteSpace="nowrap">
          {deployment.mac_addresses.join(", ") || "—"}
        </Td>
        <Td whiteSpace="nowrap">{formatTimestamp(deployment.first_seen)}</Td>
        <Td whiteSpace="nowrap">{formatTimestamp(deployment.last_seen)}</Td>
        <Td maxW="240px">
          <Text color={errorText ? "red.500" : "text.secondary"} noOfLines={2}>
            {errorText ?? "—"}
          </Text>
        </Td>
      </Tr>
      <Tr>
        <Td colSpan={10} p={0} borderBottomWidth={expanded ? "1px" : "0"}>
          <Collapse in={expanded} animateOpacity>
            <Box
              id={`deployment-details-${deployment.hostname}`}
              px={6}
              py={4}
              bg="surface.subtle"
            >
              {expanded && <DeploymentDetails hostname={deployment.hostname} />}
            </Box>
          </Collapse>
        </Td>
      </Tr>
    </Fragment>
  );
}

export default function Deployments() {
  const { data: deployments = [], isLoading, error } = useDeployments();

  if (isLoading) return <Spinner size="xl" color="adi.500" />;

  return (
    <Box>
      <ConceptHeading
        name="deployment"
        pageKey="/deployments"
        headingText="Node deployments"
      />

      {error && (
        <Alert status="error" mb={4}>
          <AlertIcon />
          Could not load node deployments: {error.message}
        </Alert>
      )}

      <Panel overflowX="auto">
        <Table variant="simple" size="sm">
          <Thead>
            <Tr>
              <Th>Hostname</Th>
              <Th>Attempt</Th>
              <Th>Stage</Th>
              <Th>Status</Th>
              <Th>Progress</Th>
              <Th>IP</Th>
              <Th>MAC</Th>
              <Th>First seen</Th>
              <Th>Last seen</Th>
              <Th>Latest error</Th>
            </Tr>
          </Thead>
          <Tbody>
            {deployments.map((deployment) => (
              <DeploymentRow key={deployment.hostname} deployment={deployment} />
            ))}
            {!error && deployments.length === 0 && (
              <Tr>
                <Td colSpan={10} textAlign="center" color="text.secondary" py={8}>
                  No node deployments have been reported.
                </Td>
              </Tr>
            )}
          </Tbody>
        </Table>
      </Panel>
    </Box>
  );
}
