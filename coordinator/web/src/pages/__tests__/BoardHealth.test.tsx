import { fireEvent, render, screen } from "@testing-library/react";
import { ChakraProvider } from "@chakra-ui/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import BoardHealth from "../BoardHealth";
import { boardHealthApi } from "../../api/boardHealth";
import theme from "../../theme";

vi.mock("../../api/boardHealth", () => ({
  boardHealthApi: {
    getSummary: vi.fn(),
    listSchedules: vi.fn(),
    listRuns: vi.fn(),
    getRun: vi.fn(),
    triggerRuns: vi.fn(),
    cancelRun: vi.fn(),
    createSchedule: vi.fn(),
    updateSchedule: vi.fn(),
    deleteSchedule: vi.fn(),
    triggerSchedule: vi.fn(),
  },
}));

const mockSummary = {
  total_places: 2,
  healthy_count: 1,
  failing_count: 0,
  untested_count: 1,
  running_count: 0,
  places: [
    {
      name: "mini2",
      daughter_board: "adrv9002",
      carrier: "zcu102",
      boot_strategy: "BootFPGASoC",
      acquired: null,
      default_image: "2023_R2_P1",
      last_run: {
        id: 101,
        status: "passed" as const,
        started_at: Date.now() / 1000 - 300,
        finished_at: Date.now() / 1000 - 250,
        duration: 50.0,
        boot_strategy: "BootFPGASoC",
        image: "2023_R2_P1",
        ip_address: "192.168.1.100",
        iiod_reachable: true,
        error_message: null,
        trigger: "manual" as const,
        triggered_by: "analog",
      },
    },
    {
      name: "tron",
      daughter_board: "adrv9009zu11eg",
      carrier: "adrv2crr-fmc",
      boot_strategy: "BootZynqMPJTAG",
      acquired: null,
      default_image: "2023_R2_P1",
      last_run: null,
    },
  ],
};

const mockSchedules = [
  {
    id: 1,
    name: "Nightly Sanity",
    description: "Daily golden boot",
    cron_expression: "0 2 * * *",
    places: ["*"],
    image: null,
    power_down: true,
    enabled: true,
    created_at: 1729000000,
    updated_at: 1729000000,
    last_run_at: null,
    next_run_at: 1729050000,
  },
];

const mockRuns = [
  {
    id: 101,
    place_name: "mini2",
    status: "passed" as const,
    started_at: Date.now() / 1000 - 300,
    finished_at: Date.now() / 1000 - 250,
    duration: 50.0,
    boot_strategy: "BootFPGASoC",
    image: "2023_R2_P1",
    ip_address: "192.168.1.100",
    iiod_reachable: true,
    error_message: null,
    trigger: "manual" as const,
    triggered_by: "analog",
  },
];

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <ChakraProvider theme={theme}>
      <QueryClientProvider client={queryClient}>
        <BoardHealth />
      </QueryClientProvider>
    </ChakraProvider>,
  );
}

describe("BoardHealth", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(boardHealthApi.getSummary).mockResolvedValue(mockSummary);
    vi.mocked(boardHealthApi.listSchedules).mockResolvedValue(mockSchedules);
    vi.mocked(boardHealthApi.listRuns).mockResolvedValue(mockRuns);
    vi.mocked(boardHealthApi.getRun).mockResolvedValue({
      ...mockRuns[0],
      log_output: "Booting target...\nVerified iiod on port 30431\nSuccess!",
    });
  });

  it("renders page header and KPI metrics", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "Board Health" })).toBeInTheDocument();
    expect(screen.getByText("Deployed Boards")).toBeInTheDocument();
    expect(screen.getByText("Healthy Boards")).toBeInTheDocument();
  });

  it("renders deployed boards table with status pills", async () => {
    renderPage();

    const mini2Elements = await screen.findAllByText("mini2");
    expect(mini2Elements.length).toBeGreaterThan(0);
    expect(screen.getByText("tron")).toBeInTheDocument();
    expect(screen.getAllByText("PASSED").length).toBeGreaterThan(0);
    expect(screen.getByText("UNTESTED")).toBeInTheDocument();
    expect(screen.getAllByText("192.168.1.100").length).toBeGreaterThan(0);
  });

  it("opens manual check modal when Check button is clicked", async () => {
    renderPage();

    const checkButtons = await screen.findAllByRole("button", { name: /^Check$/i });
    fireEvent.click(checkButtons[0]);

    expect(await screen.findByText("Run Health Check")).toBeInTheDocument();
    const mini2Elements = screen.getAllByText("mini2");
    expect(mini2Elements.length).toBeGreaterThan(0);
  });

  it("switches to Schedules tab and displays schedules", async () => {
    renderPage();

    const schedulesTab = await screen.findByRole("tab", { name: /Schedules/i });
    fireEvent.click(schedulesTab);

    expect(await screen.findByText("Nightly Sanity")).toBeInTheDocument();
    expect(screen.getByText("0 2 * * *")).toBeInTheDocument();
    expect(screen.getByText("All Deployed Boards")).toBeInTheDocument();
  });

  it("switches to Run History tab and views log modal", async () => {
    renderPage();

    const historyTab = await screen.findByRole("tab", { name: /Run History & Logs/i });
    fireEvent.click(historyTab);

    expect(await screen.findByText("#101")).toBeInTheDocument();

    const logButton = screen.getByRole("button", { name: /Log/i });
    fireEvent.click(logButton);

    expect(await screen.findByText("Health Check Run #101")).toBeInTheDocument();
    expect(await screen.findByText(/Verified iiod on port 30431/i)).toBeInTheDocument();
  });
});
