import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ChakraProvider } from "@chakra-ui/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import NetBoxSection from "../NetBoxSection";
import { netboxApi, type NetBoxDevice } from "../../api/netbox";

vi.mock("../../api/netbox", () => ({ netboxApi: { getPlace: vi.fn() } }));

const wrap = (ui: React.ReactNode) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <ChakraProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter>{ui}</MemoryRouter>
      </QueryClientProvider>
    </ChakraProvider>
  );
};

const device: NetBoxDevice = {
  id: 42,
  name: "tron",
  display: "tron",
  url: "https://netbox.example/dcim/devices/42/",
  status: "active",
  site: "US-Home",
  location: "Lab Bench",
  rack: "Bench-Rack-1",
  rack_url: "https://netbox.example/dcim/racks/10/",
  position: 12,
  face: "front",
  device_type: "ADRV9009-ZU11EG",
  manufacturer: "Analog Devices",
  role: "labgrid-target",
  primary_ip: "10.0.1.243/24",
  comments: null,
  power_connections: [
    { port_name: "Power 1", connected_device: "pdu-1", connected_outlet: "Outlet 3" },
  ],
  console_connections: [
    { port_name: "Console", connected_device: null, connected_port: null },
  ],
};

describe("NetBoxSection", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows the matched device with links into NetBox", async () => {
    vi.mocked(netboxApi.getPlace).mockResolvedValue({ configured: true, matched: true, device });
    render(wrap(<NetBoxSection place="tron" />));

    const link = await screen.findByRole("link", { name: /tron/ });
    expect(link).toHaveAttribute("href", device.url);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
    expect(screen.getByRole("link", { name: "Bench-Rack-1" })).toHaveAttribute(
      "href",
      device.rack_url,
    );
    expect(screen.getByText("active")).toBeInTheDocument();
    expect(screen.getByText("US-Home / Lab Bench")).toBeInTheDocument();
    expect(screen.getByText(/U12 · front/)).toBeInTheDocument();
    expect(screen.getByText("Analog Devices ADRV9009-ZU11EG")).toBeInTheDocument();
    expect(screen.getByText("10.0.1.243/24")).toBeInTheDocument();
    expect(screen.getByText("Power 1 → pdu-1 / Outlet 3")).toBeInTheDocument();
    expect(screen.getByText("Console → not cabled")).toBeInTheDocument();
    expect(netboxApi.getPlace).toHaveBeenCalledWith("tron");
  });

  it("says when no device has the place's name", async () => {
    vi.mocked(netboxApi.getPlace).mockResolvedValue({
      configured: true,
      matched: false,
      device: null,
    });
    render(wrap(<NetBoxSection place="tron" />));

    expect(await screen.findByText("NetBox")).toBeInTheDocument();
    expect(screen.getByText(/No single NetBox device is named/)).toBeInTheDocument();
  });

  it("renders nothing when NetBox isn't configured", async () => {
    vi.mocked(netboxApi.getPlace).mockResolvedValue({
      configured: false,
      matched: false,
      device: null,
    });
    const { container } = render(wrap(<NetBoxSection place="tron" />));

    await waitFor(() => expect(netboxApi.getPlace).toHaveBeenCalled());
    expect(screen.queryByText("NetBox")).not.toBeInTheDocument();
    expect(container.textContent).toBe("");
  });

  it("renders nothing when the lookup fails", async () => {
    vi.mocked(netboxApi.getPlace).mockRejectedValue(new Error("500: boom"));
    const { container } = render(wrap(<NetBoxSection place="tron" />));

    await waitFor(() => expect(netboxApi.getPlace).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });
});
