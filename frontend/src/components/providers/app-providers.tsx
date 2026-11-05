"use client";

import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LocaleProvider } from "./locale-provider";
import { ThemeProvider } from "./theme-provider";
import { AuthProvider } from "./auth-provider";
import { ContentPreferencesProvider } from "./content-preferences-provider";
import { ToastProvider } from "./toast-provider";
import { NotificationsProvider } from "./notifications-provider";

export function AppProviders({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            refetchOnWindowFocus: false,
            retry: 1,
          },
        },
      })
  );

  return (
    <QueryClientProvider client={client}>
      <LocaleProvider>
        <ThemeProvider>
          <AuthProvider>
            <ContentPreferencesProvider>
              <ToastProvider>
                <NotificationsProvider>{children}</NotificationsProvider>
              </ToastProvider>
            </ContentPreferencesProvider>
          </AuthProvider>
        </ThemeProvider>
      </LocaleProvider>
    </QueryClientProvider>
  );
}
