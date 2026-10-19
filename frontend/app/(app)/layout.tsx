import { AppHeader } from "@/components/layout/app-header";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { SiteFooter } from "@/components/layout/site-footer";
import { SidebarProvider } from "@/components/ui/sidebar";

// The app shell: sidebar, sticky header, page content, footer.
// Pages outside this route group (sign-in, sign-up, 404) render without it.
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-background focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:shadow-md focus:ring-2 focus:ring-ring"
      >
        Skip to content
      </a>
      <SidebarProvider>
        <AppSidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <AppHeader />
          <main id="main-content" tabIndex={-1} className="flex-1 outline-none">
            <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
              {children}
            </div>
          </main>
          <SiteFooter />
        </div>
      </SidebarProvider>
    </>
  );
}
