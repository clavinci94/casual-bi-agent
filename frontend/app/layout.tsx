import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/sidebar";
import { TopBar } from "@/components/topbar";
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
      <body className="min-h-screen">
        <SwrProvider>
          <div className="flex min-h-screen">
            <Sidebar />
            <div className="flex-1 flex flex-col min-w-0">
              <TopBar />
              <main className="flex-1 max-w-5xl mx-auto px-6 sm:px-8 py-8 w-full">
                {children}
              </main>
            </div>
          </div>
        </SwrProvider>
      </body>
    </html>
  );
}
