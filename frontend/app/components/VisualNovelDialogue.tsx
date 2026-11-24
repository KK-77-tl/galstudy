"use client";

import { useEffect, useRef, useState } from "react";
import styles from "./VisualNovelDialogue.module.css";

export type DialogueLine = { text: string; pauseMs?: number };
export default function VisualNovelDialogue({ lines, onComplete, speaker = "？？？", speed = 42 }: {
  lines: DialogueLine[]; onComplete: () => void; speaker?: string; speed?: number;
}) {
  const [index, setIndex] = useState(0);
  const [count, setCount] = useState(0);
  const [waiting, setWaiting] = useState(false);
  const lastClick = useRef(0);
  const finished = useRef(false);
  const chars = Array.from(lines[index].text);
  const text = lines[index].text;
  useEffect(() => {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) { setCount(Array.from(text).length); return; }
    if (count >= Array.from(text).length) return;
    const timer = setTimeout(() => setCount(n => n + 1), speed);
    return () => clearTimeout(timer);
  }, [text, speed, count]);
  useEffect(() => {
    if (!waiting) return;
    const timer = setTimeout(() => { setIndex(i => i + 1); setCount(0); setWaiting(false); }, lines[index].pauseMs ?? 0);
    return () => clearTimeout(timer);
  }, [waiting, index, lines]);
  function advance() {
    const now = performance.now();
    if (finished.current || waiting || now - lastClick.current < 180) return;
    lastClick.current = now;
    if (count < chars.length) { setCount(chars.length); return; }
    if (index === lines.length - 1) { finished.current = true; onComplete(); return; }
    if (lines[index].pauseMs) { setWaiting(true); return; }
    setIndex(index + 1);
    setCount(0);
  }
  return <button type="button" className={styles.dialogue} aria-label="继续对话" onClick={advance} disabled={waiting}>
    <span className={styles.speaker}>{speaker}</span>
    <span className={styles.text} aria-hidden="true">{chars.slice(0, count).join("")}</span>
    <span className={styles.accessible} aria-live="polite">{text}</span>
    <span className={styles.prompt}>{waiting ? "…" : "点击继续 ▷"}</span>
  </button>;
}
