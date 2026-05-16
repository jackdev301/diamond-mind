import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

const FONTS_URL = "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap";

export const metadata: Metadata = {
  title: "Diamond Mind",
  description: "MLB Intelligence System",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href={FONTS_URL} rel="stylesheet" />
      </head>
      <body>
        <nav style={{
          borderBottom: "1px solid var(--border)",
          padding: "0 24px",
          height: "52px",
          display: "flex",
          alignItems: "center",
          gap: "24px",
          background: "var(--surface)",
          position: "sticky",
          top: 0,
          zIndex: 100,
        }}>
          <span style={{
            fontFamily: "var(--font-ui)",
            fontWeight: 700,
            fontSize: "15px",
            color: "var(--text)",
            letterSpacing: "-0.02em",
            marginRight: "8px",
          }}>
            Diamond Mind
          </span>
          <div style={{ width: "1px", height: "16px", background: "var(--border-2)" }} />
          {[
            { href: "/", label: "Slate" },
            { href: "/picks", label: "Picks" },
            { href: "/report", label: "Report" },
            { href: "/verify", label: "Verifier" },
          ].map(({ href, label }) => (
            <Link key={href} href={href} className="nav-link" style={{
              fontFamily: "var(--font-ui)",
              fontWeight: 500,
              fontSize: "13px",
            }}>
              {label}
            </Link>
          ))}
        </nav>
        <main style={{ maxWidth: "1120px", margin: "0 auto", padding: "28px 24px" }}>
          {children}
        </main>
      </body>
    </html>
  );
}
