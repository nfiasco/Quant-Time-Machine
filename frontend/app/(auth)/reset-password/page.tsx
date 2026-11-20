import { routeMetadata, routes } from "@/config/navigation";
import { AuthScreen } from "@/features/auth/auth-screen";

export const metadata = routeMetadata(routes.resetPassword);

export default async function Page(props: PageProps<"/reset-password">) {
  const { next, error } = await props.searchParams;
  return <AuthScreen mode="reset-password" next={next} error={error} />;
}
