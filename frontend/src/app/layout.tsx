import type { Metadata, Viewport } from "next";
import { Suspense } from "react";
import "./globals.css";
import { AppProviders } from "@/components/providers/app-providers";
import { AppShell } from "@/components/layout/app-shell";

export const metadata: Metadata = {
  title: {
    default: "NyaGallery",
    template: "%s · NyaGallery",
  },
  description:
    "A self-hosted gallery for anime illustration collection. Pixiv-aware, tag-driven, ImageFlow-inspired.",
  manifest: "/manifest.webmanifest",
  applicationName: "NyaGallery",
  icons: {
    icon: "/favicon.ico",
    shortcut: "/favicon.ico",
    apple: "/logo.png",
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f3f8fb" },
    { media: "(prefers-color-scheme: dark)", color: "#0f141b" },
  ],
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <script
          // Sync theme before paint to avoid a flash.
          dangerouslySetInnerHTML={{
            __html: `(()=>{try{const k='nya.theme';const v=localStorage.getItem(k)||'system';const m=window.matchMedia('(prefers-color-scheme: dark)').matches;const dark=v==='dark'||(v==='system'&&m);document.documentElement.classList.toggle('dark',dark);}catch(e){}})()`,
          }}
        />
      </head>
      <body className="min-h-screen bg-background text-foreground antialiased">
        <AppProviders>
          <Suspense fallback={<div className="min-h-screen bg-background" />}>
            <AppShell>{children}</AppShell>
          </Suspense>
        </AppProviders>
      </body>
    </html>
  );
}
