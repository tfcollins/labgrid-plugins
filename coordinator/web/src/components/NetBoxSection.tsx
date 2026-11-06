import { Badge, Code, Grid, HStack, Icon, Link, Stack, Text } from "@chakra-ui/react";
import { useQuery } from "@tanstack/react-query";
import { MdOpenInNew } from "react-icons/md";
import { netboxApi, type NetBoxDevice } from "../api/netbox";
import RelatedPanel from "./RelatedPanel";

const STATUS_COLORS: Record<string, string> = {
  active: "green",
  planned: "blue",
  staged: "blue",
  failed: "red",
  offline: "red",
  decommissioning: "orange",
};

/** "pdu-1 / Outlet 3", or "not cabled" when NetBox has no cable on the port. */
function peer(device: string | null, port: string | null): string {
  if (!device && !port) return "not cabled";
  return [device, port].filter(Boolean).join(" / ");
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <Text color="text.secondary">{label}</Text>
      <Text as="div" overflowWrap="anywhere">{children}</Text>
    </>
  );
}

function DeviceDetails({ device }: { device: NetBoxDevice }) {
  const where = [device.site, device.location].filter(Boolean).join(" / ");
  const slot = [device.position != null ? `U${device.position}` : null, device.face]
    .filter(Boolean)
    .join(" · ");
  const model = [device.manufacturer, device.device_type].filter(Boolean).join(" ");

  return (
    <Stack spacing={2}>
      <HStack spacing={2}>
        <Link href={device.url} isExternal color="link" fontWeight={500}>
          {device.display || device.name} <Icon as={MdOpenInNew} mx="1px" verticalAlign="-2px" />
        </Link>
        {device.status && (
          <Badge colorScheme={STATUS_COLORS[device.status] ?? "gray"}>{device.status}</Badge>
        )}
      </HStack>
      <Grid templateColumns="auto 1fr" columnGap={3} rowGap={1}>
        {where && <Row label="Site">{where}</Row>}
        {device.rack && (
          <Row label="Rack">
            {device.rack_url ? (
              <Link href={device.rack_url} isExternal color="link">{device.rack}</Link>
            ) : (
              device.rack
            )}
            {slot && <Text as="span" color="text.secondary"> {slot}</Text>}
          </Row>
        )}
        {model && <Row label="Type">{model}</Row>}
        {device.role && <Row label="Role">{device.role}</Row>}
        {device.primary_ip && <Row label="IP"><Code fontSize="xs">{device.primary_ip}</Code></Row>}
        {device.power_connections.map((p) => (
          <Row key={`power-${p.port_name}`} label="Power">
            {p.port_name} → {peer(p.connected_device, p.connected_outlet)}
          </Row>
        ))}
        {device.console_connections.map((c) => (
          <Row key={`console-${c.port_name}`} label="Console">
            {c.port_name} → {peer(c.connected_device, c.connected_port)}
          </Row>
        ))}
      </Grid>
      {device.comments && (
        <Text color="text.secondary" fontSize="xs" whiteSpace="pre-wrap">{device.comments}</Text>
      )}
    </Stack>
  );
}

/** The place's NetBox device, as a RelatedPanel section. Renders nothing until
 * loaded, if the API request fails, or when the API has no NetBox configured;
 * says so when the API couldn't ask NetBox. */
export default function NetBoxSection({ place }: { place: string }) {
  const { data } = useQuery({
    queryKey: ["place-netbox", place],
    queryFn: () => netboxApi.getPlace(place),
    staleTime: 60_000,
    retry: false,
    enabled: !!place,
  });

  if (!data?.configured) return null;

  return (
    <RelatedPanel.Section title="NetBox">
      {data.matched && data.device ? (
        <DeviceDetails device={data.device} />
      ) : data.error ? (
        <Stack spacing={1}>
          <Text color="text.secondary">NetBox lookup failed.</Text>
          <Text color="text.secondary" fontSize="xs" maxW="xs">{data.error}</Text>
        </Stack>
      ) : (
        <Text color="text.secondary">
          No single NetBox device is named <Code fontSize="xs">{place}</Code>.
        </Text>
      )}
    </RelatedPanel.Section>
  );
}
