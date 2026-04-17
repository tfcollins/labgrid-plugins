import { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { Spinner, Center } from "@chakra-ui/react";
import { useAuth } from "./AuthContext";

export default function RequireAdmin({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <Center h="50vh">
        <Spinner />
      </Center>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== "admin") return <Navigate to="/" replace />;
  return <>{children}</>;
}
