"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/search", label: "Face search" },
  { href: "/rules", label: "Rules" },
];

export default function Nav() {
  const pathname = usePathname();
  return (
    <header className="border-b border-line bg-white">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-4">
        <Link href="/" className="flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-md bg-saffron text-sm font-semibold text-white">M</span>
          <span>
            <span className="block text-lg font-semibold leading-none tracking-tight">Mini-ASTR</span>
            <span className="text-xs text-stone-500">Synthetic SIM connection review</span>
          </span>
        </Link>
        <nav className="flex gap-1 text-sm">
          {LINKS.map((link) => {
            const active = link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`rounded-full px-3 py-1.5 ${active ? "bg-ink text-white" : "text-ink hover:bg-paper"}`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
