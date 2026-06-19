import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box, Button, Checkbox, FormControl, FormErrorMessage, FormLabel,
  HStack, Heading, IconButton, Input, Select, Spinner, Stack, Step,
  StepIcon, StepIndicator, StepNumber, StepSeparator, StepStatus,
  StepTitle, Stepper, Tag, TagLabel, Text, Textarea,
  useSteps, useToast,
} from "@chakra-ui/react";
import { MdAdd, MdDelete } from "react-icons/md";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

interface PickedGroup {
  exporter: string;
  group: string;
  // "*" means all classes; otherwise a specific class name from the group.
  cls: string;
  // The classes available in this exporter/group, for the per-row Select.
  classOptions: string[];
}

interface TagRow {
  key: string;
  value: string;
}

const STEPS = [
  { title: "Name", description: "Choose a name" },
  { title: "Resources", description: "Pick what to attach" },
  { title: "Tags & comment", description: "Required + optional metadata" },
  { title: "Review", description: "Confirm and create" },
];

const PLACE_NAME_RE = /^[A-Za-z0-9_.-]+$/;

const BOARD_LOCATIONS = [
  "Munich", "Cluj", "GT", "RTP", "Wilm", "Chelm", "US-Home",
] as const;

const REQUIRED_TAG_KEYS = ["board-location", "carrier", "daughter-board"] as const;

