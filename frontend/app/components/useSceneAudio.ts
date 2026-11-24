"use client";
import { useEffect, useRef, useState } from "react";

// Original, quiet synthesized accompaniment. No external recordings required.
export function useSceneAudio() {
  const context = useRef<AudioContext | null>(null);
  const output = useRef<GainNode | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const [muted, setMuted] = useState(false);
  useEffect(() => () => {
    if (timer.current) clearInterval(timer.current);
    void context.current?.close();
    timer.current = null;
    context.current = null;
    output.current = null;
  }, []);
  function start() {
    if (context.current) {
      if (context.current.state === "suspended") void context.current.resume().catch(() => {});
      return;
    }
    try {
      const ctx = new AudioContext();
      context.current = ctx;
      const gain = ctx.createGain();
      output.current = gain;
      gain.gain.value = 0;
      gain.connect(ctx.destination);
      gain.gain.linearRampToValueAtTime(muted ? 0 : .045, ctx.currentTime + 2);
      void ctx.resume().catch(() => {});
      let chord = 0;
      const play = () => {
        const notes = [[220, 261.63, 329.63], [174.61, 220, 261.63], [196, 246.94, 293.66], [164.81, 220, 329.63]][chord++ % 4];
        notes.forEach((frequency, i) => {
          const voice = ctx.createOscillator();
          const envelope = ctx.createGain();
          const at = ctx.currentTime + i * .35;
          voice.type = "triangle";
          voice.frequency.value = frequency;
          envelope.gain.setValueAtTime(0, at);
          envelope.gain.linearRampToValueAtTime(.3, at + .04);
          envelope.gain.exponentialRampToValueAtTime(.001, at + 3.5);
          voice.connect(envelope).connect(gain);
          voice.start(at); voice.stop(at + 4);
          voice.onended = () => { voice.disconnect(); envelope.disconnect(); };
        });
      };
      play(); timer.current = setInterval(play, 4800);
    } catch { /* The scene remains usable when browser audio is unavailable. */ }
  }
  function toggle() {
    start();
    const next = !muted;
    setMuted(next);
    if (output.current && context.current) output.current.gain.setTargetAtTime(next ? 0 : .045, context.current.currentTime, .2);
  }
  function pageTurn() {
    const ctx = context.current;
    if (!ctx || muted || !output.current) return;
    const buffer = ctx.createBuffer(1, ctx.sampleRate * .4, ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < data.length; i++) data[i] = (Math.random() * 2 - 1) * .12 * Math.sin(Math.PI * i / data.length);
    const source = ctx.createBufferSource();
    const filter = ctx.createBiquadFilter();
    filter.type = "lowpass"; filter.frequency.value = 2400;
    source.buffer = buffer; source.connect(filter).connect(output.current); source.start();
    source.onended = () => { source.disconnect(); filter.disconnect(); };
  }
  return { start, toggle, pageTurn, muted };
}
