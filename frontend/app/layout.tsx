import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SecureRAG — Financial Intelligence Platform",
  description: "Evaluation-first RAG over SEC 10-K filings with security guardrails",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
