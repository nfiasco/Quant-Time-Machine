import Link from "next/link";

import { routes } from "@/config/navigation";
import { siteConfig } from "@/config/site";

const linkClass =
  "rounded-sm underline-offset-4 hover:text-foreground hover:underline";

export function SiteFooter() {
  return (
    <footer className="border-t">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-3 px-4 py-6 text-xs text-muted-foreground sm:px-6 lg:px-8">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p>
            {siteConfig.name} · {siteConfig.course}
          </p>
          <nav aria-label="Footer">
            <ul className="flex flex-wrap gap-x-4 gap-y-1">
              <li>
                <Link href={routes.methodology.href} className={linkClass}>
                  Methodology
                </Link>
              </li>
              <li>
                <Link href={routes.privacy.href} className={linkClass}>
                  Privacy
                </Link>
              </li>
              <li>
                <a
                  href={siteConfig.repoUrl}
                  target="_blank"
                  rel="noreferrer"
                  className={linkClass}
                >
                  GitHub
                </a>
              </li>
            </ul>
          </nav>
        </div>
        <p className="text-pretty">
          {siteConfig.disclaimer} {siteConfig.fredNotice}
        </p>
      </div>
    </footer>
  );
}
