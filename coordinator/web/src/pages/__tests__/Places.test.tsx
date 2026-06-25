// src/pages/__tests__/Places.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ChakraProvider } from "@chakra-ui/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import theme from "../../theme";
import Places from "../Places";

vi.mock("../../api/ws", () => ({ useWebSocket: () => {} }));
vi.mock("../../hooks/usePlaces", () => ({
  usePlaces: () => ({
    isLoading: false,
    data: [
      { name: "p-free", tags: {}, matches: [], acquired: null, aliases: [], comment: "", acquired_resources: [] },
      { name: "p-held", tags: {}, matches: [], acquired: "travis", aliases: [], comment: "", acquired_resources: [] },
    ],
  }),
  useDeletePlace: () => ({ mutate: vi.fn() }),
  useAcquirePlace: () => ({ mutateAsync: vi.fn() }),
  useReleasePlace: () => ({ mutateAsync: vi.fn() }),
}));
vi.mock("../../hooks/useRelationships", () => ({
  useRelationships: () => ({
    placeToExporters: new Map([["p-free", [{ name: "exp1", online: true }]], ["p-held", [{ name: "exp1", online: true }]]]),
    placeToMissingMatches: new Map(),
    placeHealth: new Map([["p-free", "ready"], ["p-held", "held"]]),
  }),
}));

const wrap = (ui: React.ReactNode) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <ChakraProvider theme={theme}>
      <QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>
    </ChakraProvider>
  );
};

describe("Places", () => {
  beforeEach(() => localStorage.clear());
  it("renders status pills with the expected labels", () => {
    render(wrap(<Places />));
    expect(screen.getByText("ready")).toBeInTheDocument();
    expect(screen.getByText("held")).toBeInTheDocument();
  });
  it("renders the spec-sheet table foot summary", () => {
    render(wrap(<Places />));
    expect(screen.getByText(/2 of 2 · 1 free · 1 acquired/)).toBeInTheDocument();
  });
});
