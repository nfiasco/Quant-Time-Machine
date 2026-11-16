import { routeMetadata, routes } from "@/config/navigation";
import { AuthScreen } from "@/features/auth/auth-screen";

export const metadata = routeMetadata(routes.forgotPassword);

export default async function Page(props: PageProps<"/forgot-password">) {
  const { next, error } = await props.searchParams;
  return <AuthScreen mode="forgot-password" next={next} error={error} />;
}
