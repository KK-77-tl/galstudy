"use client";
import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type PointerEvent,
} from "react";
import { MessageCircle, Move, Send, X, Trash2, RefreshCw } from "lucide-react";
import { api } from "../../lib/api";
import { chatEvents } from "../../lib/chat-stream";
import styles from "./Companion.module.css";

export type Character = {
  id: string;
  name: string;
  portrait: string;
  expressions?: Record<string, string>;
  tagline: string;
  greeting: string;
  selected?: boolean;
  mode?: string;
};
type Course = { id: string; title: string };
type Reference = {
  point_id: string;
  file: string;
  location: string;
  quote: string;
  text?: string;
};
type Message = {
  id: string;
  role: string;
  content: string;
  status: string;
  mode: string;
  references: Reference[];
};
type Conversation = { id: string; mode: string; messages: Message[] };
export default function Companion({
  characters,
  courses,
  activeCourseId,
  characterId,
  onCharacterChange,
}: {
  characters: Character[];
  courses: Course[];
  activeCourseId?: string;
  characterId: string;
  onCharacterChange: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [courseId, setCourseId] = useState(
    activeCourseId || courses[0]?.id || "",
  );
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [input, setInput] = useState("");
  const [error, setError] = useState("");
  const [canDemoRetry, setCanDemoRetry] = useState(false);
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(false);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [remainingTokens, setRemainingTokens] = useState(0);
  const [warning, setWarning] = useState(false);
  const [position, setPosition] = useState<{ x: number; y: number } | null>(
    null,
  );
  const controller = useRef<AbortController | null>(null);
  const transcript = useRef<HTMLDivElement>(null);
  const drag = useRef<{
    x: number;
    y: number;
    left: number;
    top: number;
    width: number;
  } | null>(null);
  const character =
    characters.find((c) => c.id === characterId) || characters[0];

  useEffect(() => {
    return () => controller.current?.abort();
  }, []);
  useEffect(() => {
    if (activeCourseId) setCourseId(activeCourseId);
  }, [activeCourseId]);
  useEffect(() => {
    if (!courseId && courses[0]) setCourseId(courses[0].id);
  }, [courseId, courses]);
  useEffect(() => {
    controller.current?.abort();
    controller.current = null;
    setSending(false);
    setInput("");
  }, [courseId, characterId]);
  useEffect(() => {
    function clamp() {
      setPosition((current) =>
        current
          ? {
              x: Math.max(
                8,
                Math.min(
                  current.x,
                  window.innerWidth - (window.innerWidth <= 780 ? 96 : 158),
                ),
              ),
              y: Math.max(8, Math.min(current.y, window.innerHeight - 70)),
            }
          : null,
      );
    }
    window.addEventListener("resize", clamp);
    return () => window.removeEventListener("resize", clamp);
  }, []);
  useEffect(() => {
    if (!open || !courseId) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    setConversation(null);
    api<{ id: string }>(`/courses/${courseId}/chat/sessions`, {
      method: "POST",
      body: JSON.stringify({ character_id: characterId }),
    })
      .then((session) => api<Conversation>("/chat/sessions/" + session.id))
      .then((session) => {
        if (!cancelled) setConversation(session);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, courseId, characterId]);
  useEffect(() => {
    if (transcript.current)
      transcript.current.scrollTop = transcript.current.scrollHeight;
  }, [conversation]);

  function updateReply(
    id: string,
    change: Partial<Message>,
    fragment?: string,
  ) {
    setConversation((current) =>
      current
        ? {
            ...current,
            messages: current.messages.map((message) =>
              message.id === id
                ? {
                    ...message,
                    ...change,
                    content:
                      fragment !== undefined
                        ? message.content + fragment
                        : (change.content ?? message.content),
                  }
                : message,
            ),
          }
        : current,
    );
  }
  async function send(event: FormEvent, useDemo = false) {
    event.preventDefault();
    if (!conversation || sending || controller.current || !input.trim()) return;
    const question = input.trim(),
      requestId = crypto.randomUUID(),
      replyId = "pending-" + requestId;
    setError("");
    setSending(true);
    setCanDemoRetry(false);
    setInput("");
    setConversation({
      ...conversation,
      messages: [
        ...conversation.messages,
        {
          id: requestId,
          role: "user",
          content: question,
          status: "complete",
          mode: "demo",
          references: [],
        },
        {
          id: replyId,
          role: "assistant",
          content: "",
          status: "processing",
          mode: conversation.mode,
          references: [],
        },
      ],
    });
    const abort = new AbortController();
    controller.current = abort;
    try {
      const response = await fetch(
        `/api/chat/sessions/${conversation.id}/messages`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            request_id: requestId,
            message: question,
            use_demo: useDemo,
          }),
          signal: abort.signal,
        },
      );
      if (!response.ok) {
        const data = await response.json();
        throw new Error(
          typeof data.detail === "string" ? data.detail : "消息提交失败",
        );
      }
      if (!response.body) throw new Error("浏览器未提供流式响应");
      for await (const item of chatEvents(response.body)) {
        if (controller.current !== abort || abort.signal.aborted) return;
        if (item.type === "meta") {
          updateReply(replyId, {
            mode: item.mode || "demo",
            references: item.references || [],
          });
          if (item.usage) {
            setRemaining(item.usage.remaining_requests);
            setRemainingTokens(item.usage.remaining_reserved_tokens);
            setWarning(item.usage.warning);
          }
        }
        if (item.type === "delta") updateReply(replyId, {}, item.text || "");
        if (item.type === "error") {
          setCanDemoRetry(true);
          throw new Error(item.message || "回复中断");
        }
        if (item.type === "done") {
          updateReply(replyId, { status: "complete" });
        }
      }
      const saved = await api<Conversation>(
        "/chat/sessions/" + conversation.id,
      );
      if (controller.current === abort) setConversation(saved);
    } catch (e) {
      if (!abort.signal.aborted) {
        const message = e instanceof Error ? e.message : "发送失败";
        setError(message);
        updateReply(replyId, { status: "failed", content: message });
        setInput(question);
      }
    } finally {
      if (controller.current === abort) {
        controller.current = null;
        setSending(false);
      }
    }
  }
  function startDrag(event: PointerEvent<HTMLButtonElement>) {
    const rect = event.currentTarget.parentElement!.getBoundingClientRect();
    drag.current = {
      x: event.clientX,
      y: event.clientY,
      left: rect.left,
      top: rect.top,
      width: rect.width,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function move(event: PointerEvent<HTMLButtonElement>) {
    if (!drag.current) return;
    setPosition({
      x: Math.max(
        8,
        Math.min(
          window.innerWidth - drag.current.width,
          drag.current.left + event.clientX - drag.current.x,
        ),
      ),
      y: Math.max(
        8,
        Math.min(
          window.innerHeight - 70,
          drag.current.top + event.clientY - drag.current.y,
        ),
      ),
    });
  }
  async function reload() {
    if (!conversation) return;
    setLoading(true);
    setError("");
    try {
      setConversation(
        await api<Conversation>("/chat/sessions/" + conversation.id),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }
  async function clear() {
    if (!conversation || sending) return;
    setLoading(true);
    setError("");
    try {
      await api("/chat/sessions/" + conversation.id, { method: "DELETE" });
      const session = await api<{ id: string }>(
        `/courses/${courseId}/chat/sessions`,
        { method: "POST", body: JSON.stringify({ character_id: characterId }) },
      );
      setConversation(await api<Conversation>("/chat/sessions/" + session.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "清空失败");
    } finally {
      setLoading(false);
    }
  }
  return (
    <aside
      className={styles.companion}
      style={
        position
          ? { left: position.x, top: position.y, right: "auto", bottom: "auto" }
          : undefined
      }
      aria-label="悬浮陪学伙伴"
    >
      {open && (
        <section className={styles.panel} aria-label="陪学对话">
          <header>
            <div>
              <strong>{character?.name || "陪学伙伴"}</strong>
              <small>{character?.tagline}</small>
            </div>
            <button
              aria-label="刷新会话"
              disabled={sending || loading}
              onClick={reload}
            >
              <RefreshCw size={15} />
            </button>
            <button
              aria-label="清空会话"
              disabled={sending || loading}
              onClick={clear}
            >
              <Trash2 size={15} />
            </button>
            <button aria-label="收起陪学" onClick={() => setOpen(false)}>
              <X size={18} />
            </button>
          </header>
          <div className={styles.selectors}>
            <label>
              课程
              <select
                aria-label="陪学课程"
                disabled={sending || loading}
                value={courseId}
                onChange={(e) => setCourseId(e.target.value)}
              >
                {!courses.length && <option value="">请先创建学习项目</option>}
                {courses.map((course) => (
                  <option key={course.id} value={course.id}>
                    {course.title}
                  </option>
                ))}
              </select>
            </label>
            <label>
              角色
              <select
                aria-label="陪学角色"
                disabled={sending || loading}
                value={characterId}
                onChange={(e) => onCharacterChange(e.target.value)}
              >
                {characters.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div
            className={styles.transcript}
            ref={transcript}
            aria-live="polite"
            aria-label="聊天记录"
          >
            {loading && <p className={styles.hint}>正在读取会话…</p>}
            {!loading && !conversation?.messages.length && (
              <p className={styles.hint}>
                {courseId
                  ? character?.greeting
                  : "创建一个学习项目，确认知识点后，就可以在这里一起讨论。"}
                <br />
                {conversation?.mode === "cloud"
                  ? "云模型会使用本课程资料回答。未找到资料时使用明确的 Demo 提示。"
                  : "Demo 模式会摘录相关知识点，未找到资料时会明确提示。"}
              </p>
            )}
            {conversation?.messages.map((message) => (
              <article
                key={message.id}
                className={
                  message.role === "user" ? styles.user : styles.assistant
                }
              >
                <small>
                  {message.role === "user" ? "你" : character?.name}
                  {message.role === "assistant" &&
                    " · " + (message.mode === "cloud" ? "云模型" : "Demo")}
                </small>
                <p>
                  {message.content ||
                    (message.status === "processing"
                      ? "正在思考…"
                      : "回复为空")}
                </p>
                {message.references.length > 0 && (
                  <details>
                    <summary>课程来源 · {message.references.length} 条</summary>
                    {message.references.map((ref, index) => (
                      <div key={ref.point_id}>
                        <strong>
                          [{index + 1}] {ref.file} · {ref.location}
                        </strong>
                        <p>{ref.quote}</p>
                      </div>
                    ))}
                  </details>
                )}
              </article>
            ))}
          </div>
          {error && (
            <div role="alert" className={styles.error}>
              {error}
            </div>
          )}
          <form onSubmit={send} className={styles.form}>
            <label className={styles.srOnly} htmlFor="companion-question">
              向陪学伙伴提问
            </label>
            <textarea
              id="companion-question"
              value={input}
              maxLength={1000}
              onChange={(e) => setInput(e.target.value)}
              placeholder="问问本课程的知识点…"
              disabled={sending || loading || !conversation}
            />
            <div>
              <small className={warning ? styles.warning : ""}>
                {remaining === null
                  ? "最多1000字 · 仅引用本课程已确认资料"
                  : `请求余额 ${remaining} 次 · 预留额度 ${remainingTokens} tokens${warning ? " · 即将用完" : ""}`}
              </small>
              <button
                aria-label="发送陪学消息"
                type="submit"
                disabled={sending || loading || !input.trim() || !conversation}
              >
                <Send size={17} />
              </button>
            </div>
            {error && input && canDemoRetry && (
              <button
                className={styles.demoRetry}
                type="button"
                disabled={sending || loading}
                onClick={(e) => send(e, true)}
              >
                使用 Demo 重试
              </button>
            )}
          </form>
        </section>
      )}
      <div className={styles.dock}>
        <button
          aria-label="拖动陪学伙伴"
          className={styles.drag}
          onPointerDown={startDrag}
          onPointerMove={move}
          onPointerUp={() => {
            drag.current = null;
          }}
          onPointerCancel={() => {
            drag.current = null;
          }}
        >
          <Move size={14} />
        </button>
        <button
          aria-label={open ? "收起陪学伙伴" : "打开陪学伙伴"}
          className={styles.toggle}
          onClick={() => setOpen(!open)}
        >
          {character && <img src={character.portrait} alt="" />}
          <span>
            {character?.name || "陪学伙伴"}
            <small>陪你一起学</small>
          </span>
          <MessageCircle size={17} />
        </button>
      </div>
    </aside>
  );
}
