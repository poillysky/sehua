import "@/styles/globals.css";
import { Metadata, Viewport } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages } from "next-intl/server";
import clsx from "clsx";

import { Providers } from "./providers";

import { siteConfig } from "@/config/site";
import { fontSans, fontNoto, fontMono } from "@/config/fonts";
import { DemoMode } from "@/components/DemoMode";
import { GlobalBackButton } from "@/components/PageBackButton";
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
  // 勿设 height: device-height —— iOS Safari 下易导致页底滚不到 / 视口异常
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
          /* 勿加 h-full：会覆盖 style.css 的 height:auto，导致 iOS Safari 滚不到页底 */
          "min-h-dvh bg-background font-sans antialiased",
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
            <div className="app-shell relative flex min-h-[100dvh] flex-col">
              <DemoMode />
              <GlobalBackButton />
              <main className="container z-10 mx-auto flex w-full max-w-6xl flex-grow flex-col md:w-4/5">
                {children}
              </main>
            </div>
          </Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
