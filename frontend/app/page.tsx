import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-24 text-center">
      <h1 className="text-4xl font-bold tracking-tight">Quant Time Machine</h1>
      <p className="mt-4 text-lg text-gray-500">
        Test investment ideas using only the information that was actually
        available on each historical date.
      </p>
      <Link
        href="/time-machine"
        className="mt-8 inline-block rounded-lg bg-black px-6 py-3 font-medium text-white"
      >
        Get started
      </Link>
    </main>
  );
}
