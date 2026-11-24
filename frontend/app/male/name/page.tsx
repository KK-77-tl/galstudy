"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import styles from "./page.module.css";

const ARTWORK = "/assets/naming/galstudy_male_name.png";
type Phase = "loading" | "editing" | "reply" | "farewell" | "leaving";

export default function MaleNamePage() {
  const router = useRouter();
  const image = useRef<HTMLImageElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const submitted = useRef(false);
  const [phase, setPhase] = useState<Phase>("loading");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [imageFailed, setImageFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    image.current!.decode().then(() => {
      if (!cancelled) setPhase("editing");
    }).catch(() => { if (!cancelled) setImageFailed(true); });
    router.prefetch("/male");
    return () => { cancelled = true; };
  }, [router]);

  useEffect(() => {
    if (phase === "reply") {
      const timer = window.setTimeout(() => setPhase("farewell"), 1800);
      return () => window.clearTimeout(timer);
    }
    if (phase === "farewell") {
      const timer = window.setTimeout(() => {
        try {
          localStorage.setItem("galstudy.playerName.male", name);
          localStorage.setItem("galstudy.audience", "male");
          setPhase("leaving");
        } catch {
          submitted.current = false;
          setError("姓名暂时无法保存，请允许本站使用浏览器存储后重试。");
          setPhase("editing");
        }
      }, 2000);
      return () => window.clearTimeout(timer);
    }
  }, [phase, name]);

  function startStory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (phase !== "editing" || submitted.current) return;
    const cleaned = name.trim();
    if (!cleaned || /[\u0000-\u001f\u007f]/u.test(cleaned)) {
      setError("请先告诉我，你的名字。");
      input.current?.focus();
      return;
    }
    submitted.current = true;
    setError("");
    setName(cleaned);
    setPhase("reply");
  }

  const dialogue = phase === "reply" ? `原来是${name}啊。`
    : phase === "farewell" || phase === "leaving" ? "那就请多指教啦！"
    : "初次见面……可以告诉我，你的名字吗？";

  return (
    <main className={styles.page} aria-label="男性向故事起名">
      <link rel="preload" as="image" href={ARTWORK} />
      <div className={styles.stage} data-phase={phase}
        onAnimationEnd={(event) => {
          if (event.target === event.currentTarget && phase === "leaving") router.replace("/male");
        }}>
        <img ref={image} className={styles.artwork} src={ARTWORK}
          width={1672} height={941} loading="eager" fetchPriority="high" draggable={false}
          alt="GalStudy。樱花与海景映入教室，手捧书本的少女站在窗前。右侧写着请告诉我，你的名字。" />
        <form className={styles.form} onSubmit={startStory} aria-label="为你的故事起名">
          <input ref={input} className={styles.name} aria-label="玩家姓名" name="playerName"
            autoComplete="off" maxLength={20} spellCheck={false} enterKeyHint="go"
            placeholder="请输入你的名字" value={name} disabled={phase !== "editing"}
            aria-invalid={Boolean(error)} aria-describedby={error ? "name-error" : undefined}
            onChange={(event) => { setName(event.target.value); setError(""); }} />
          <button className={styles.start} type="submit" aria-label="开始故事"
            disabled={phase !== "editing"} />
          {error && <p id="name-error" className={styles.error} role="alert">{error}</p>}
        </form>
        <p className={styles.dialogue} role="status" aria-live="polite" aria-atomic="true"
          key={phase === "leaving" ? "farewell" : phase}>{dialogue}</p>
      </div>
      {imageFailed && <p className={styles.loadError} role="alert">画面加载失败，请刷新页面重试。</p>}
    </main>
  );
}
