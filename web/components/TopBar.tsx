import Link from "next/link";
import ThemeToggle from "./ThemeToggle";

/**
 * The bar across every page.
 *
 * Until now Today had no way to reach anything and the search page had a lone
 * "Today" link in the corner, so the two pages did not read as one product.
 * A persistent bar answers the three questions a first-time reader has at
 * once: what is this, where else can I go, and where am I now.
 *
 * `here` rather than usePathname so this stays a server component - it is on
 * every page, and shipping a client bundle to highlight one link would be a
 * poor trade.
 */
export default function TopBar({ here }: { here: "today" | "search" | "settings" }) {
  const links = [
    { key: "today", href: "/", label: "Today" },
    { key: "search", href: "/search", label: "Every shipment" },
    { key: "settings", href: "/settings", label: "Settings" },
  ] as const;

  return (
    <div className="topbar">
      <div className="topbar-inner">
        <Link className="brand" href={"/" as never}>
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 32 32" width="22" height="22">
              <rect width="32" height="32" rx="7" fill="currentColor" />
              <path
                d="M9 16.5l5 5 9-11"
                stroke="var(--paper)"
                strokeWidth="3.2"
                fill="none"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
          <span className="brand-name">Document checks</span>
        </Link>

        <nav aria-label="Sections">
          {links.map((l) => (
            <Link
              key={l.key}
              href={l.href as never}
              aria-current={here === l.key ? "page" : undefined}
            >
              {l.label}
            </Link>
          ))}
        </nav>

        <ThemeToggle />
      </div>
    </div>
  );
}
