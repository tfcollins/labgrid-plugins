import { useParams, Link as RLink, useNavigate } from "react-router-dom";
import { Box, HStack, IconButton, Text, Button } from "@chakra-ui/react";
import { MdArrowBack } from "react-icons/md";
import XTermView from "../components/XTermView";
import { consoleWebSocketUrl } from "../api/console";

export default function Console() {
  const { name = "", resource = "" } = useParams();
  const nav = useNavigate();
  const url = consoleWebSocketUrl(name, resource);
  return (
    <Box h="calc(100vh - 56px)" display="flex" flexDirection="column">
      <HStack p={2} bg="gray.800" color="white">
        <IconButton
          as={RLink} to={`/places/${encodeURIComponent(name)}`}
          aria-label="Back" icon={<MdArrowBack />} size="sm" variant="ghost" colorScheme="whiteAlpha"
        />
        <Text fontSize="sm">{name} / {resource}</Text>
        <HStack spacing={1} ml={4}>
          <Box w="8px" h="8px" borderRadius="full" bg="red.400" />
          <Text fontSize="xs">Recording</Text>
        </HStack>
        <Button ml="auto" size="xs" variant="outline" colorScheme="whiteAlpha" onClick={() => nav(0)}>
          Reconnect
        </Button>
      </HStack>
      <Box flex={1} bg="#1a1a1a" p={2}>
        <XTermView wsUrl={url} />
      </Box>
    </Box>
  );
}
