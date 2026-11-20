import { routeMetadata, routes } from "@/config/navigation";
import { AuthScreen } from "@/features/auth/auth-screen";

export const metadata = routeMetadata(routes.signUp);

export default async function Page(props: PageProps<"/sign-up">) {
  const { next, error } = await props.searchParams;
  return <AuthScreen mode="sign-up" next={next} error={error} />;
}
