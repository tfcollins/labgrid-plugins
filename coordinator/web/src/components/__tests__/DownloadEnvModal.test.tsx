import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ChakraProvider } from "@chakra-ui/react";
import DownloadEnvModal from "../DownloadEnvModal";

const wrap = (ui: React.ReactNode) => <ChakraProvider>{ui}</ChakraProvider>;

const SOC_CLASSES = new Set([
  "NetworkSerialPort", "VesyncOutlet", "NetworkUSBSDMuxDevice",
  "NetworkUSBMassStorage", "KuiperRelease",
]);
const SERIAL_CLASSES = new Set(["NetworkSerialPort"]);

function mockFetchYaml(body: string) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input: RequestInfo | URL) => {
    const reqUrl =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.toString()
          : input.url;
    const tier = new URL(reqUrl, "http://localhost").searchParams.get("tier") ?? "unknown";
    return new Response(`# tier=${tier}\n${body}`, { status: 200 });
  });
}

describe("DownloadEnvModal", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockFetchYaml("targets:\n  main:\n    drivers: []\n");
  });

  it("renders three tier radio options when open", () => {
    render(wrap(
      <DownloadEnvModal isOpen onClose={() => {}} placeName="test" resourceClasses={SOC_CLASSES} />
    ));
    expect(screen.getByLabelText(/shell only/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/all drivers/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/full boot/i)).toBeInTheDocument();
  });

  it("defaults to full boot tier", () => {
    render(wrap(
      <DownloadEnvModal isOpen onClose={() => {}} placeName="test" resourceClasses={SOC_CLASSES} />
    ));
    expect(screen.getByLabelText(/full boot/i)).toBeChecked();
  });

  it("shows inferred strategy badge for SoC resources", () => {
    render(wrap(
      <DownloadEnvModal isOpen onClose={() => {}} placeName="test" resourceClasses={SOC_CLASSES} />
    ));
    expect(screen.getByText(/BootFPGASoC/)).toBeInTheDocument();
  });

  it("shows 'no strategy' badge for serial-only resources", () => {
    render(wrap(
      <DownloadEnvModal isOpen onClose={() => {}} placeName="test" resourceClasses={SERIAL_CLASSES} />
    ));
    expect(screen.getByText(/no strategy inferred/i)).toBeInTheDocument();
  });

  it("download button includes the selected tier in the URL", () => {
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
    render(wrap(
      <DownloadEnvModal isOpen onClose={() => {}} placeName="myplace" resourceClasses={SOC_CLASSES} />
    ));
    fireEvent.click(screen.getByRole("button", { name: /download/i }));
    expect(openSpy).toHaveBeenCalledWith(
      expect.stringContaining("/api/places/myplace/env-yaml?tier=boot"),
      "_blank",
    );
  });

  it("renders yaml preview fetched from the server", async () => {
    render(wrap(
      <DownloadEnvModal isOpen onClose={() => {}} placeName="myplace" resourceClasses={SOC_CLASSES} />
    ));
    const preview = await screen.findByTestId("preview-content");
    expect(preview.textContent).toContain("tier=boot");
    expect(preview.textContent).toContain("targets:");
  });

  it("refetches preview when tier changes", async () => {
    render(wrap(
      <DownloadEnvModal isOpen onClose={() => {}} placeName="myplace" resourceClasses={SOC_CLASSES} />
    ));
    const preview = await screen.findByTestId("preview-content");
    await waitFor(() => expect(preview.textContent).toContain("tier=boot"));

    fireEvent.click(screen.getByLabelText(/shell only/i));
    await waitFor(() => expect(
      screen.getByTestId("preview-content").textContent,
    ).toContain("tier=shell"));
  });

  it("shows preview error when fetch fails", async () => {
    vi.restoreAllMocks();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("bad", { status: 500 }));
    render(wrap(
      <DownloadEnvModal isOpen onClose={() => {}} placeName="myplace" resourceClasses={SOC_CLASSES} />
    ));
    const err = await screen.findByTestId("preview-error");
    expect(err.textContent).toMatch(/500/);
  });
});
