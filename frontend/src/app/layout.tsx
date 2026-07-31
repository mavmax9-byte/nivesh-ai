import type { Metadata } from "next";

import { MobileNav } from "@/components/layout/MobileNav";
import { Navbar } from "@/components/layout/Navbar";
import { Sidebar } from "@/components/layout/Sidebar";

import "./globals.css";

export const metadata: Metadata = {
  title: "Nivesh AI",
  description: "Institutional-grade AI investment research platform for Indian equities.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">
        <div className="flex min-h-screen flex-col">
          <Navbar />
          <MobileNav />
          <div className="flex flex-1">
            <Sidebar />
            <main className="mx-auto w-full max-w-content flex-1 p-4 sm:p-6">{children}</main>
          </div>
        </div>
      </body>
    </html>
  );
}
