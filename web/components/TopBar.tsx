import Image from "next/image";
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
        {/*
          Two files rather than one recoloured by a CSS filter: the brand blue
          manages 2.27:1 on the dark paper, which cannot be read, so the dark
          theme gets its own lighter ink at 6.3:1. Both are declared and CSS
          shows one, so switching theme never flashes a missing image.

          The name lives on the link, not on either image. Only one image is
          ever displayed and the other is display:none, which assistive
          technology skips entirely - so putting the alt text on an image left
          the link with no name at all in whichever theme hid that one.

          Width and height are set so the row does not reflow as it loads.
        */}
        <Link className="brand" href={"/" as never} aria-label="easyLogistics — home">
          <Image
            className="brand-logo brand-logo-light"
            src="/logo.png"
            alt=""
            width={432}
            height={96}
            sizes="140px"
            priority
          />
          <Image
            className="brand-logo brand-logo-dark"
            src="/logo-dark.png"
            alt=""
            aria-hidden="true"
            width={432}
            height={96}
            sizes="140px"
            priority
          />
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
