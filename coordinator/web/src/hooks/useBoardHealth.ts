import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  boardHealthApi,
  type CreateScheduleInput,
  type TriggerRunInput,
  type UpdateScheduleInput,
} from "../api/boardHealth";

export function useBoardHealthSummary() {
  return useQuery({
    queryKey: ["board-health-summary"],
    queryFn: () => boardHealthApi.getSummary(),
    refetchInterval: 10_000,
  });
}

export function useBoardHealthRuns(filters: { place?: string; status?: string; limit?: number; offset?: number } = {}) {
  return useQuery({
    queryKey: ["board-health-runs", filters],
    queryFn: () => boardHealthApi.listRuns(filters),
    refetchInterval: 10_000,
  });
}

export function useBoardHealthRun(runId: number | null) {
  return useQuery({
    queryKey: ["board-health-run", runId],
    queryFn: () => (runId !== null ? boardHealthApi.getRun(runId) : null),
    enabled: runId !== null,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data && (data.status === "pending" || data.status === "running")) {
        return 3_000;
      }
      return false;
    },
  });
}

export function useBoardHealthSchedules() {
  return useQuery({
    queryKey: ["board-health-schedules"],
    queryFn: () => boardHealthApi.listSchedules(),
    refetchInterval: 15_000,
  });
}

export function useTriggerHealthCheck() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: TriggerRunInput) => boardHealthApi.triggerRuns(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["board-health-summary"] });
      queryClient.invalidateQueries({ queryKey: ["board-health-runs"] });
    },
  });
}

export function useCancelHealthCheck() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (runId: number) => boardHealthApi.cancelRun(runId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["board-health-summary"] });
      queryClient.invalidateQueries({ queryKey: ["board-health-runs"] });
      queryClient.invalidateQueries({ queryKey: ["board-health-run"] });
    },
  });
}

export function useCreateSchedule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateScheduleInput) => boardHealthApi.createSchedule(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["board-health-schedules"] });
      queryClient.invalidateQueries({ queryKey: ["board-health-summary"] });
    },
  });
}

export function useUpdateSchedule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: UpdateScheduleInput }) =>
      boardHealthApi.updateSchedule(id, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["board-health-schedules"] });
      queryClient.invalidateQueries({ queryKey: ["board-health-summary"] });
    },
  });
}

export function useDeleteSchedule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => boardHealthApi.deleteSchedule(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["board-health-schedules"] });
      queryClient.invalidateQueries({ queryKey: ["board-health-summary"] });
    },
  });
}

export function useTriggerSchedule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => boardHealthApi.triggerSchedule(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["board-health-schedules"] });
      queryClient.invalidateQueries({ queryKey: ["board-health-summary"] });
      queryClient.invalidateQueries({ queryKey: ["board-health-runs"] });
    },
  });
}
