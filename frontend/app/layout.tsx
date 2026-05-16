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
      <body>
        <nav style={{
          borderBottom: "1px solid var(--border)",
          padding: "0 24px",
          height: "48px",
          display: "flex",
          alignItems: "center",
          gap: "32px",
          background: "var(--surface)",
        }}>
          <span style={{
            fontFamily: "var(--font-display)",
            fontWeight: 800,
            fontSize: "18px",
            letterSpacing: "0.05em",
            color: "var(--amber)",
            textTransform: "uppercase",
          }}>
            ◆ Diamond Mind
          </span>
          {[
            { href: "/", label: "Slate" },
            { href: "/report", label: "Report" },
            { href: "/verify", label: "Verifier" },
          ].map(({ href, label }) => (
            <Link key={href} href={href} style={{
              fontFamily: "var(--font-display)",
              fontWeight: 600,
              fontSize: "13px",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "var(--text-2)",
              textDecoration: "none",
              transition: "color 0.15s",
            }}
            onMouseEnter={e => (e.currentTarget.style.color = "var(--text)")}
            onMouseLeave={e => (e.currentTarget.style.color = "var(--text-2)")}
            >
              {label}
            </Link>
          ))}
        </nav>
        <main style={{ maxWidth: "1200px", margin: "0 auto", padding: "32px 24px" }}>
          {children}
        </main>
      </body>
    </html>
  );
}
