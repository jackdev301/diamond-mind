"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Slate" },
  { href: "/picks", label: "Picks" },
  { href: "/tracker", label: "Tracker" },
  { href: "/report", label: "Report" },
  { href: "/verify", label: "Verifier" },
  { href: "/admin", label: "Admin" },
];

export function NavLinks() {
  const path = usePathname();
  return (
    <>
      {LINKS.map(({ href, label }) => {
        const active = href === "/" ? path === "/" : path.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className="nav-link"
            style={{
              fontFamily: "var(--font-ui)",
              fontWeight: active ? 600 : 500,
              fontSize: "13px",
              color: active ? "var(--text)" : "var(--text-2)",
              borderBottom: active ? "2px solid var(--blue)" : "2px solid transparent",
              paddingBottom: "2px",
              textDecoration: "none",
            }}
          >
            {label}
          </Link>
        );
      })}
    </>
  );
}
