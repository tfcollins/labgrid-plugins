import { useQuery } from "@tanstack/react-query";
import { deploymentsApi } from "../api/deployments";

export function useDeployments() {
  return useQuery({
    queryKey: ["deployments"],
    queryFn: deploymentsApi.list,
    refetchInterval: 10_000,
  });
}

export function useDeployment(hostname: string, enabled = true) {
  return useQuery({
    queryKey: ["deployments", hostname],
    queryFn: () => deploymentsApi.get(hostname),
    enabled: enabled && hostname.length > 0,
    refetchInterval: 10_000,
  });
}
