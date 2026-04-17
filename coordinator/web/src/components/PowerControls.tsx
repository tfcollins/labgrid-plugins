import { useEffect, useState } from "react";
import { Badge, Button, HStack, Spinner, useToast } from "@chakra-ui/react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { powerApi, PowerAction } from "../api/power";

interface Props {
  place: string;
  resource: string;
  enabled: boolean;  // owner check from parent
}

export default function PowerControls({ place, resource, enabled }: Props) {
  const toast = useToast();
  const [optimistic, setOptimistic] = useState<"on" | "off" | null>(null);

  const status = useQuery({
    queryKey: ["power-status", place, resource],
    queryFn: () => powerApi.control(place, "get", resource),
    enabled,
    refetchInterval: 5000,
    retry: false,
  });

  // Reset optimistic once a real status arrives.
  useEffect(() => {
    if (status.data?.state) setOptimistic(null);
  }, [status.data?.state]);

  const ctrl = useMutation({
    mutationFn: (action: PowerAction) => powerApi.control(place, action, resource),
    onMutate: (action) => {
      if (action === "on") setOptimistic("on");
      else if (action === "off") setOptimistic("off");
    },
    onSuccess: (_d, action) => {
      toast({ status: "success", title: `power ${action} ok`, duration: 2000 });
      status.refetch();
    },
    onError: (e: unknown) => {
      setOptimistic(null);
      toast({
        status: "error",
        title: "power command failed",
        description: e instanceof Error ? e.message : String(e),
      });
    },
  });

  const state = optimistic ?? status.data?.state ?? null;

  return (
    <HStack spacing={2}>
      {status.isLoading ? (
        <Spinner size="xs" />
      ) : state === "on" ? (
        <Badge colorScheme="green">on</Badge>
      ) : state === "off" ? (
        <Badge colorScheme="gray">off</Badge>
      ) : (
        <Badge colorScheme="yellow">unknown</Badge>
      )}
      <Button
        size="xs"
        colorScheme="green"
        isDisabled={!enabled || ctrl.isPending}
        onClick={() => ctrl.mutate("on")}
      >
        On
      </Button>
      <Button
        size="xs"
        colorScheme="red"
        isDisabled={!enabled || ctrl.isPending}
        onClick={() => ctrl.mutate("off")}
      >
        Off
      </Button>
      <Button
        size="xs"
        isDisabled={!enabled || ctrl.isPending}
        onClick={() => ctrl.mutate("cycle")}
      >
        Cycle
      </Button>
    </HStack>
  );
}
