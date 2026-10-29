// Non-generated asset URLs (evidence files, preview streams). API operations
// always go through the generated client in src/client.
export function apiUrl(path: string): string {
  return `${import.meta.env.VITE_API_URL ?? ""}${path}`
}
