"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import VisualNovelDialogue from "../../components/VisualNovelDialogue";
import { useSceneAudio } from "../../components/useSceneAudio";
import { playerProfiles, validatePlayerName } from "../../../lib/player-profile";
import styles from "./page.module.css";

const ARTWORK = "/assets/naming/galstudy_female_name_v3.png";
const INTRO = [{ text: "这枚书签，送给你。" }, { text: "对了……", pauseMs: 500 }, { text: "还不知道该怎么称呼你。" }];
type Phase = "loading" | "intro" | "editing" | "saving" | "reply" | "leaving";

export default function FemaleNamePage() {
  const router = useRouter();
  const image = useRef<HTMLImageElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const locked = useRef(false);
  const composing = useRef(false);
  const active = useRef(true);
  const [phase, setPhase] = useState<Phase>("loading");
  const [name, setName] = useState("");
  const [userId, setUserId] = useState("");
  const [error, setError] = useState("");
  const sound = useSceneAudio();
  useEffect(() => {
    active.current = true;
    let cancelled = false;
    Promise.all([image.current!.decode(), playerProfiles.currentUserId()]).then(async ([, id]) => {
      const existing = await playerProfiles.load(id, "female");
      if (cancelled) return;
      setUserId(id);
      if (navigator.userActivation?.hasBeenActive) sound.start();
      if (existing) {
        setName(existing.playerName);
        if (existing.hasCompletedNameEntry) { router.replace("/female"); return; }
        setPhase("reply");
      } else setPhase("intro");
    }).catch(() => { if (!cancelled) setError("画面或本机存档加载失败，请刷新重试。"); });
    router.prefetch("/female");
    return () => { cancelled = true; active.current = false; };
  }, [router]);
  useEffect(() => {
    if (phase !== "editing") return;
    // Desktop autofocus avoids unexpectedly opening the phone's software keyboard.
    if (matchMedia("(min-width: 800px)").matches) input.current?.focus();
  }, [phase]);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (composing.current || phase !== "editing" || locked.current) return;
    let cleaned: string;
    try { cleaned = validatePlayerName(name); } catch (e) {
      setError((e as Error).message); input.current?.focus(); return;
    }
    locked.current = true;
    setError(""); setName(cleaned); setPhase("saving");
    try {
      await playerProfiles.save(userId, "female", cleaned, false);
      if (active.current) setPhase("reply");
    } catch {
      if (active.current) { locked.current = false; setPhase("editing"); setError("姓名暂时无法保存，请检查浏览器存储后重试。"); }
    }
  }
  async function complete() {
    if (locked.current && phase === "leaving") return;
    try {
      await playerProfiles.save(userId, "female", name, true);
      if (!active.current) return;
      sound.pageTurn(); setPhase("leaving");
    } catch { if (active.current) setError("存档暂时无法保存，请刷新后重试。"); }
  }
  const editing = phase === "editing" || phase === "saving";
  const replies = [{ text: `${name}……`, pauseMs: 600 }, { text: "我记住了。" }, { text: "下次见面，我会这样叫你。" }];
  return <main className={styles.page} aria-label="女性向故事起名" onPointerDown={sound.start} onKeyDown={sound.start}>
    <link rel="preload" as="image" href={ARTWORK} />
    <div className={styles.tools}><Link href="/select">返回选择</Link><button type="button" onClick={sound.toggle} aria-pressed={sound.muted}>{sound.muted ? "开启声音" : "静音"}</button></div>
    <div className={styles.stage} data-phase={phase} onAnimationEnd={event => {
      if (event.target === event.currentTarget && phase === "leaving") router.replace("/female");
    }}>
      <img ref={image} className={styles.artwork} src={ARTWORK} width={1672} height={941} alt="雨后阅读室中，深蓝西装的黑发青年向你递出金羽毛书签。" fetchPriority="high" draggable={false} />
      <div className={styles.veil} />
      {editing && <>
        <h1 className={styles.mobileTitle}>请告诉我，你的名字</h1>
        <form className={styles.form} onSubmit={submit} aria-label="为你的故事起名" aria-busy={phase === "saving"}>
          <input ref={input} className={styles.name} aria-label="玩家姓名" name="playerName" placeholder="请输入你的名字" value={name}
            onChange={e => { setName(e.target.value); setError(""); }} disabled={phase === "saving"} autoComplete="off" spellCheck={false} enterKeyHint="go"
            aria-invalid={Boolean(error)} aria-describedby={error ? "female-name-error" : undefined}
            onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }}
            onKeyDown={event => { if (event.key === "Enter" && (composing.current || event.nativeEvent.isComposing || event.keyCode === 229)) event.preventDefault(); }} />
          <button className={styles.start} type="submit" aria-label={phase === "saving" ? "保存中" : "开始故事"} disabled={phase === "saving"}><span className={styles.mobileButton}>开始故事 →</span></button>
          {phase === "saving" && <p className={styles.error} role="status">正在记下你的名字……</p>}
          {error && <p id="female-name-error" className={styles.error} role="alert">{error}</p>}
        </form>
      </>}
      {phase === "intro" && <VisualNovelDialogue lines={INTRO} onComplete={() => setPhase("editing")} />}
      {(phase === "reply" || phase === "leaving") && <VisualNovelDialogue lines={replies} onComplete={complete} />}
    </div>
    {error && !editing && <p className={styles.loadError} role="alert">{error}</p>}
  </main>;
}
