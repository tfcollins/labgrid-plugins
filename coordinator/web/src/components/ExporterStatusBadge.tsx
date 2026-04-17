import { Badge } from "@chakra-ui/react";
import type { Resource } from "../api/client";

interface Props {
  resources: Resource[];
}

export default function ExporterStatusBadge({ resources }: Props) {
  if (resources.length === 0) {
    return <Badge colorScheme="gray">No resources</Badge>;
  }

  const availCount = resources.filter((r) => r.avail).length;
  const total = resources.length;

  if (availCount === total) {
    return <Badge colorScheme="green">All available</Badge>;
  }
  if (availCount === 0) {
    return <Badge colorScheme="red">Unavailable</Badge>;
  }
  return (
    <Badge colorScheme="yellow">
      {availCount}/{total} available
    </Badge>
  );
}
