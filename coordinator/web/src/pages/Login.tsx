import { useState } from "react";
import { useNavigate, useLocation, Link as RLink } from "react-router-dom";
import {
  Box, Button, FormControl, FormLabel, Input, VStack, Heading,
  Alert, AlertIcon, Center, Divider, Text, Link,
} from "@chakra-ui/react";
import { useAuth } from "../auth/AuthContext";
import { authApi } from "../api/auth";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const from = (loc.state as { from?: string } | null)?.from || "/";

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password);
      nav(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Center minH="80vh">
      <Box w="sm" p={8} borderWidth={1} borderRadius="md">
        <Heading size="md" mb={6}>Sign in</Heading>
        <form onSubmit={onSubmit}>
          <VStack spacing={4}>
            <FormControl>
              <FormLabel htmlFor="username">Username</FormLabel>
              <Input id="username" value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
            </FormControl>
            <FormControl>
              <FormLabel htmlFor="password">Password</FormLabel>
              <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
            </FormControl>
            {error && (
              <Alert status="error">
                <AlertIcon />
                {error}
              </Alert>
            )}
            <Button type="submit" w="full" isLoading={submitting}>
              Sign in
            </Button>
          </VStack>
        </form>
        <Divider my={6} />
        <Link as={RLink} to={authApi.oidcLoginUrl()} reloadDocument>
          <Button variant="outline" w="full">Continue with SSO</Button>
        </Link>
        <Text fontSize="xs" color="text.secondary" mt={4}>
          (SSO button works only if OIDC is configured.)
        </Text>
      </Box>
    </Center>
  );
}
