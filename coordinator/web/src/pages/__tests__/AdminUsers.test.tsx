import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ChakraProvider } from "@chakra-ui/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AdminUsers from "../AdminUsers";

vi.mock("../../api/auth", () => ({
  authApi: {
    listUsers: vi.fn().mockResolvedValue([
      { id: 1, username: "alice", role: "admin", disabled: false, has_password: true, has_oidc: false },
      { id: 2, username: "bob", role: "user", disabled: true, has_password: true, has_oidc: false },
    ]),
    createUser: vi.fn().mockResolvedValue({ id: 3, username: "new", role: "user", disabled: false, has_password: true, has_oidc: false }),
    deleteUser: vi.fn().mockResolvedValue(undefined),
    setPassword: vi.fn().mockResolvedValue(undefined),
    setRole: vi.fn().mockResolvedValue(undefined),
    setDisabled: vi.fn().mockResolvedValue(undefined),
  },
}));

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

describe("AdminUsers", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders the user list", async () => {
    render(wrap(<AdminUsers />));
    expect(await screen.findByText("alice")).toBeInTheDocument();
    expect(screen.getByText("bob")).toBeInTheDocument();
  });

  it("creates a new user", async () => {
    const { authApi } = await import("../../api/auth");
    render(wrap(<AdminUsers />));
    await screen.findByText("alice");
    fireEvent.click(screen.getByRole("button", { name: /add user/i }));
    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: "new" } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "pw" } });
    fireEvent.click(screen.getByRole("button", { name: /^create$/i }));
    await waitFor(() =>
      expect(authApi.createUser).toHaveBeenCalledWith("new", "pw", "user")
    );
  });

  it("deletes a user", async () => {
    const { authApi } = await import("../../api/auth");
    render(wrap(<AdminUsers />));
    await screen.findByText("bob");
    const deleteButtons = screen.getAllByRole("button", { name: /delete/i });
    fireEvent.click(deleteButtons[1]); // bob's row (alice is row 0)
    fireEvent.click(await screen.findByRole("button", { name: /confirm delete/i }));
    await waitFor(() => expect(authApi.deleteUser).toHaveBeenCalledWith(2));
  });
});
