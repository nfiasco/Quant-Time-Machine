"use client";

import { useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { routes } from "@/config/navigation";
import { Brand, Icon } from "./icons";

export function Navigation() {
  const [open, setOpen] = useState(false);

  return (
    <header className="site-header shell">
      <Brand />
      <Button
        variant="ghost"
        className="menu-toggle"
        aria-label={open ? "Close navigation" : "Open navigation"}
        aria-expanded={open}
        aria-controls="main-navigation"
        onClick={() => setOpen(!open)}
      >
        <span />
        <span />
      </Button>
      <nav
        id="main-navigation"
        className={`navigation ${open ? "is-open" : ""}`}
        aria-label="Main navigation"
        onClick={() => setOpen(false)}
        onKeyDown={(event) => {
          if (event.key === "Escape") setOpen(false);
        }}
      >
        <a href="#platform">Platform</a>
        <a href="#how-it-works">How it works</a>
        <a href="#data-sources">Data sources</a>
        <Button asChild variant="outline" className="nav-cta">
          <Link href={routes.dashboard.href}>
            Open workspace <Icon name="diagonal" />
          </Link>
        </Button>
      </nav>
    </header>
  );
}
