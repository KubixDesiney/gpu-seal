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
      "Explore GPU-SEAL, inspect result bundles locally, understand the canary-only method, and run the open-source GPU assurance framework on your own hardware.",
    applicationName: "GPU-SEAL",
    icons: {
      icon: "/favicon.png",
      shortcut: "/favicon.png",
    },
    openGraph: {
      type: "website",
      url: origin,
      title: "GPU-SEAL — Open GPU Cloud Assurance",
      description: "Measure the GPU you rented. Trust the evidence, not the invoice.",
      images: [
        {
          url: `${origin}/og.png`,
          width: 1200,
          height: 630,
          alt: "GPU-SEAL Ghost Meter open GPU assurance portal",
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: "GPU-SEAL — Open GPU Cloud Assurance",
      description: "Measure the GPU you rented. Trust the evidence, not the invoice.",
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
