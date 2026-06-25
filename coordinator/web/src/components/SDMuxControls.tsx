import { useEffect, useState } from "react";
import { Badge, Button, HStack, Spinner, useToast } from "@chakra-ui/react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { sdmuxApi, SDMuxAction, SDMuxMode } from "../api/sdmux";

interface Props {
  place: string;
  resource: string;
  enabled: boolean;
}

const ACTIONS: { label: string; value: Exclude<SDMuxAction, "get"> }[] = [
  { label: "Host", value: "host" },
  { label: "DUT", value: "dut" },
  { label: "Off", value: "off" },
];

const MODE_COLORS: Record<string, string> = {
  host: "adi",
  dut: "purple",
  off: "gray",
  client: "teal",
};

export default function SDMuxControls({ place, resource, enabled }: Props) {
  const toast = useToast();
  const [optimistic, setOptimistic] = useState<SDMuxMode>(null);

  const status = useQuery({
    queryKey: ["sdmux-status", place, resource],
    queryFn: () => sdmuxApi.control(place, "get", resource),
    enabled,
    refetchInterval: 5000,
    retry: false,
  });

  useEffect(() => {
    if (status.data?.mode) setOptimistic(null);
  }, [status.data?.mode]);

  const ctrl = useMutation({
    mutationFn: (action: SDMuxAction) => sdmuxApi.control(place, action, resource),
    onMutate: (action) => {
      if (action !== "get") setOptimistic(action);
    },
    onSuccess: (_d, action) => {
      toast({ status: "success", title: `sd-mux ${action} ok`, duration: 2000 });
      status.refetch();
    },
    onError: (e: unknown) => {
      setOptimistic(null);
      toast({
        status: "error",
        title: "sd-mux command failed",
        description: e instanceof Error ? e.message : String(e),
      });
    },
  });

  const mode = optimistic ?? status.data?.mode ?? null;

  return (
    <HStack spacing={2}>
      {status.isLoading ? (
        <Spinner size="xs" />
      ) : mode ? (
        <Badge colorScheme={MODE_COLORS[mode] ?? "gray"}>{mode}</Badge>
      ) : (
        <Badge colorScheme="yellow">unknown</Badge>
      )}
      {ACTIONS.map((a) => (
        <Button
          key={a.value}
          size="xs"
          variant={mode === a.value ? "solid" : "outline"}
          colorScheme={MODE_COLORS[a.value]}
          isDisabled={!enabled || ctrl.isPending}
          onClick={() => ctrl.mutate(a.value)}
        >
          {a.label}
        </Button>
      ))}
    </HStack>
  );
}
