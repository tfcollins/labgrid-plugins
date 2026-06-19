import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { ChakraProvider } from "@chakra-ui/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import PlaceWizard from "../PlaceWizard";

const navMock = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => navMock };
});

vi.mock("../../api/client", () => ({
  api: {
    getPlaces: vi.fn().mockResolvedValue([
      { name: "existing", aliases: [], comment: "", tags: {}, matches: [],
        acquired: null, acquired_resources: [], allowed: [], created: 0, changed: 0,
        reservation: null, acquired_username: null },
    ]),
    getResources: vi.fn().mockResolvedValue([
      { exporter: "exp1", group: "grpA", cls: "NetworkSerialPort", name: "n1",
        params: {}, acquired: null, avail: true },
      { exporter: "exp1", group: "grpA", cls: "VesyncOutlet", name: "n2",
        params: {}, acquired: null, avail: true },
      { exporter: "exp2", group: "grpB", cls: "NetworkPowerPort", name: "n3",
        params: {}, acquired: null, avail: true },
    ]),
    createPlace: vi.fn().mockResolvedValue(undefined),
    addPlaceMatch: vi.fn().mockResolvedValue(undefined),
    setPlaceTags: vi.fn().mockResolvedValue(undefined),
    setPlaceComment: vi.fn().mockResolvedValue(undefined),
    deletePlace: vi.fn().mockResolvedValue(undefined),
  },
}));

const wrap = (ui: React.ReactNode) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <ChakraProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/places/new"]}>
          <Routes>
            <Route path="/places/new" element={ui} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </ChakraProvider>
  );
};

describe("PlaceWizard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    navMock.mockReset();
  });

  it("disables Next when name is empty", async () => {
    render(wrap(<PlaceWizard />));
    const next = await screen.findByRole("button", { name: /^next$/i });
    expect(next).toBeDisabled();
  });

  it("blocks Next on duplicate name", async () => {
    render(wrap(<PlaceWizard />));
    const input = await screen.findByLabelText(/place name/i);
    fireEvent.change(input, { target: { value: "existing" } });
    expect(await screen.findByText(/already exists/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^next$/i })).toBeDisabled();
  });

  it("walks through all steps and submits in order", async () => {
    const { api } = await import("../../api/client");
    render(wrap(<PlaceWizard />));

    // Step 1: name
    fireEvent.change(await screen.findByLabelText(/place name/i), {
      target: { value: "fresh-place" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^next$/i }));

    // Step 2: pick the first group
    const cb = await screen.findByRole("checkbox", { name: /select group exp1\/grpA/i });
    fireEvent.click(cb);
    fireEvent.click(screen.getByRole("button", { name: /^next$/i }));

    // Step 3: fill the three required tags
    fireEvent.change(await screen.findByLabelText(/board-location/i), { target: { value: "Munich" } });
    fireEvent.change(screen.getByLabelText(/^carrier/i), { target: { value: "vcu118" } });
    fireEvent.change(screen.getByLabelText(/daughter-board/i), { target: { value: "fmcomms2" } });
    fireEvent.click(screen.getByRole("button", { name: /^next$/i }));

    // Step 4: review + create
    fireEvent.click(await screen.findByRole("button", { name: /create place/i }));

    await waitFor(() => expect(api.createPlace).toHaveBeenCalledWith("fresh-place"));
    await waitFor(() =>
      expect(api.addPlaceMatch).toHaveBeenCalledWith("fresh-place", "exp1/grpA/*")
    );
    await waitFor(() =>
      expect(api.setPlaceTags).toHaveBeenCalledWith("fresh-place", {
        "board-location": "Munich",
        carrier: "vcu118",
        "daughter-board": "fmcomms2",
      })
    );
    expect(api.setPlaceComment).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(navMock).toHaveBeenCalledWith("/places/fresh-place")
    );
  });

  it("blocks Next on step 3 until all required tags are filled", async () => {
    render(wrap(<PlaceWizard />));

    fireEvent.change(await screen.findByLabelText(/place name/i), {
      target: { value: "req-tags" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^next$/i }));

    const cb = await screen.findByRole("checkbox", { name: /select group exp1\/grpA/i });
    fireEvent.click(cb);
    fireEvent.click(screen.getByRole("button", { name: /^next$/i }));

    // On step 3 with no required tags filled, Next is disabled
    const next = await screen.findByRole("button", { name: /^next$/i });
    expect(next).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/board-location/i), { target: { value: "Cluj" } });
    expect(next).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/^carrier/i), { target: { value: "zcu102" } });
    expect(next).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/daughter-board/i), { target: { value: "ad9084" } });
    await waitFor(() => expect(next).toBeEnabled());
  });

  it("submits tags and comment when provided, skips them otherwise", async () => {
    const { api } = await import("../../api/client");
    render(wrap(<PlaceWizard />));

    fireEvent.change(await screen.findByLabelText(/place name/i), {
      target: { value: "tagged" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^next$/i }));

    const cb = await screen.findByRole("checkbox", { name: /select group exp2\/grpB/i });
    fireEvent.click(cb);
    fireEvent.click(screen.getByRole("button", { name: /^next$/i }));

    // Step 3: required tags + one extra + comment
    fireEvent.change(await screen.findByLabelText(/board-location/i), { target: { value: "RTP" } });
    fireEvent.change(screen.getByLabelText(/^carrier/i), { target: { value: "vcu118" } });
    fireEvent.change(screen.getByLabelText(/daughter-board/i), { target: { value: "adis16460" } });
    fireEvent.click(await screen.findByRole("button", { name: /add tag/i }));
    fireEvent.change(await screen.findByLabelText(/tag 0 key/i), { target: { value: "note" } });
    fireEvent.change(screen.getByLabelText(/tag 0 value/i), { target: { value: "demo" } });
    fireEvent.change(screen.getByLabelText(/comment/i), { target: { value: "demo" } });
    fireEvent.click(screen.getByRole("button", { name: /^next$/i }));

    // Step 4
    fireEvent.click(await screen.findByRole("button", { name: /create place/i }));

    await waitFor(() => expect(api.createPlace).toHaveBeenCalledWith("tagged"));
    await waitFor(() =>
      expect(api.setPlaceTags).toHaveBeenCalledWith("tagged", {
        "board-location": "RTP",
        carrier: "vcu118",
        "daughter-board": "adis16460",
        note: "demo",
      })
    );
    await waitFor(() =>
      expect(api.setPlaceComment).toHaveBeenCalledWith("tagged", "demo")
    );
  });

  it("rolls back when an addPlaceMatch fails", async () => {
    const { api } = await import("../../api/client");
    (api.addPlaceMatch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("boom"));
    render(wrap(<PlaceWizard />));

    fireEvent.change(await screen.findByLabelText(/place name/i), {
      target: { value: "rollback-test" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^next$/i }));

    const cb = await screen.findByRole("checkbox", { name: /select group exp1\/grpA/i });
    fireEvent.click(cb);
    fireEvent.click(screen.getByRole("button", { name: /^next$/i }));

    // Fill required tags so we can advance past step 3
    fireEvent.change(await screen.findByLabelText(/board-location/i), { target: { value: "Wilm" } });
    fireEvent.change(screen.getByLabelText(/^carrier/i), { target: { value: "rpi4" } });
    fireEvent.change(screen.getByLabelText(/daughter-board/i), { target: { value: "fmcomms2" } });
    fireEvent.click(await screen.findByRole("button", { name: /^next$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /create place/i }));

    await waitFor(() =>
      expect(api.deletePlace).toHaveBeenCalledWith("rollback-test")
    );
    expect(navMock).not.toHaveBeenCalled();
  });
});
