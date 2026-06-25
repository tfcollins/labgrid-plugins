import { Box } from "@chakra-ui/react";
import { keyframes } from "@emotion/react";
import { type PlaceStatus, STATUS_TOKEN } from "./status";

const pulse = keyframes`
  0% { box-shadow: 0 0 0 0 var(--dot-glow); }
  70% { box-shadow: 0 0 0 4px transparent; }
  100% { box-shadow: 0 0 0 0 transparent; }
`;

/** Small status LED. Pulses subtly for live states (free/acquired). */
export default function StatusDot({ status, size = 8 }: { status: PlaceStatus; size?: number }) {
  const token = STATUS_TOKEN[status];
  const animate = status === "free" || status === "acquired";
  return (
    <Box
      data-testid="status-dot"
      data-status={status}
      w={`${size}px`}
      h={`${size}px`}
      borderRadius="full"
      bg={token}
      sx={{ "--dot-glow": "currentColor" }}
      color={token}
      animation={animate ? `${pulse} 3.4s ease-in-out infinite` : undefined}
      flexShrink={0}
    />
  );
}
