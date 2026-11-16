import { routeMetadata, routes } from "@/config/navigation";
import { AuthScreen } from "@/features/auth/auth-screen";

export const metadata = routeMetadata(routes.signIn);

export default async function Page(props: PageProps<"/sign-in">) {
  const { next, error } = await props.searchParams;
  return <AuthScreen mode="sign-in" next={next} error={error} />;
}
