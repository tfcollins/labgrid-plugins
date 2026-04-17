import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ChakraProvider } from "@chakra-ui/react";
import Login from "../Login";
import { AuthProvider } from "../../auth/AuthContext";

vi.mock("../../api/auth", () => ({
  authApi: {
    me: vi.fn().mockRejectedValue(new Error("401")),
    login: vi.fn().mockResolvedValue({ username: "alice", role: "user" }),
    logout: vi.fn(),
    oidcLoginUrl: () => "/api/auth/oidc/login",
  },
}));

const wrap = (ui: React.ReactNode) => (
  <ChakraProvider>
    <MemoryRouter>
      <AuthProvider>{ui}</AuthProvider>
    </MemoryRouter>
  </ChakraProvider>
);

describe("Login", () => {
  beforeEach(() => vi.clearAllMocks());

  it("submits username and password", async () => {
    const { authApi } = await import("../../api/auth");
    render(wrap(<Login />));
    fireEvent.change(await screen.findByLabelText(/username/i), {
      target: { value: "alice" },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: "pw" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(authApi.login).toHaveBeenCalledWith("alice", "pw"));
  });

  it("shows error on failed login", async () => {
    const { authApi } = await import("../../api/auth");
    (authApi.login as any).mockRejectedValueOnce(new Error("401: invalid credentials"));
    render(wrap(<Login />));
    fireEvent.change(await screen.findByLabelText(/username/i), { target: { value: "x" } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "y" } });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText(/invalid credentials/i)).toBeInTheDocument();
  });
});
