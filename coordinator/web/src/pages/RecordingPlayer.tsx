import { useEffect, useRef } from "react";
import { useParams, Link as RLink } from "react-router-dom";
import { Box, Heading, HStack, IconButton } from "@chakra-ui/react";
import { MdArrowBack } from "react-icons/md";
import * as AsciinemaPlayer from "asciinema-player";
import "asciinema-player/dist/bundle/asciinema-player.css";
import { recordingsApi } from "../api/recordings";

export default function RecordingPlayer() {
  const { id = "" } = useParams();
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const player = AsciinemaPlayer.create(
      recordingsApi.castUrl(id),
      containerRef.current,
      { fit: "width", theme: "dracula" }
    );
    return () => {
      try { player.dispose(); } catch { /* ignore */ }
    };
  }, [id]);

  return (
    <Box p={4}>
      <HStack mb={4}>
        <IconButton as={RLink} to="/recordings" aria-label="Back"
          icon={<MdArrowBack />} size="sm" variant="ghost" />
        <Heading size="md">Recording {id}</Heading>
      </HStack>
      <Box ref={containerRef} />
    </Box>
  );
}
