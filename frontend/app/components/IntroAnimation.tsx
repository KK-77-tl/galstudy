"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import styles from "./IntroAnimation.module.css";

export type IntroAnimationProps = {
  classroomSrc?: string;
  logoSrc?: string;
  onComplete: (reason: "finished" | "skipped") => void;
  className?: string;
};

/** A ten-second sequence. Timing begins after both displayed images decode. */
export default function IntroAnimation({
  classroomSrc = "/assets/intro/galstudy_intro_quote_v1.png",
  logoSrc = "/assets/intro/galstudy_black_title_v1.png",
  onComplete,
  className = "",
}: IntroAnimationProps) {
  const classroom = useRef<HTMLImageElement>(null);
  const logo = useRef<HTMLImageElement>(null);
  const completed = useRef(false);
  const callback = useRef(onComplete);
  const [state, setState] = useState<"loading" | "playing" | "error">("loading");

  useEffect(() => { callback.current = onComplete; }, [onComplete]);

  const finish = useCallback((reason: "finished" | "skipped") => {
    if (completed.current) return;
    completed.current = true;
    callback.current(reason);
  }, []);

  useEffect(() => {
    let cancelled = false;
    completed.current = false;
    setState("loading");
    Promise.all([classroom.current!.decode(), logo.current!.decode()])
      .then(() => { if (!cancelled) setState("playing"); })
      .catch(() => { if (!cancelled) setState("error"); });
    return () => { cancelled = true; };
  }, [classroomSrc, logoSrc]);

  return (
    <section
      className={`${styles.intro} ${className}`}
      data-state={state}
      aria-label="GalStudy 入场动画"
      aria-busy={state === "loading"}
    >
      <link rel="preload" as="image" href={classroomSrc} />
      <link rel="preload" as="image" href={logoSrc} />
      <div className={styles.classroom}>
        <img ref={classroom} src={classroomSrc} width="1672" height="941"
          loading="eager" fetchPriority="high" draggable={false}
          alt="夕阳下的教室。What does your conscience say? You shall become who you are. — Friedrich Nietzsche" />
      </div>
      <div className={styles.title}
        onAnimationEnd={(event) => {
          if (event.target === event.currentTarget) finish("finished");
        }}>
        <img ref={logo} src={logoSrc} width="1672" height="941"
          loading="eager" fetchPriority="high" draggable={false} alt="GalStudy" />
      </div>
      <button type="button" className={styles.skip} onClick={() => finish("skipped")}>
        跳过 <span aria-hidden="true">›</span>
      </button>
      {state === "error" && <p className={styles.error} role="status">素材加载失败，请点击跳过继续。</p>}
    </section>
  );
}
