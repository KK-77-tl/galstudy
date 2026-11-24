"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type MouseEvent } from "react";
import { useRouter } from "next/navigation";
import styles from "./selection.module.css";

export default function SelectionPage() {
  const router = useRouter();
  const [leaving, setLeaving] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const busy = useRef(false);
  useEffect(() => {
    router.prefetch("/female/name");
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [router]);
  function enterFemale(event: MouseEvent<HTMLAnchorElement>) {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
    event.preventDefault();
    if (busy.current) return;
    busy.current = true;
    remember("female");
    setLeaving(true);
    timer.current = setTimeout(() => router.push("/female/name"), matchMedia("(prefers-reduced-motion: reduce)").matches ? 100 : 500);
  }
  function remember(audience: string) {
    try { localStorage.setItem("galstudy.audience", audience); } catch { /* Selection remains usable with storage disabled. */ }
  }
  return (
    <main className={styles.selection} data-leaving={leaving}>
      <link rel="prefetch" as="image" href="/assets/naming/galstudy_female_name_v3.png" />
      <header className={styles.header}>
        <img src="/assets/intro/galstudy_black_title_v1.png" width="1672" height="941" alt="GalStudy" />
        <Link href="/" className={styles.replay}>重播序章 <span aria-hidden="true">↺</span></Link>
      </header>
      <div className={styles.content}>
        <p className={styles.eyebrow}>与你的故事，即将开始</p>
        <h1>选择你的心动篇章</h1>
        <p className={styles.description}>从一次相遇开始，让学习有了期待。</p>
        <div className={styles.options}>
          <Link href="/study" className={styles.option} onClick={() => remember("male")}>
            <span className={styles.scene} style={{ backgroundImage: "url('/assets/classroom.webp')" }} />
            <span className={styles.optionText}><span className={styles.caption}>放学后的约定</span><strong>男性向</strong><span>与她相遇，翻开新的学习篇章</span><span className={styles.enter}>开启故事 <span aria-hidden="true">→</span></span></span>
          </Link>
          <Link href="/female/name" className={styles.option} onClick={enterFemale}>
            <span className={styles.scene} style={{ backgroundImage: "url('/assets/library.webp')" }} />
            <span className={styles.optionText}><span className={styles.caption}>书页间的邂逅</span><strong>女性向</strong><span>与他相遇，收藏温柔的学习时光</span><span className={styles.enter}>开启故事 <span aria-hidden="true">→</span></span></span>
          </Link>
        </div>
      </div>
      <p className={styles.footer}>每一页知识，都是故事的开始。</p>
    </main>
  );
}
