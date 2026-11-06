import { SiteFooter } from "@/components/layout/site-footer";

import { ApiSection } from "./api-section";
import { FeaturesSection } from "./features-section";
import { LandingHeader } from "./landing-header";
import { Story } from "./story/story";

/**
 * The public landing page (/). overflow-x-clip, unlike hidden, keeps the story's stage
 * sticky.
 */
export function LandingPage() {
  return (
    <div className="flex min-h-full flex-col overflow-x-clip bg-background text-foreground">
      <a
        href="#features"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] focus:rounded-md focus:bg-background focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:shadow-md focus:ring-2 focus:ring-ring"
      >
        Skip the story
      </a>
      <LandingHeader />
      <main id="main-content" tabIndex={-1} className="flex-1 outline-none">
        <Story />
        <FeaturesSection />
        <ApiSection />
      </main>
      <SiteFooter note="The moving ticker wall is decoration: its tickers are real, its numbers are random." />
    </div>
  );
}
