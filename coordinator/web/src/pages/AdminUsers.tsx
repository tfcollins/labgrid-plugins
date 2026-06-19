import { useState } from "react";
import {
  Box, Button, Heading, HStack, Table, Tbody, Td, Th, Thead, Tr,
  Modal, ModalBody, ModalContent, ModalCloseButton, ModalFooter, ModalHeader, ModalOverlay,
  FormControl, FormLabel, Input, Select, Switch, useDisclosure, useToast, Badge,
} from "@chakra-ui/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { authApi, ManagedUser } from "../api/auth";

export default function AdminUsers() {
  const qc = useQueryClient();
  const toast = useToast();
  const { data: users = [] } = useQuery({ queryKey: ["users"], queryFn: authApi.listUsers });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["users"] });

  const setRoleM = useMutation({
    mutationFn: ({ id, role }: { id: number; role: "admin" | "user" }) =>
      authApi.setRole(id, role),
    onSuccess: invalidate,
  });
  const setDisabledM = useMutation({
    mutationFn: ({ id, disabled }: { id: number; disabled: boolean }) =>
      authApi.setDisabled(id, disabled),
    onSuccess: invalidate,
  });

  const [pendingDelete, setPendingDelete] = useState<ManagedUser | null>(null);
  const deleteM = useMutation({
    mutationFn: (id: number) => authApi.deleteUser(id),
    onSuccess: () => { invalidate(); setPendingDelete(null); },
  });

  const create = useDisclosure();
  const [newName, setNewName] = useState("");
  const [newPw, setNewPw] = useState("");
  const [newRole, setNewRole] = useState<"admin" | "user">("user");
  const createM = useMutation({
    mutationFn: () => authApi.createUser(newName, newPw, newRole),
    onSuccess: () => {
      invalidate();
      create.onClose();
      setNewName(""); setNewPw(""); setNewRole("user");
      toast({ status: "success", title: "User created" });
    },
    onError: (e: unknown) =>
      toast({ status: "error", title: e instanceof Error ? e.message : String(e) }),
  });

  const [pwUser, setPwUser] = useState<ManagedUser | null>(null);
  const [pwValue, setPwValue] = useState("");
  const setPwM = useMutation({
    mutationFn: () => authApi.setPassword(pwUser!.id, pwValue),
    onSuccess: () => { setPwUser(null); setPwValue(""); toast({ status: "success", title: "Password reset" }); },
  });

  return (
    <Box p={4}>
      <HStack mb={4}>
        <Heading size="md">Manage users</Heading>
        <Button ml="auto" onClick={create.onOpen}>Add user</Button>
      </HStack>

      <Table size="sm">
        <Thead>
          <Tr>
            <Th>Username</Th>
            <Th>Role</Th>
            <Th>Status</Th>
            <Th>Auth</Th>
            <Th></Th>
          </Tr>
        </Thead>
        <Tbody>
          {users.map((u) => (
            <Tr key={u.id}>
              <Td>{u.username}</Td>
              <Td>
                <Select
                  size="xs" w="24"
                  value={u.role}
                  onChange={(e) => setRoleM.mutate({ id: u.id, role: e.target.value as "admin" | "user" })}
                >
                  <option value="user">user</option>
                  <option value="admin">admin</option>
                </Select>
              </Td>
              <Td>
                <Switch
                  isChecked={!u.disabled}
                  onChange={() => setDisabledM.mutate({ id: u.id, disabled: !u.disabled })}
                />
                {u.disabled && <Badge ml={2} colorScheme="red">disabled</Badge>}
              </Td>
              <Td>
                {u.has_password && <Badge mr={1}>local</Badge>}
                {u.has_oidc && <Badge colorScheme="purple">SSO</Badge>}
              </Td>
              <Td>
                <HStack>
                  {u.has_password && (
                    <Button size="xs" onClick={() => setPwUser(u)}>Reset password</Button>
                  )}
                  <Button size="xs" colorScheme="red" onClick={() => setPendingDelete(u)}>
                    Delete
                  </Button>
                </HStack>
              </Td>
            </Tr>
          ))}
        </Tbody>
      </Table>

      {/* Create modal */}
      <Modal isOpen={create.isOpen} onClose={create.onClose}>
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Add user</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <FormControl mb={3}>
              <FormLabel htmlFor="new-username">Username</FormLabel>
              <Input id="new-username" value={newName} onChange={(e) => setNewName(e.target.value)} />
            </FormControl>
            <FormControl mb={3}>
              <FormLabel htmlFor="new-password">Password</FormLabel>
              <Input id="new-password" type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} />
            </FormControl>
            <FormControl>
              <FormLabel>Role</FormLabel>
              <Select value={newRole} onChange={(e) => setNewRole(e.target.value as "admin" | "user")}>
                <option value="user">user</option>
                <option value="admin">admin</option>
              </Select>
            </FormControl>
          </ModalBody>
          <ModalFooter>
            <Button mr={2} onClick={create.onClose}>Cancel</Button>
            <Button onClick={() => createM.mutate()} isLoading={createM.isPending}>
              Create
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Delete confirm */}
      <Modal isOpen={!!pendingDelete} onClose={() => setPendingDelete(null)}>
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Delete user?</ModalHeader>
          <ModalBody>
            Permanently delete <b>{pendingDelete?.username}</b>? This cannot be undone.
          </ModalBody>
          <ModalFooter>
            <Button mr={2} onClick={() => setPendingDelete(null)}>Cancel</Button>
            <Button
              colorScheme="red"
              onClick={() => deleteM.mutate(pendingDelete!.id)}
              isLoading={deleteM.isPending}
            >
              Confirm delete
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Password reset */}
      <Modal isOpen={!!pwUser} onClose={() => setPwUser(null)}>
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Reset password for {pwUser?.username}</ModalHeader>
          <ModalBody>
            <FormControl>
              <FormLabel htmlFor="reset-pw">New password</FormLabel>
              <Input id="reset-pw" type="password" value={pwValue} onChange={(e) => setPwValue(e.target.value)} />
            </FormControl>
          </ModalBody>
          <ModalFooter>
            <Button mr={2} onClick={() => setPwUser(null)}>Cancel</Button>
            <Button onClick={() => setPwM.mutate()} isLoading={setPwM.isPending}>
              Save
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </Box>
  );
}
