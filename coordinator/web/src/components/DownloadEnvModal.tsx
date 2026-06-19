import { useEffect, useMemo, useState } from "react";
import {
  Badge, Box, Button, HStack, IconButton, Modal, ModalBody, ModalCloseButton,
  ModalContent, ModalFooter, ModalHeader, ModalOverlay, Radio, RadioGroup,
  Spinner, Stack, Text, useToast,
} from "@chakra-ui/react";
import { MdContentCopy } from "react-icons/md";
import { inferStrategy } from "../lib/inferStrategy";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  placeName: string;
  resourceClasses: Set<string>;
}

const TIERS = [
  { value: "boot", label: "Full boot", desc: "All drivers + inferred strategy." },
  { value: "drivers", label: "All drivers", desc: "One driver per resource. No boot strategy." },
  { value: "shell", label: "Shell only", desc: "Serial console + shell login. Minimal." },
];

export default function DownloadEnvModal({ isOpen, onClose, placeName, resourceClasses }: Props) {
  const [tier, setTier] = useState("boot");
  const [preview, setPreview] = useState<string>("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const toast = useToast();

  const strategy = useMemo(() => inferStrategy(resourceClasses), [resourceClasses]);
  const showBadge = tier === "boot";

  const url = `/api/places/${encodeURIComponent(placeName)}/env-yaml?tier=${tier}`;

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    setPreviewLoading(true);
    setPreviewError(null);
    fetch(url)
      .then(async (res) => {
        if (!res.ok) throw new Error(`Server returned ${res.status}`);
        return res.text();
      })
      .then((text) => {
        if (cancelled) return;
        setPreview(text);
      })
      .catch((e) => {
        if (cancelled) return;
        setPreview("");
        setPreviewError(e instanceof Error ? e.message : "Failed to load preview");
      })
      .finally(() => {
        if (cancelled) return;
        setPreviewLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, url]);

  const handleDownload = () => {
    window.open(url, "_blank");
  };

  const handleCopy = async () => {
    if (preview) {
      try {
        await navigator.clipboard.writeText(preview);
        toast({ status: "success", title: "Copied to clipboard", duration: 2000 });
        return;
      } catch (e) {
        toast({ status: "error", title: e instanceof Error ? e.message : "Copy failed", duration: 3000 });
        return;
      }
    }
    try {
      const res = await fetch(url);
      if (!res.ok) {
        toast({ status: "error", title: `Server returned ${res.status}`, duration: 3000 });
        return;
      }
      const text = await res.text();
      await navigator.clipboard.writeText(text);
      toast({ status: "success", title: "Copied to clipboard", duration: 2000 });
    } catch (e) {
      toast({ status: "error", title: e instanceof Error ? e.message : "Copy failed", duration: 3000 });
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="xl">
      <ModalOverlay />
      <ModalContent>
        <ModalHeader>Download env yaml</ModalHeader>
        <ModalCloseButton />
        <ModalBody>
          <RadioGroup value={tier} onChange={setTier}>
            <Stack spacing={3}>
              {TIERS.map((t) => (
                <Box key={t.value}>
                  <Radio value={t.value}>
                    <Text fontWeight={500}>{t.label}</Text>
                  </Radio>
                  <Text fontSize="xs" color="gray.500" ml={6}>{t.desc}</Text>
                </Box>
              ))}
            </Stack>
          </RadioGroup>

          {showBadge && (
            <Box mt={4}>
              {strategy ? (
                <Badge colorScheme="green">Strategy: {strategy}</Badge>
              ) : (
                <Badge colorScheme="gray">No strategy inferred</Badge>
              )}
            </Box>
          )}

          <Box mt={4}>
            <Text fontSize="sm" fontWeight={500} mb={1}>Preview</Text>
            <Box
              borderWidth="1px"
              borderRadius="md"
              bg="gray.50"
              _dark={{ bg: "gray.900" }}
              maxH="360px"
              overflow="auto"
              p={3}
              fontFamily="mono"
              fontSize="xs"
            >
              {previewLoading ? (
                <HStack spacing={2} color="gray.500">
                  <Spinner size="xs" />
                  <Text>Loading preview…</Text>
                </HStack>
              ) : previewError ? (
                <Text color="red.500" data-testid="preview-error">{previewError}</Text>
              ) : (
                <Box
                  as="pre"
                  whiteSpace="pre"
                  m={0}
                  data-testid="preview-content"
                >{preview}</Box>
              )}
            </Box>
          </Box>
        </ModalBody>
        <ModalFooter>
          <HStack spacing={2}>
            <IconButton
              aria-label="Copy yaml to clipboard"
              icon={<MdContentCopy />}
              size="sm"
              variant="outline"
              onClick={handleCopy}
            />
            <Button onClick={handleDownload}>
              Download {placeName}.yaml
            </Button>
          </HStack>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}
