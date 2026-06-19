import { Link as RouterLink } from "react-router-dom";
import {
  Box,
  Heading,
  Text,
  Code,
  VStack,
  Divider,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Badge,
  useColorModeValue,
  ListItem,
  OrderedList,
  UnorderedList,
  Stack,
  Link,
  Button,
} from "@chakra-ui/react";
import ConceptGlanceCard from "../components/ConceptGlanceCard";
import { resetTermsSeen } from "../components/Term";

function CodeBlock({ children }: { children: string }) {
  const bg = useColorModeValue("gray.800", "gray.900");
  return (
    <Box
      as="pre"
      bg={bg}
      color="gray.100"
      p={4}
      borderRadius="md"
      fontSize="sm"
      overflowX="auto"
      my={3}
    >
      <code>{children}</code>
    </Box>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Box mb={8}>
      <Heading size="md" mb={3} color="text.primary">
        {title}
      </Heading>
      {children}
    </Box>
  );
}

export default function Help() {
  const cardBg = useColorModeValue("white", "gray.800");

  return (
    <Box maxW="800px">
      <Heading size="lg" mb={4}>Help</Heading>

      <Stack spacing={4} mb={6}>
        <Heading size="md">How labgrid concepts fit together</Heading>
        <ConceptGlanceCard />
        <Text>
          An <b>exporter</b> is a lab host. It publishes hardware — serial ports, SD muxes,
          power outlets, FPGA JTAG adapters — to the coordinator as individual <b>resources</b>.
          A <b>place</b> is a user-defined bundle: it has one or more <b>match rules</b>
          (patterns like <code>bq/tlab/*</code>) that pull specific resources from exporters.
        </Text>
        <Text>
          When you want to use a place, you <b>acquire</b> it. That takes an exclusive lock:
          nobody else can drive its resources until you <b>release</b>. Acquisition is
          per-user and survives browser reloads — if you close your tab while holding a
          place, you're still holding it.
        </Text>
        <Text>
          Want to see the relationships live?{" "}
          <Link as={RouterLink} to="/topology" color="link">Open Topology</Link>.
        </Text>
        <Box>
          <Button size="sm" variant="outline" onClick={resetTermsSeen}>
            Reset concept tooltips
          </Button>
          <Text fontSize="xs" color="gray.500" mt={1}>
            Clears the "you've seen this term" flags. Every underlined term will pop its
            tooltip again on first hover.
          </Text>
        </Box>
      </Stack>

      <Divider mb={6} />

      <Heading size="md" mb={4}>Guide to adding exporters, configuring resources, and setting up places</Heading>

      <Box bg={cardBg} borderRadius="lg" p={6} shadow="sm">
        <VStack align="stretch" spacing={0}>
          <Section title="1. Create an Exporter Config">
            <Text mb={3}>
              Each exporter needs a YAML file defining its resource groups. Use
              the naming convention{" "}
              <Code colorScheme="adi">{"<BOARD>_<CHIP>"}</Code> for group names:
            </Text>

            <CodeBlock>{`## resources.yaml
ZCU102_AD9081:
  NetworkService:
    cls: NetworkService
    address: "10.0.0.23"
    username: "root"
  RawSerialPort:
    cls: RawSerialPort
    port: "/dev/ttyUSB0"
    speed: 115200
  USBSDMuxDevice:
    cls: USBSDMuxDevice`}</CodeBlock>

            <Text fontSize="sm" color="text.secondary">
              Every resource must have a <Code fontSize="xs">cls</Code> field
              matching its labgrid resource class. Use{" "}
              <Code fontSize="xs">##</Code> for comments (single{" "}
              <Code fontSize="xs">#</Code> is reserved for Jinja2 statements).
            </Text>
          </Section>

          <Divider />

          <Section title="2. Available Resource Classes">
            <Table variant="simple" size="sm">
              <Thead>
                <Tr>
                  <Th>Class</Th>
                  <Th>Purpose</Th>
                  <Th>Key Params</Th>
                </Tr>
              </Thead>
              <Tbody>
                <Tr>
                  <Td>
                    <Badge colorScheme="adi">NetworkService</Badge>
                  </Td>
                  <Td>Network/SSH access</Td>
                  <Td>
                    <Code fontSize="xs">address, username, password</Code>
                  </Td>
                </Tr>
                <Tr>
                  <Td>
                    <Badge colorScheme="adi">RawSerialPort</Badge>
                  </Td>
                  <Td>Serial console</Td>
                  <Td>
                    <Code fontSize="xs">port, speed</Code>
                  </Td>
                </Tr>
                <Tr>
                  <Td>
                    <Badge colorScheme="adi">XilinxDeviceJTAG</Badge>
                  </Td>
                  <Td>FPGA JTAG programming</Td>
                  <Td>
                    <Code fontSize="xs">
                      root_target, microblaze_target, bitstream_path,
                      kernel_path
                    </Code>
                  </Td>
                </Tr>
                <Tr>
                  <Td>
                    <Badge colorScheme="adi">XilinxVivadoTool</Badge>
                  </Td>
                  <Td>Vivado tool path</Td>
                  <Td>
                    <Code fontSize="xs">vivado_path</Code>
                  </Td>
                </Tr>
                <Tr>
                  <Td>
                    <Badge colorScheme="adi">USBMassStorage</Badge>
                  </Td>
                  <Td>USB storage device</Td>
                  <Td>
                    <Code fontSize="xs">match (udev filters)</Code>
                  </Td>
                </Tr>
                <Tr>
                  <Td>
                    <Badge colorScheme="adi">USBSDMuxDevice</Badge>
                  </Td>
                  <Td>USB SD Mux</Td>
                  <Td>
                    <Code fontSize="xs">match (udev filters)</Code>
                  </Td>
                </Tr>
                <Tr>
                  <Td>
                    <Badge colorScheme="adi">MassStorageDevice</Badge>
                  </Td>
                  <Td>Block device partition</Td>
                  <Td>
                    <Code fontSize="xs">path</Code>
                  </Td>
                </Tr>
                <Tr>
                  <Td>
                    <Badge colorScheme="adi">VesyncOutlet</Badge>
                  </Td>
                  <Td>VeSync smart outlet</Td>
                  <Td>
                    <Code fontSize="xs">outlet_names, username, password</Code>
                  </Td>
                </Tr>
                <Tr>
                  <Td>
                    <Badge colorScheme="adi">CyberPowerOutlet</Badge>
                  </Td>
                  <Td>CyberPower PDU</Td>
                  <Td>
                    <Code fontSize="xs">address, outlet</Code>
                  </Td>
                </Tr>
                <Tr>
                  <Td>
                    <Badge colorScheme="adi">HomeAssistantOutlet</Badge>
                  </Td>
                  <Td>Home Assistant switch</Td>
                  <Td>
                    <Code fontSize="xs">url, token, entity_id</Code>
                  </Td>
                </Tr>
                <Tr>
                  <Td>
                    <Badge colorScheme="adi">KuiperRelease</Badge>
                  </Td>
                  <Td>ADI Kuiper Linux image</Td>
                  <Td>
                    <Code fontSize="xs">
                      release_version, cache_path, kernel_path
                    </Code>
                  </Td>
                </Tr>
                <Tr>
                  <Td>
                    <Badge colorScheme="adi">TFTPServerResource</Badge>
                  </Td>
                  <Td>TFTP boot server</Td>
                  <Td>
                    <Code fontSize="xs">root_dir</Code>
                  </Td>
                </Tr>
              </Tbody>
            </Table>
          </Section>

          <Divider />

          <Section title="3. Validate the Config">
            <Text mb={2}>
              Before deploying, validate the config against the schema:
            </Text>
            <CodeBlock>python exporter_configs/validate.py resources.yaml</CodeBlock>
          </Section>

          <Divider />

          <Section title="4. Start the Exporter">
            <Text mb={2}>
              Install the plugins on the exporter host and start the exporter,
              pointing it at the coordinator:
            </Text>
            <CodeBlock>{`## Install
pip install -e ".[dev]"

## Start exporter (name must be unique)
labgrid-exporter \\
    -c <coordinator-host>:20408 \\
    -n my-lab-host \\
    resources.yaml`}</CodeBlock>
            <Text fontSize="sm" color="text.secondary">
              The exporter name (<Code fontSize="xs">-n</Code>) must be unique
              across all exporters. It defaults to the system hostname.
            </Text>
          </Section>

          <Divider />

          <Section title="5. Create a Place">
            <Text mb={2}>
              Once the exporter registers its resources, create a place and add
              match patterns to bind resources to it:
            </Text>
            <OrderedList spacing={2} mb={3}>
              <ListItem>
                Go to the <strong>Places</strong> page and click{" "}
                <strong>Create Place</strong>
              </ListItem>
              <ListItem>
                Name it following the convention{" "}
                <Code fontSize="xs">{"<board>-<location>"}</Code> (e.g.,{" "}
                <Code fontSize="xs">vcu118-lab1</Code>)
              </ListItem>
              <ListItem>
                Add a match pattern to bind the exporter's resources to the
                place
              </ListItem>
              <ListItem>
                Set tags for filtering (e.g.,{" "}
                <Code fontSize="xs">board=vcu118</Code>)
              </ListItem>
            </OrderedList>

            <Text mb={2}>Or via the REST API / CLI:</Text>
            <CodeBlock>{`## REST API
curl -X POST http://localhost:8000/api/places \\
    -H "Content-Type: application/json" \\
    -d '{"name":"vcu118-lab1"}'

curl -X POST http://localhost:8000/api/places/vcu118-lab1/matches \\
    -H "Content-Type: application/json" \\
    -d '{"pattern":"my-lab-host/VCU118_AD9081/*"}'

## labgrid-client
labgrid-client -x <coordinator>:20408 create vcu118-lab1
labgrid-client -x <coordinator>:20408 -p vcu118-lab1 \\
    add-match "my-lab-host/VCU118_AD9081/*"`}</CodeBlock>
          </Section>

          <Divider />

          <Section title="6. Group Naming Convention">
            <Text mb={3}>
              Use consistent group names across all exporters so match patterns
              work reliably:
            </Text>
            <Table variant="simple" size="sm">
              <Thead>
                <Tr>
                  <Th>Board</Th>
                  <Th>Chip</Th>
                  <Th>Group Name</Th>
                </Tr>
              </Thead>
              <Tbody>
                <Tr>
                  <Td>VCU118</Td>
                  <Td>AD9081</Td>
                  <Td>
                    <Code>VCU118_AD9081</Code>
                  </Td>
                </Tr>
                <Tr>
                  <Td>VCU118</Td>
                  <Td>AD9084</Td>
                  <Td>
                    <Code>VCU118_AD9084</Code>
                  </Td>
                </Tr>
                <Tr>
                  <Td>ZCU102</Td>
                  <Td>AD9081</Td>
                  <Td>
                    <Code>ZCU102_AD9081</Code>
                  </Td>
                </Tr>
                <Tr>
                  <Td>Raspberry Pi CM4</Td>
                  <Td>(none)</Td>
                  <Td>
                    <Code>RPI_CM4</Code>
                  </Td>
                </Tr>
              </Tbody>
            </Table>
            <Text fontSize="sm" color="text.secondary" mt={2}>
              This enables wildcard match patterns like{" "}
              <Code fontSize="xs">*/VCU118_AD9081/*</Code> that work regardless
              of which exporter host the board is connected to.
            </Text>
          </Section>

          <Divider />

          <Section title="Templates">
            <Text mb={2}>
              Pre-built exporter templates are available in{" "}
              <Code fontSize="xs">exporter_configs/templates/</Code>:
            </Text>
            <UnorderedList spacing={1}>
              <ListItem>
                <Code fontSize="xs">vcu118_ad9081.yaml</Code> — VCU118 with
                AD9081 transceiver
              </ListItem>
              <ListItem>
                <Code fontSize="xs">zcu102.yaml</Code> — ZCU102 SoC
              </ListItem>
              <ListItem>
                <Code fontSize="xs">rpi.yaml</Code> — Raspberry Pi
              </ListItem>
            </UnorderedList>
            <Text fontSize="sm" color="text.secondary" mt={2}>
              These use Jinja2 variables for host-specific values. Fill them in
              and use directly with <Code fontSize="xs">labgrid-exporter</Code>.
            </Text>
          </Section>
        </VStack>
      </Box>
    </Box>
  );
}
