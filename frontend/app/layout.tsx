import type { Metadata } from "next";
import "./globals.css";
import { AuthGate } from "@/components/auth-gate";
import { Nav } from "@/components/nav";
import { SwrProvider } from "@/components/swr-config";

export const metadata: Metadata = {
  title: "Causal BI · Dashboard",
  description:
    "Agentic BI with causal inference, human-in-the-loop approval, and organisational memory.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen flex flex-col">
        <SwrProvider>
          <AuthGate>
            <Nav />
            <main className="flex-1 max-w-6xl mx-auto px-6 py-8 w-full">
              {children}
            </main>
          </AuthGate>
        </SwrProvider>
      </body>
    </html>
  );
}
