import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Document checks",
  description:
    "Draft bills of lading, checked against the shipping instruction that ordered them.",
  icons: { icon: "/favicon.svg" },
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
