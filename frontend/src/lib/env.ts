/**
 * Typed accessor for public environment configuration.
 * Server-only secrets never live here -- only NEXT_PUBLIC_* values.
 */
export const env = {
  apiUrl: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1",
};
