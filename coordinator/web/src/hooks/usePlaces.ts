import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

export function usePlaces() {
  return useQuery({
    queryKey: ["places"],
    queryFn: api.getPlaces,
  });
}

export function usePlace(name: string) {
  return useQuery({
    queryKey: ["places", name],
    queryFn: () => api.getPlace(name),
    enabled: !!name,
  });
}

export function useCreatePlace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => api.createPlace(name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["places"] }),
  });
}

export function useDeletePlace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => api.deletePlace(name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["places"] }),
  });
}

export function useAcquirePlace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => api.acquirePlace(name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["places"] }),
  });
}

export function useReleasePlace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => api.releasePlace(name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["places"] }),
  });
}
