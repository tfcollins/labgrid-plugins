import { Menu, MenuButton, MenuList, MenuItem, Button, Avatar, HStack, Text } from "@chakra-ui/react";
import { useNavigate, Link as RLink } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export default function AccountMenu() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  if (!user) {
    return (
      <Button as={RLink} to="/login" size="sm" variant="outline">
        Sign in
      </Button>
    );
  }
  return (
    <Menu>
      <MenuButton as={Button} size="sm" variant="ghost">
        <HStack>
          <Avatar size="xs" name={user.username} />
          <Text>{user.username}</Text>
          <Text fontSize="xs" color="text.secondary">({user.role})</Text>
        </HStack>
      </MenuButton>
      <MenuList>
        {user.role === "admin" && (
          <MenuItem as={RLink} to="/admin/users">Manage users</MenuItem>
        )}
        <MenuItem onClick={async () => { await logout(); nav("/login"); }}>
          Log out
        </MenuItem>
      </MenuList>
    </Menu>
  );
}
