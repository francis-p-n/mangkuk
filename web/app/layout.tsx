import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Document checks",
  description:
    "Draft bills of lading, checked against the shipping instruction that ordered them.",
  // Declared with its type so the browser does not have to sniff it. SVG
  // only, as the static site does: the mark is two shapes and scales to any
  // size, where a bitmap would need one file per size to look right.
  icons: { icon: [{ url: "/favicon.svg", type: "image/svg+xml" }] },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
