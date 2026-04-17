import { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { Spinner, Center } from "@chakra-ui/react";
import { useAuth } from "./AuthContext";

export default function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) {
    return (
      <Center h="50vh">
        <Spinner />
      </Center>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  }
  return <>{children}</>;
}
