import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

export function useReservations() {
  return useQuery({
    queryKey: ["reservations"],
    queryFn: api.getReservations,
  });
}

export function useCreateReservation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      filters,
      prio,
    }: {
      filters: Record<string, Record<string, string>>;
      prio?: number;
    }) => api.createReservation(filters, prio),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["reservations"] }),
  });
}

export function useCancelReservation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (token: string) => api.cancelReservation(token),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["reservations"] }),
  });
}

export function useReservationsLive() {
  return useQuery({
    queryKey: ["reservations"],
    queryFn: api.getReservations,
    refetchInterval: 5000,
  });
}

/** Manual "refresh now" nudge for a single reservation token. Intentionally
 * unused today — consumers rely on `useReservationsLive`'s 5s refetch. Kept
 * available for a future UI action (e.g. a "poll" icon button next to a row). */
export function usePollReservation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (token: string) => api.pollReservation(token),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["reservations"] }),
  });
}
