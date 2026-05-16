import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Diamond Mind",
  description: "MLB Intelligence System",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-950 text-gray-100 antialiased">
        <nav className="border-b border-gray-800 px-6 py-3 flex items-center gap-6">
          <span className="font-bold text-lg tracking-tight">⚾ Diamond Mind</span>
          <Link href="/" className="text-sm text-gray-400 hover:text-white transition-colors">Slate</Link>
          <Link href="/report" className="text-sm text-gray-400 hover:text-white transition-colors">Report</Link>
          <Link href="/verify" className="text-sm text-gray-400 hover:text-white transition-colors">Bet Verifier</Link>
        </nav>
        <main className="max-w-6xl mx-auto px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
