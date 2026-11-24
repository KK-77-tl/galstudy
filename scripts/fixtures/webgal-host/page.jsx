"use client";

import { useEffect, useRef, useState } from "react";

function EngineFrame() {
  const frame = useRef(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const iframe = frame.current;
    const controller = new AbortController();
    let document;
    let bypass = false;
    let busy = false;

    async function submitChoice(event) {
      if (bypass) return;
      const item = event.target.closest('#chooseContainer [class*="Choose_item_"]');
      if (!item) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      if (busy) return;
      busy = true;
      setPending(true);
      setError("");
      try {
        const options = { signal: controller.signal };
        const currentResponse = await fetch("/current", options);
        if (!currentResponse.ok) throw new Error("Unable to read server progress");
        const current = await currentResponse.json();
        const choice = current.node.choices.find(
          (candidate) => candidate.label === item.textContent.trim(),
        );
        if (!choice) throw new Error("Choice does not match server progress");
        const response = await fetch("/advance", {
          ...options,
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ choice: choice.id, version: current.version }),
        });
        if (!response.ok) throw new Error(`Advance rejected ${response.status}`);
        await response.json();
        if (controller.signal.aborted || !item.isConnected) return;
        bypass = true;
        item.dispatchEvent(
          new MouseEvent("click", {
            bubbles: true,
            cancelable: true,
            view: iframe.contentWindow,
          }),
        );
        bypass = false;
      } catch (cause) {
        if (!controller.signal.aborted) setError(String(cause));
      } finally {
        busy = false;
        if (!controller.signal.aborted) setPending(false);
      }
    }

    function attach() {
      document?.removeEventListener("click", submitChoice, true);
      document = iframe.contentDocument;
      document.addEventListener("click", submitChoice, true);
    }
    iframe.addEventListener("load", attach);
    if (iframe.contentDocument?.readyState === "complete") attach();
    return () => {
      controller.abort();
      iframe.removeEventListener("load", attach);
      document?.removeEventListener("click", submitChoice, true);
    };
  }, []);

  return (
    <>
      <output id="bridge-state">{pending ? "pending" : "idle"}</output>
      <output id="bridge-error" role="alert">{error}</output>
      <iframe ref={frame} id="engine" title="WebGAL original research scene"
        src="/engine/index.html" width="1280" height="800" />
    </>
  );
}

export default function ResearchHost() {
  const [mounted, setMounted] = useState(false);
  return (
    <main>
      <button id="mount" onClick={() => setMounted(true)}>Mount</button>
      <button id="unmount" onClick={() => setMounted(false)}>Unmount</button>
      {mounted && <EngineFrame />}
    </main>
  );
}
