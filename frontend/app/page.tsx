"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import IntroAnimation from "./components/IntroAnimation";

export default function EntrancePage() {
  const router = useRouter();
  useEffect(() => { router.prefetch("/select"); }, [router]);
  return <IntroAnimation onComplete={() => router.replace("/select")} />;
}