export default function PlaceWizard() {
  const nav = useNavigate();
  const toast = useToast();
  const { activeStep, setActiveStep } = useSteps({
    index: 0, count: STEPS.length,
  });

  const places = useQuery({ queryKey: ["places"], queryFn: api.getPlaces });
  const resources = useQuery({ queryKey: ["resources"], queryFn: () => api.getResources() });

  const [name, setName] = useState("");
  const [picked, setPicked] = useState<PickedGroup[]>([]);
  const [boardLocation, setBoardLocation] = useState("");
  const [carrier, setCarrier] = useState("");
  const [daughterBoard, setDaughterBoard] = useState("");
  const [tags, setTags] = useState<TagRow[]>([]);
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const subtleBg = "surface.subtle";

  // ---------- derived data ----------

  const existingNames = useMemo(
    () => new Set((places.data ?? []).map((p) => p.name)),
    [places.data]
  );

  const nameError = useMemo(() => {
    const t = name.trim();
    if (!t) return "";
    if (!PLACE_NAME_RE.test(t))
      return "Use letters, digits, '.', '_' or '-' only.";
    if (existingNames.has(t)) return `A place named "${t}" already exists.`;
    return "";
  }, [name, existingNames]);

  const groups = useMemo(() => {
    const map = new Map<string, { exporter: string; group: string; classes: Set<string> }>();
    for (const r of resources.data ?? []) {
      const k = `${r.exporter}/${r.group}`;
      if (!map.has(k)) {
        map.set(k, { exporter: r.exporter, group: r.group, classes: new Set() });
      }
      map.get(k)!.classes.add(r.cls);
    }
    return Array.from(map.values())
      .map((g) => ({ ...g, classes: Array.from(g.classes).sort() }))
      .sort((a, b) =>
        a.exporter === b.exporter ? a.group.localeCompare(b.group) : a.exporter.localeCompare(b.exporter)
      );
  }, [resources.data]);

  const isPicked = (exporter: string, group: string) =>
    picked.some((p) => p.exporter === exporter && p.group === group);

  const togglePick = (exporter: string, group: string, classOptions: string[]) => {
    setPicked((cur) => {
      if (cur.some((p) => p.exporter === exporter && p.group === group)) {
        return cur.filter((p) => !(p.exporter === exporter && p.group === group));
      }
      return [...cur, { exporter, group, cls: "*", classOptions }];
    });
  };

  const setPickedClass = (exporter: string, group: string, cls: string) => {
    setPicked((cur) =>
      cur.map((p) =>
        p.exporter === exporter && p.group === group ? { ...p, cls } : p
      )
    );
  };

  // ---------- step validation ----------

  const requiredTagsComplete =
    boardLocation.trim() !== "" && carrier.trim() !== "" && daughterBoard.trim() !== "";

  const customTagCollidesWithRequired = tags.some((t) =>
    (REQUIRED_TAG_KEYS as readonly string[]).includes(t.key.trim())
  );

  const stepValid = (i: number): boolean => {
    if (i === 0) return name.trim().length > 0 && !nameError;
    if (i === 1) return picked.length > 0;
    if (i === 2) {
      if (!requiredTagsComplete) return false;
      if (customTagCollidesWithRequired) return false;
      // tags must have non-empty key when key OR value is set
      return tags.every((t) => (t.key === "" && t.value === "") || t.key !== "");
    }
    return true;
  };

  const canNext = stepValid(activeStep);
  const canBack = activeStep > 0 && !submitting;

  // ---------- commit ----------

  const submit = async () => {
    setSubmitting(true);
    const placeName = name.trim();
    const tagsObj: Record<string, string> = {
      "board-location": boardLocation.trim(),
      carrier: carrier.trim(),
      "daughter-board": daughterBoard.trim(),
      ...Object.fromEntries(
        tags.filter((t) => t.key.trim() !== "").map((t) => [t.key.trim(), t.value])
      ),
    };
    const trimmedComment = comment.trim();

    try {
      await api.createPlace(placeName);
    } catch (e) {
      setSubmitting(false);
      toast({ status: "error", title: "Failed to create place",
        description: e instanceof Error ? e.message : String(e) });
      return;
    }

    const rollback = async (failedAt: string, err: unknown) => {
      try { await api.deletePlace(placeName); } catch { /* ignore */ }
      setSubmitting(false);
      toast({
        status: "error",
        title: `Failed at ${failedAt}; rolled back`,
        description: err instanceof Error ? err.message : String(err),
        duration: 5000,
      });
    };

    try {
      for (const p of picked) {
        await api.addPlaceMatch(placeName, `${p.exporter}/${p.group}/${p.cls}`);
      }
    } catch (e) {
      return rollback("add resource match", e);
    }

    try { await api.setPlaceTags(placeName, tagsObj); }
    catch (e) { return rollback("set tags", e); }
    if (trimmedComment) {
      try { await api.setPlaceComment(placeName, trimmedComment); }
      catch (e) { return rollback("set comment", e); }
    }

    toast({ status: "success", title: `Place "${placeName}" created`, duration: 2000 });
    nav(`/places/${encodeURIComponent(placeName)}`);
  };

  // ---------- render ----------

  if (places.isLoading || resources.isLoading) return <Spinner />;

  return (
    <Box maxW="900px" mx="auto">
      <Heading size="lg" mb={6}>New place</Heading>

      <Stepper index={activeStep} mb={8} colorScheme="adi">
        {STEPS.map((s, i) => (
          <Step key={i}>
            <StepIndicator>
              <StepStatus
                complete={<StepIcon />}
                incomplete={<StepNumber />}
                active={<StepNumber />}
              />
            </StepIndicator>
            <Box flexShrink="0">
              <StepTitle>{s.title}</StepTitle>
            </Box>
            <StepSeparator />
          </Step>
        ))}
      </Stepper>

      <Box minH="320px">
        {activeStep === 0 && (
          <FormControl isInvalid={!!nameError}>
            <FormLabel htmlFor="place-name">Place name</FormLabel>
            <Input
              id="place-name"
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. vcu118-lab1"
            />
            <FormErrorMessage>{nameError}</FormErrorMessage>
          </FormControl>
        )}

        {activeStep === 1 && (
          <Stack spacing={3}>
            {groups.length === 0 ? (
              <Text color="text.secondary">No exporter resources are available right now.</Text>
            ) : (
              groups.map((g) => {
                const ticked = isPicked(g.exporter, g.group);
                const pick = picked.find((p) => p.exporter === g.exporter && p.group === g.group);
                return (
                  <Box
                    key={`${g.exporter}/${g.group}`}
                    p={3}
                    borderWidth={1}
                    borderRadius="md"
                    bg={ticked ? subtleBg : undefined}
                  >
                    <HStack align="start">
                      <Checkbox
                        aria-label={`Select group ${g.exporter}/${g.group}`}
                        isChecked={ticked}
                        onChange={() => togglePick(g.exporter, g.group, g.classes)}
                        mt={1}
                      />
                      <Box flex={1}>
                        <Text fontWeight="600">
                          {g.exporter} / {g.group}
                        </Text>
                        <HStack spacing={1} mt={1} flexWrap="wrap">
                          {g.classes.map((c) => (
                            <Tag key={c} size="sm" variant="subtle">
                              <TagLabel>{c}</TagLabel>
                            </Tag>
                          ))}
                        </HStack>
                      </Box>
                      {ticked && (
                        <Select
                          size="sm" w="200px"
                          value={pick?.cls ?? "*"}
                          onChange={(e) => setPickedClass(g.exporter, g.group, e.target.value)}
                          aria-label={`Class filter for ${g.exporter}/${g.group}`}
                        >
                          <option value="*">all classes (*)</option>
                          {g.classes.map((c) => (
                            <option key={c} value={c}>{c} only</option>
                          ))}
                        </Select>
                      )}
                    </HStack>
                  </Box>
                );
              })
            )}
            {picked.length > 0 && (
              <Text fontSize="sm" color="text.secondary">
                {picked.length} group{picked.length === 1 ? "" : "s"} selected.
              </Text>
            )}
          </Stack>
        )}

        {activeStep === 2 && (
          <Stack spacing={4}>
            <Box>
              <Text fontWeight="600" mb={2}>Required tags</Text>
              <Stack spacing={3}>
                <FormControl isRequired>
                  <FormLabel htmlFor="tag-board-location" fontSize="sm">board-location</FormLabel>
                  <Select
                    id="tag-board-location"
                    placeholder="Select a location"
                    value={boardLocation}
                    onChange={(e) => setBoardLocation(e.target.value)}
                  >
                    {BOARD_LOCATIONS.map((loc) => (
                      <option key={loc} value={loc}>{loc}</option>
                    ))}
                  </Select>
                </FormControl>
                <FormControl isRequired>
                  <FormLabel htmlFor="tag-carrier" fontSize="sm">carrier</FormLabel>
                  <Input
                    id="tag-carrier"
                    value={carrier}
                    onChange={(e) => setCarrier(e.target.value)}
                    placeholder="e.g. rpi4, vcu118, zcu102"
                  />
                </FormControl>
                <FormControl isRequired>
                  <FormLabel htmlFor="tag-daughter-board" fontSize="sm">daughter-board</FormLabel>
                  <Input
                    id="tag-daughter-board"
                    value={daughterBoard}
                    onChange={(e) => setDaughterBoard(e.target.value)}
                    placeholder="e.g. fmcomms2, ad9084, adis16460"
                  />
                </FormControl>
              </Stack>
            </Box>
            <Box>
              <HStack mb={2}>
                <FormLabel m={0}>Additional tags</FormLabel>
                <Button
                  ml="auto" size="xs" leftIcon={<MdAdd />}
                  onClick={() => setTags((t) => [...t, { key: "", value: "" }])}
                >
                  Add tag
                </Button>
              </HStack>
              {customTagCollidesWithRequired && (
                <Text fontSize="xs" color="red.500" mb={2}>
                  Custom tag keys can't reuse the required keys above
                  ({REQUIRED_TAG_KEYS.join(", ")}).
                </Text>
              )}
              {tags.length === 0 ? (
                <Text fontSize="sm" color="text.secondary">None. Add one if you want an extra label.</Text>
              ) : (
                <Stack spacing={2}>
                  {tags.map((t, i) => (
                    <HStack key={i}>
                      <Input
                        placeholder="key" value={t.key}
                        onChange={(e) =>
                          setTags((cur) => cur.map((x, j) => (j === i ? { ...x, key: e.target.value } : x)))
                        }
                        aria-label={`Tag ${i} key`}
                      />
                      <Input
                        placeholder="value" value={t.value}
                        onChange={(e) =>
                          setTags((cur) => cur.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))
                        }
                        aria-label={`Tag ${i} value`}
                      />
                      <IconButton
                        aria-label="Remove tag" icon={<MdDelete />} size="sm" variant="ghost"
                        onClick={() => setTags((cur) => cur.filter((_, j) => j !== i))}
                      />
                    </HStack>
                  ))}
                </Stack>
              )}
            </Box>
            <FormControl>
              <FormLabel htmlFor="place-comment">Comment</FormLabel>
              <Textarea
                id="place-comment" value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Free-form description (optional)"
                rows={3}
              />
            </FormControl>
          </Stack>
        )}

        {activeStep === 3 && (
          <Stack spacing={4}>
            <Box>
              <Text fontSize="sm" color="text.secondary">Name</Text>
              <Text fontWeight="600">{name.trim()}</Text>
            </Box>
            <Box>
              <Text fontSize="sm" color="text.secondary">Resource matches ({picked.length})</Text>
              {picked.map((p, i) => (
                <Text key={i} fontFamily="mono" fontSize="sm">
                  {p.exporter}/{p.group}/{p.cls}
                </Text>
              ))}
            </Box>
            <Box>
              <Text fontSize="sm" color="text.secondary">Tags</Text>
              <HStack spacing={1} flexWrap="wrap">
                <Tag size="sm" colorScheme="adi"><TagLabel>board-location={boardLocation.trim()}</TagLabel></Tag>
                <Tag size="sm" colorScheme="adi"><TagLabel>carrier={carrier.trim()}</TagLabel></Tag>
                <Tag size="sm" colorScheme="adi"><TagLabel>daughter-board={daughterBoard.trim()}</TagLabel></Tag>
                {tags.filter((t) => t.key.trim()).map((t, i) => (
                  <Tag key={i} size="sm"><TagLabel>{t.key.trim()}={t.value}</TagLabel></Tag>
                ))}
              </HStack>
            </Box>
            <Box>
              <Text fontSize="sm" color="text.secondary">Comment</Text>
              <Text fontSize="sm">{comment.trim() || <em>none</em>}</Text>
            </Box>
          </Stack>
        )}
      </Box>

      <HStack mt={8} justify="space-between">
        <Button variant="ghost" onClick={() => nav("/places")} isDisabled={submitting}>
          Cancel
        </Button>
        <HStack>
          {canBack && (
            <Button onClick={() => setActiveStep(activeStep - 1)} variant="outline">
              Back
            </Button>
          )}
          {activeStep < STEPS.length - 1 ? (
            <Button
              onClick={() => setActiveStep(activeStep + 1)}
              isDisabled={!canNext}
            >
              Next
            </Button>
          ) : (
            <Button onClick={submit} isLoading={submitting}>
              Create place
            </Button>
          )}
        </HStack>
      </HStack>
    </Box>
  );
}
