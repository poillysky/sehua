import "@/styles/globals.css";
import { Metadata, Viewport } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages } from "next-intl/server";
import clsx from "clsx";

import { Providers } from "./providers";

import { siteConfig } from "@/config/site";
import { fontSans, fontNoto, fontMono } from "@/config/fonts";
import { DemoMode } from "@/components/DemoMode";
import { BgEffect } from "@/components/BgEffect";
import { IosStandalone } from "@/components/IosStandalone";
import { SafariChromeTint } from "@/components/SafariChromeTint";
import { CHROME_DARK, CHROME_LIGHT } from "@/config/chrome";

export const metadata: Metadata = {
  title: {
    default: siteConfig.name,
    template: `%s - ${siteConfig.name}`,
  },
  description: siteConfig.description,
  applicationName: siteConfig.name,
  appleWebApp: {
    capable: true,
    title: siteConfig.shortName,
    statusBarStyle: "black-translucent",
  },
  formatDetection: {
    telephone: false,
  },
  other: {
    "mobile-web-app-capable": "yes",
  },
  icons: {
    icon: [
      { url: "/icon/favicon", type: "image/png", sizes: "32x32" },
      { url: "/icon/192", type: "image/png", sizes: "192x192" },
      { url: "/icon/512", type: "image/png", sizes: "512x512" },
      { url: "/icons/app-icon.svg", type: "image/svg+xml" },
      { url: "/logo.svg", type: "image/svg+xml" },
    ],
    apple: [{ url: "/apple-icon", type: "image/png", sizes: "180x180" }],
    shortcut: "/icon/favicon",
  },
  manifest: "/manifest.webmanifest",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: CHROME_LIGHT },
    { media: "(prefers-color-scheme: dark)", color: CHROME_DARK },
  ],
  colorScheme: "light dark",
  width: "device-width",
  height: "device-height",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: "cover",
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    <html suppressHydrationWarning lang={locale}>
      <head />
      <body
        className={clsx(
          "h-full bg-background font-sans antialiased",
          fontSans.variable,
          fontMono.variable,
          locale.startsWith("zh") ? fontNoto.className : "",
        )}
      >
        <NextIntlClientProvider messages={messages}>
          <Providers
            themeProps={{
              attribute: "class",
              defaultTheme: "system",
              enableSystem: true,
            }}
          >
            <IosStandalone />
            <SafariChromeTint />
            <div className="app-shell relative flex h-full min-h-[100dvh] flex-col">
              <DemoMode />
              <BgEffect />
              <main className="container z-10 mx-auto w-full max-w-6xl flex-grow md:w-4/5">
                {children}
              </main>
            </div>
          </Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
