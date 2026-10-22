import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { ApiError } from "./api/client";
import "./theme.css";

const queries = new QueryClient({
  defaultOptions: {
    queries: {
      // Fleet data is a read model that changes when a phone syncs — seconds
      // stale is fine, and refetching on every window focus would hammer the
      // server for a dashboard that is usually left open on a second monitor.
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      // A rejected token will be rejected again. Retrying it three times just
      // delays the sign-in prompt the operator actually needs to see.
      retry: (attempt, error) =>
        !(error instanceof ApiError && error.isAuthFailure) && attempt < 2,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queries}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
