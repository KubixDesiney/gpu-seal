import type { Metadata } from "next";
import { headers } from "next/headers";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Shown on social cards, where there is no page around the claim to qualify
// it. The boundary has to be in the text itself.
const SHARE_DESCRIPTION =
  "Measure the GPU you rented. Pre-alpha: structural inspection only, no provider study yet, nothing cryptographically verified.";

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host =
    requestHeaders.get("x-forwarded-host") ??
    requestHeaders.get("host") ??
    "localhost:3000";
  const protocol =
    requestHeaders.get("x-forwarded-proto") ??
    (host.startsWith("localhost") || host.startsWith("127.0.0.1")
      ? "http"
      : "https");
  const origin = `${protocol}://${host}`;

  return {
    metadataBase: new URL(origin),
    title: "GPU-SEAL — Open GPU Cloud Assurance",
    description:
      "Explore GPU-SEAL, inspect result bundles locally, understand the canary-only method, and run the open-source GPU assurance framework on your own hardware. Structural inspection only; no provider measurement study has been run.",
    applicationName: "GPU-SEAL",
    // Pre-alpha: reachable by link, but not to be indexed. robots.txt alone
    // only blocks crawling, so a URL linked elsewhere can still be listed.
    robots: { index: false, follow: false },
    icons: {
      icon: "/favicon.png",
      shortcut: "/favicon.png",
    },
    openGraph: {
      type: "website",
      url: origin,
      title: "GPU-SEAL — Open GPU Cloud Assurance",
      description: SHARE_DESCRIPTION,
      images: [
        {
          url: `${origin}/og.png`,
          width: 1200,
          height: 630,
          alt: "GPU-SEAL open GPU assurance portal",
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: "GPU-SEAL — Open GPU Cloud Assurance",
      description: SHARE_DESCRIPTION,
      images: [`${origin}/og.png`],
    },
  };
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable}`}>
        {children}
      </body>
    </html>
  );
}
