import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function useStatsOverview() {
  return useQuery({
    queryKey: ["stats", "overview"],
    queryFn: api.getStatsOverview,
    refetchInterval: 30000,
  });
}

export function usePlaceStats(days = 30) {
  return useQuery({
    queryKey: ["stats", "places", days],
    queryFn: () => api.getPlaceStats(days),
  });
}

export function useResourceStats(days = 30) {
  return useQuery({
    queryKey: ["stats", "resources", days],
    queryFn: () => api.getResourceStats(days),
  });
}

export function useExporterStats(days = 30) {
  return useQuery({
    queryKey: ["stats", "exporters", days],
    queryFn: () => api.getExporterStats(days),
  });
}

export function useEvents(params?: {
  limit?: number;
  offset?: number;
  event_type?: string;
  place_name?: string;
}) {
  return useQuery({
    queryKey: ["events", params],
    queryFn: () => api.getEvents(params),
  });
}
