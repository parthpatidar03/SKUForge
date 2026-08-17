import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SKUForge — verified product enrichment",
  description:
    "Turns a part number, a brand and one line of text into a commerce ready "
    + "product record, where every attribute carries a confidence score, a "
    + "cited source and the exact sentence supporting it.",
  applicationName: "SKUForge",
};

export const viewport: Viewport = {
  themeColor: "#1B3A8F",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col bg-paper text-ink">
        {children}
      </body>
    </html>
  );
}
