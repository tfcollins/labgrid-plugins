import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function useResources(params?: {
  exporter?: string;
  cls?: string;
  avail?: boolean;
}) {
  return useQuery({
    queryKey: ["resources", params],
    queryFn: () => api.getResources(params),
  });
}

export function useExporters() {
  return useQuery({
    queryKey: ["exporters"],
    queryFn: api.getExporters,
  });
}
