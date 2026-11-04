import { routeMetadata, routes } from "@/config/navigation";
import { LandingPage } from "@/features/landing/landing-page";

export const metadata = routeMetadata(routes.home);

export default function HomePage() {
  return <LandingPage />;
}
