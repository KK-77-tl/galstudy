"use client";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  BookOpen,
  LayoutGrid,
  Sparkles,
  Upload,
  ArrowUpRight,
  ArrowRight,
  Play,
  Plus,
  LogOut,
  ChevronLeft,
  Check,
  X,
  FileText,
  BookMarked,
  Flower2,
  Library,
  Bookmark,
  Menu,
} from "lucide-react";
import { z } from "zod";
import { api } from "../../lib/api";
import Companion, { type Character } from "../components/Companion";
import Workshop from "../components/Workshop";

const referenceSchema = z.object({
  point_id: z.string(),
  file_id: z.string().nullable().optional(),
  file: z.string(),
  location: z.string(),
  quote: z.string(),
});
const playSchema = z.object({
  node_id: z.string(),
  version: z.number(),
  score: z.number(),
  feedback: z.string().optional(),
  feedback_references: z.array(referenceSchema).default([]),
  story_revision: z.number().default(0),
  total_questions: z.number().default(1),
  mode: z.string().default("demo"),
  node: z.object({
    chapter: z.number(),
    speaker: z.string(),
    expression: z.string(),
    scene: z.string(),
    text: z.string(),
    ending: z.boolean(),
    question: z.boolean(),
    references: z.array(referenceSchema).default([]),
    choices: z.array(z.object({ id: z.string(), label: z.string() })),
  }),
});
type PlayState = z.infer<typeof playSchema>;
type Course = { id: string; title: string; demo: boolean };
type Point = {
  id: string;
  text: string;
  confirmed: boolean;
  location: string;
  file: string;
  source: string;
  mode: string;
  kind: string;
  quote: string;
};
type Detail = Course & {
  has_story: boolean;
  story_revision: number;
  learning_mode: string;
  ocr_enabled: boolean;
  story_mode: string;
  story_generating: boolean;
  llm_usage: {
    remaining_requests: number;
    remaining_reserved_tokens: number;
    warning: boolean;
  };
  files: {
    id: string;
    name: string;
    status: string;
    error: string;
    mode: string;
    attempts: number;
  }[];
  points: Point[];
};
type Wrong = {
  id: string;
  question: string;
  answer: string;
  explanation: string;
  reviewed: boolean;
};
export default function Home() {
  const [email, setEmail] = useState<string | null>(null);
  const [checked, setChecked] = useState(false);
  const [auth, setAuth] = useState<"login" | "register" | null>(null);
  const [view, setView] = useState("home");
  const [courses, setCourses] = useState<Course[]>([]);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [playing, setPlaying] = useState<PlayState | null>(null);
  const [wrong, setWrong] = useState<Wrong[]>([]);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [newCourse, setNewCourse] = useState(false);
  const [mobileMenu, setMobileMenu] = useState(false);
  const [characterId, setCharacterId] = useState("shiori");
  const [characterProfiles, setCharacterProfiles] = useState<Character[]>([]);
  const [preferredCharacterId, setPreferredCharacterId] = useState<
    string | null
  >(null);
  const preferredCharacter = characterProfiles.find(
    (profile) => profile.id === preferredCharacterId,
  );
  const sceneCharacter =
    preferredCharacter ||
    characterProfiles.find((profile) => profile.name === playing?.node.speaker);
  const loadProfiles = useCallback(async () => {
    const profiles = await api<Character[]>("/characters");
    setCharacterProfiles(profiles);
    const selected = profiles.find((profile) => profile.selected);
    setPreferredCharacterId(selected?.id || null);
    setCharacterId(selected?.id || "shiori");
  }, []);
  useEffect(() => {
    if (email) loadProfiles().catch((e) => setNotice(e.message));
  }, [email, loadProfiles]);
  useEffect(() => {
    if (preferredCharacterId) {
      setCharacterId(preferredCharacterId);
      return;
    }
    if (playing?.node.speaker)
      setCharacterId(
        playing.node.speaker === "遥"
          ? "haruka"
          : playing.node.speaker === "凛"
            ? "rin"
            : "shiori",
      );
  }, [playing?.node.speaker, preferredCharacterId]);
  const loadCourses = useCallback(
    async () => setCourses(await api<Course[]>("/courses")),
    [],
  );
  useEffect(() => {
    api<{ email: string }>("/auth/me")
      .then((u) => {
        setEmail(u.email);
        loadCourses();
      })
      .catch(() => {})
      .finally(() => setChecked(true));
  }, [loadCourses]);
  const refresh = useCallback(
    async (id: string) => setDetail(await api<Detail>("/courses/" + id)),
    [],
  );
  useEffect(() => {
    if (
      !detail ||
      (!detail.story_generating &&
        !detail.files.some((f) => ["queued", "processing"].includes(f.status)))
    )
      return;
    const timer = setInterval(
      () => refresh(detail.id).catch((e) => setNotice(e.message)),
      1200,
    );
    return () => clearInterval(timer);
  }, [detail, refresh]);
  async function run(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setNotice("");
    try {
      await action();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "操作失败，请重试");
    } finally {
      setBusy(false);
    }
  }
  function navigate(next: string) {
    if (!checked) return;
    setMobileMenu(false);
    if (!email) {
      setAuth("login");
      return;
    }
    setView(next);
    setPlaying(null);
    if (next === "wrong")
      run(async () => setWrong(await api<Wrong[]>("/wrong-answers")));
  }
  async function loadPlayer(courseId: string) {
    await refresh(courseId);
    setPlaying(playSchema.parse(await api("/courses/" + courseId + "/play")));
    setView("play");
  }
  async function startDemo() {
    if (!checked) return;
    if (!email) {
      setAuth("register");
      return;
    }
    await run(async () => {
      const course =
        courses.find((c) => c.demo) ||
        (await api<Course>("/courses", {
          method: "POST",
          body: JSON.stringify({
            title: "学习方法入门 · 放学后的约定",
            demo: true,
          }),
        }));
      await loadCourses();
      await loadPlayer(course.id);
    });
  }
  async function openCourse(course: Course) {
    await run(async () => {
      await refresh(course.id);
      setPlaying(null);
      setView("course");
    });
  }
  async function authenticate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    await run(async () => {
      const u = await api<{ email: string }>("/auth/" + auth, {
        method: "POST",
        body: JSON.stringify(Object.fromEntries(values)),
      });
      setEmail(u.email);
      setAuth(null);
      setView("courses");
      await loadCourses();
    });
  }
  async function generateCourseStory(useDemo = false) {
    if (!detail) return;
    await run(async () => {
      const result = await api<{ revision: number; mode: string }>(
        `/courses/${detail.id}/story`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_revision: detail.story_revision,
            use_demo: useDemo,
          }),
        },
      );
      await refresh(detail.id);
      if (!detail.has_story) await loadPlayer(detail.id);
      else
        setNotice(
          `${result.mode === "cloud" ? "云端" : "Demo"}剧情版本 ${result.revision} 已生成。重玩时进入新版本。`,
        );
    });
  }
  return (
    <div className="shell">
      <aside className={"sidebar " + (mobileMenu ? "shown" : "")}>
        <a className="brand" href="/" aria-label="GalStudy 首页">
          <span className="brand-icon">
            <Flower2 size={27} />
          </span>
          <span>
            GalStudy<small>让学习，成为心动的故事</small>
          </span>
        </a>
        <p className="nav-label">我的学习空间</p>
        <nav>
          {[
            { id: "home", label: "学习首页", icon: LayoutGrid },
            { id: "courses", label: "我的课程", icon: Library },
            { id: "wrong", label: "错题手记", icon: BookMarked },
            { id: "workshop", label: "角色工坊", icon: Sparkles },
          ].map((item) => (
            <button
              key={item.id}
              disabled={!checked}
              className={view === item.id ? "active" : ""}
              onClick={() => {
                if (item.id === "home") {
                  setView("home");
                  setMobileMenu(false);
                } else {
                  navigate(item.id);
                }
              }}
            >
              <item.icon size={19} />
              {item.label}
              {view === item.id && <span className="nav-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-note">
          <Sparkles size={21} />
          <strong>每一次相遇，都有新收获。</strong>
          <p>
            带上好奇心，和陪学伙伴
            <br />
            一起解锁知识的新章节。
          </p>
        </div>
        <div className="account">
          <div className="avatar">{email ? email[0].toUpperCase() : "G"}</div>
          <span>
            <strong>{email ? email.split("@")[0] : "旅人，同学"}</strong>
            <small>{email ? "本地学习账号" : "登录后保存你的学习旅程"}</small>
          </span>
          <button
            aria-label={email ? "退出登录" : "登录"}
            disabled={!checked}
            onClick={() =>
              email
                ? run(async () => {
                    await api("/auth/logout", { method: "POST" });
                    setEmail(null);
                    setCourses([]);
                    setDetail(null);
                    setPlaying(null);
                    setWrong([]);
                    setCharacterProfiles([]);
                    setPreferredCharacterId(null);
                    setCharacterId("shiori");
                    setView("home");
                  })
                : setAuth("login")
            }
          >
            <LogOut size={17} />
          </button>
        </div>
      </aside>
      <div className="content">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="mobile-toggle"
              aria-label="打开导航"
              onClick={() => setMobileMenu(!mobileMenu)}
            >
              <Menu size={22} />
            </button>
            <span>我的学习空间</span>
            <span className="slash">/</span>
            <strong>
              {view === "home"
                ? "学习首页"
                : view === "courses"
                  ? "我的课程"
                  : view === "wrong"
                    ? "错题手记"
                    : view === "play"
                      ? "故事剧场"
                      : view === "workshop"
                        ? "角色工坊"
                        : "知识点校对"}
            </strong>
          </div>
          <div className="top-actions">
            <span className="demo-badge">
              <i />{" "}
              {view === "play" && playing?.mode === "cloud"
                ? "云端剧情"
                : view === "course" && detail?.learning_mode === "cloud"
                  ? "云端已配置"
                  : "学习 Demo"}
            </span>
            {!email && (
              <button
                className="text-button"
                disabled={!checked}
                onClick={() => setAuth("login")}
              >
                登录 / 注册 <ArrowUpRight size={15} />
              </button>
            )}
            {email && (
              <span className="saved">
                <Bookmark size={14} /> 进度服务端保存
              </span>
            )}
          </div>
        </header>
        <main>
          {notice && (
            <div className="notice" role="alert">
              {notice}
              <button aria-label="关闭提示" onClick={() => setNotice("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {view === "workshop" && email && (
            <Workshop
              onCatalogChanged={loadProfiles}
              selectedCharacterId={preferredCharacterId}
            />
          )}
          {view === "home" && (
            <>
              <div className="greeting">
                <div>
                  <p className="eyebrow">A NEW CHAPTER AWAITS</p>
                  <h1>
                    今天，也一起向前一点吧 <span>✿</span>
                  </h1>
                  <p>把课件里的知识，变成故事里的每一次心动。</p>
                </div>
                <div className="date-note">
                  放学后的学习时光<span>与你的陪学伙伴，一同出发</span>
                </div>
              </div>
              <section className="hero">
                <img
                  className="hero-bg"
                  src="/assets/classroom.webp"
                  alt="樱花窗外洒满夕阳的教室"
                />
                <div className="hero-wash" />
                <div className="hero-copy">
                  <span className="pill">
                    <Sparkles size={13} /> 你的知识，你的故事
                  </span>
                  <h2>
                    与知识，
                    <br />
                    <em>怦然相遇。</em>
                  </h2>
                  <p>
                    上传一份课件，开启一段只属于你的校园物语。
                    <br />
                    在故事里理解，在陪伴中成长。
                  </p>
                  <button
                    className="primary"
                    disabled={busy || !checked}
                    onClick={() =>
                      email ? setNewCourse(true) : setAuth("register")
                    }
                  >
                    开启我的学习故事 <ArrowRight size={17} />
                  </button>
                  <button
                    className="hero-demo"
                    disabled={busy || !checked}
                    onClick={startDemo}
                  >
                    <Play size={13} fill="currentColor" /> 先体验一段原创故事
                  </button>
                </div>
                <img
                  className="hero-character"
                  src="/assets/shiori.png"
                  alt="原创陪学角色小栞，手持笔记本"
                />
                <div className="character-caption">
                  <span>小栞 SHIORI</span>
                  <p>“你的下一章，我陪你一起写。”</p>
                </div>
                <div className="hero-footer">
                  <span>✦ 放学后的约定</span>
                  <span>ORIGINAL DEMO STORY</span>
                </div>
              </section>
              <section className="quick-grid">
                <button
                  className="quick"
                  disabled={!checked}
                  onClick={() =>
                    email ? setNewCourse(true) : setAuth("register")
                  }
                >
                  <span className="quick-icon pink">
                    <Upload size={22} />
                  </span>
                  <span>
                    <strong>从一份课件开始</strong>
                    <small>PDF · PPTX · Word，知识即刻启程</small>
                  </span>
                  <ArrowUpRight size={19} />
                </button>
                <button
                  className="quick"
                  disabled={!checked}
                  onClick={startDemo}
                >
                  <span className="quick-icon green">
                    <BookOpen size={22} />
                  </span>
                  <span>
                    <strong>走进故事剧场</strong>
                    <small>选择、思考，书写属于你的分支</small>
                  </span>
                  <ArrowUpRight size={19} />
                </button>
                <button
                  className="quick"
                  disabled={!checked}
                  onClick={() => navigate("wrong")}
                >
                  <span className="quick-icon beige">
                    <BookMarked size={22} />
                  </span>
                  <span>
                    <strong>拾起遗漏的知识</strong>
                    <small>让每一次答错，都成为进步的伏笔</small>
                  </span>
                  <ArrowUpRight size={19} />
                </button>
              </section>
              <section className="courses-section">
                <div className="section-title">
                  <h2>
                    继续你的学习旅程 <span>YOUR STORIES</span>
                  </h2>
                  <button
                    className="text-button"
                    disabled={!checked}
                    onClick={() => navigate("courses")}
                  >
                    全部课程 <ArrowRight size={15} />
                  </button>
                </div>
                <div className="course-grid">
                  <article className="story-card" onClick={startDemo}>
                    <div className="course-art">
                      <img
                        src="/assets/classroom.webp"
                        alt="原创演示课程教室"
                      />
                      <span>原创演示 · 可试玩</span>
                      <button
                        aria-label="体验故事"
                        disabled={!checked}
                        onClick={(e) => {
                          e.stopPropagation();
                          startDemo();
                        }}
                      >
                        <Play size={19} fill="currentColor" />
                      </button>
                    </div>
                    <div className="course-copy">
                      <small>学习方法 · 2 个章节</small>
                      <h3>放学后的约定</h3>
                      <p>和小栞一起，找到记住知识的秘密。</p>
                      <div>
                        <span>
                          <BookOpen size={13} /> 分支剧情 · 知识挑战
                        </span>
                        <ArrowUpRight size={17} />
                      </div>
                    </div>
                  </article>
                  {courses
                    .filter((c) => !c.demo)
                    .slice(0, 1)
                    .map((c) => (
                      <article className="project-card" key={c.id}>
                        <FileText size={30} />
                        <h3>{c.title}</h3>
                        <p>资料解析与知识点校对</p>
                        <button
                          className="secondary"
                          onClick={() => openCourse(c)}
                        >
                          继续学习 <ArrowRight size={15} />
                        </button>
                      </article>
                    ))}
                  <button
                    className="new-card"
                    disabled={!checked}
                    onClick={() =>
                      email ? setNewCourse(true) : setAuth("register")
                    }
                  >
                    <span>
                      <Plus size={25} />
                    </span>
                    <strong>新的故事，等你开启</strong>
                    <small>上传你的课件，创建专属学习项目</small>
                  </button>
                </div>
              </section>
              <footer className="footer">
                <Flower2 size={15} />
                <span>让每一个知识点，都有值得记住的故事。</span>
                <small>Demo · 原创示例内容 · AI / 生图 / 支付尚未接入</small>
              </footer>
            </>
          )}
          {view === "courses" && (
            <>
              <div className="page-heading">
                <div>
                  <p className="eyebrow">YOUR STORIES</p>
                  <h1>我的课程</h1>
                  <p>每份资料，都是新故事的起点。</p>
                </div>
                <button className="primary" onClick={() => setNewCourse(true)}>
                  <Plus size={17} /> 新建学习项目
                </button>
              </div>
              <div className="course-grid">
                {courses.map((c) => (
                  <article className="project-card" key={c.id}>
                    <BookOpen size={30} />
                    <h3>{c.title}</h3>
                    <p>
                      {c.demo
                        ? "原创演示 · 双章节剧情"
                        : "资料解析 · 人工确认知识点"}
                    </p>
                    <button className="secondary" onClick={() => openCourse(c)}>
                      进入项目 <ArrowRight size={16} />
                    </button>
                  </article>
                ))}
                {!courses.length && (
                  <div className="empty">
                    还没有课程，创建一个学习项目，或从首页体验原创故事。
                  </div>
                )}
              </div>
            </>
          )}
          {view === "course" && detail && (
            <>
              <button className="back" onClick={() => setView("courses")}>
                <ChevronLeft size={16} /> 我的课程
              </button>
              <div className="page-heading">
                <div>
                  <p className="eyebrow">KNOWLEDGE STUDIO</p>
                  <h1>{detail.title}</h1>
                  <p>
                    提取原文后，编辑、补充并逐条确认。
                    {detail.learning_mode === "cloud"
                      ? "云端提炼会校验原文引用，确认前请核对内容。"
                      : "Demo 草稿采用原文摘录。"}
                  </p>
                  {detail.learning_mode === "cloud" && (
                    <p
                      className={
                        detail.llm_usage.warning ? "error-text" : "fine-print"
                      }
                    >
                      今日剩余模型请求 {detail.llm_usage.remaining_requests} 次
                      · 预留token余额{" "}
                      {detail.llm_usage.remaining_reserved_tokens}
                      {detail.llm_usage.warning && " · 调用预算已接近上限"}
                    </p>
                  )}
                </div>
                <div className="story-actions">
                  {!detail.demo && (
                    <button
                      className="secondary"
                      disabled={
                        busy ||
                        detail.story_generating ||
                        !detail.points.some((p) => p.confirmed)
                      }
                      onClick={() => generateCourseStory()}
                    >
                      <Sparkles size={16} />
                      {detail.story_generating
                        ? "云端剧情生成中…"
                        : detail.has_story
                          ? "生成新版本"
                          : detail.learning_mode === "cloud"
                            ? "生成云端剧情"
                            : "生成 Demo 剧情"}
                    </button>
                  )}
                  {!detail.demo && detail.learning_mode === "cloud" && (
                    <button
                      className="secondary"
                      disabled={
                        busy ||
                        detail.story_generating ||
                        !detail.points.some((p) => p.confirmed)
                      }
                      onClick={() => generateCourseStory(true)}
                    >
                      使用 Demo 模板
                    </button>
                  )}
                  {detail.has_story && (
                    <button
                      className="primary"
                      disabled={busy}
                      onClick={() => run(() => loadPlayer(detail.id))}
                    >
                      <Play size={16} /> 继续剧情
                    </button>
                  )}
                </div>
              </div>
              <div className="studio">
                <section className="panel">
                  <h2>课程资料</h2>
                  <p>PDF / PPTX / DOCX · 每份最大 10MB</p>
                  <p className="fine-print">
                    删除原文件会同步清理引用它的剧情版本、存档、答题记录和本课程聊天。
                  </p>
                  <label className="upload-zone">
                    <Upload size={28} />
                    <strong>{busy ? "正在上传…" : "选择课程文件"}</strong>
                    <span>
                      {detail.ocr_enabled
                        ? "文本型文档与扫描PDF可解析 · 本地OCR已启用"
                        : "文本型文档可解析，扫描件 OCR 待配置"}
                    </span>
                    <input
                      type="file"
                      accept=".pdf,.pptx,.docx"
                      disabled={busy}
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file)
                          run(async () => {
                            const data = new FormData();
                            data.set("file", file);
                            await api("/courses/" + detail.id + "/files", {
                              method: "POST",
                              body: data,
                            });
                            await refresh(detail.id);
                          });
                        e.target.value = "";
                      }}
                    />
                  </label>
                  {detail.files.map((f) => (
                    <div className="file-row" key={f.id}>
                      <FileText size={19} />
                      <div>
                        <strong>{f.name}</strong>
                        <small>
                          <span>
                            {
                              (
                                {
                                  queued: "等待解析",
                                  processing: "正在解析",
                                  ready: "解析完成",
                                  failed: "解析失败",
                                } as Record<string, string>
                              )[f.status]
                            }
                          </span>
                          {" · "}
                          {f.mode === "cloud" ? "云端提炼" : "Demo摘录"}
                        </small>
                        {f.error && <p className="error-text">{f.error}</p>}
                        {f.status === "failed" && (
                          <button
                            className="text-button"
                            disabled={busy || f.attempts >= 3}
                            onClick={() =>
                              run(async () => {
                                await api(
                                  `/courses/${detail.id}/files/${f.id}/retry`,
                                  { method: "POST" },
                                );
                                await refresh(detail.id);
                              })
                            }
                          >
                            重新解析
                          </button>
                        )}
                        {f.status === "failed" && f.mode === "cloud" && (
                          <button
                            className="text-button"
                            disabled={busy || f.attempts >= 3}
                            onClick={() =>
                              run(async () => {
                                await api(
                                  `/courses/${detail.id}/files/${f.id}/retry`,
                                  {
                                    method: "POST",
                                    body: JSON.stringify({ use_demo: true }),
                                  },
                                );
                                await refresh(detail.id);
                              })
                            }
                          >
                            使用 Demo 摘录重试
                          </button>
                        )}
                      </div>
                      <button
                        aria-label={"删除 " + f.name}
                        disabled={busy}
                        onClick={() =>
                          run(async () => {
                            await api(`/courses/${detail.id}/files/${f.id}`, {
                              method: "DELETE",
                            });
                            await refresh(detail.id);
                          })
                        }
                      >
                        <X size={16} />
                      </button>
                    </div>
                  ))}
                </section>
                <section className="panel">
                  <div className="section-title">
                    <h2>
                      知识点校对{" "}
                      <small>
                        {detail.points.filter((p) => p.confirmed).length} /{" "}
                        {detail.points.length} 已确认
                      </small>
                    </h2>
                    <button
                      className="text-button"
                      onClick={() =>
                        run(async () => {
                          await api("/courses/" + detail.id + "/points", {
                            method: "POST",
                            body: JSON.stringify({
                              text: "在这里补充一个知识点",
                              confirmed: false,
                            }),
                          });
                          await refresh(detail.id);
                        })
                      }
                    >
                      <Plus size={16} /> 补充
                    </button>
                  </div>
                  {!detail.points.length && (
                    <div className="empty">
                      上传资料后，提取结果会出现在这里。也可以手工补充知识点。
                    </div>
                  )}
                  {detail.points.map((p) => (
                    <PointEditor
                      key={p.id}
                      point={p}
                      disabled={busy}
                      onSave={(text, confirmed) =>
                        run(async () => {
                          await api(`/courses/${detail.id}/points/${p.id}`, {
                            method: "PUT",
                            body: JSON.stringify({ text, confirmed }),
                          });
                          await refresh(detail.id);
                        })
                      }
                      onDelete={() =>
                        run(async () => {
                          await api(`/courses/${detail.id}/points/${p.id}`, {
                            method: "DELETE",
                          });
                          await refresh(detail.id);
                        })
                      }
                    />
                  ))}
                </section>
              </div>
            </>
          )}
          {view === "play" && playing && detail && (
            <>
              <div className="player-heading">
                <button className="back" onClick={() => setView("course")}>
                  <ChevronLeft size={16} /> 返回项目
                </button>
                <span>
                  {playing.mode === "cloud" ? "云端剧情" : "原创 Demo"} · 第{" "}
                  {playing.node.chapter} 章 / 2 · 自动存档
                </span>
                <span>
                  答对 {playing.score} / {playing.total_questions} 题
                </span>
              </div>
              <section
                className={
                  "player " +
                  (playing.node.scene === "library" ? "library" : "")
                }
              >
                <img
                  className="player-bg"
                  src={
                    playing.node.scene === "library"
                      ? "/assets/library.webp"
                      : "/assets/classroom.webp"
                  }
                  alt={
                    playing.node.scene === "library"
                      ? "夕阳中的图书馆"
                      : "放学后的教室"
                  }
                />
                <div className="scene-label">
                  {playing.node.scene === "library"
                    ? "图书馆 · 记忆的回声"
                    : "教室 · 放学后的约定"}
                </div>
                <img
                  className={
                    "player-sprite " +
                    (playing.node.speaker === "遥" ? "haruka" : "")
                  }
                  src={
                    sceneCharacter?.expressions?.[playing.node.expression] ||
                    sceneCharacter?.portrait ||
                    (playing.node.speaker === "遥"
                      ? "/assets/haruka.png"
                      : playing.node.speaker === "凛"
                        ? "/assets/rin.png"
                        : "/assets/shiori.png")
                  }
                  alt={`${preferredCharacter?.name || playing.node.speaker} · ${playing.node.expression}`}
                />
                <div className="dialogue">
                  <div className="speaker">
                    {preferredCharacter?.name || playing.node.speaker}
                    <small>{playing.node.expression}</small>
                  </div>
                  <p>{playing.node.text}</p>
                  <div className="choices">
                    {playing.node.choices.map((c) => (
                      <button
                        key={c.id}
                        disabled={busy}
                        onClick={() =>
                          run(async () =>
                            setPlaying(
                              playSchema.parse(
                                await api("/courses/" + detail.id + "/play", {
                                  method: "POST",
                                  body: JSON.stringify({
                                    choice: c.id,
                                    version: playing.version,
                                  }),
                                }),
                              ),
                            ),
                          )
                        }
                      >
                        {c.label}
                        <ArrowRight size={15} />
                      </button>
                    ))}
                  </div>
                  {playing.node.ending && (
                    <div className="story-actions">
                      <button
                        className="secondary"
                        onClick={() => navigate("wrong")}
                      >
                        查看错题手记 <BookMarked size={16} />
                      </button>
                      <button
                        className="secondary"
                        disabled={busy}
                        onClick={() =>
                          run(async () =>
                            setPlaying(
                              playSchema.parse(
                                await api(
                                  `/courses/${detail.id}/play/restart`,
                                  {
                                    method: "POST",
                                    body: JSON.stringify({
                                      version: playing.version,
                                    }),
                                  },
                                ),
                              ),
                            ),
                          )
                        }
                      >
                        重玩最新版本
                      </button>
                    </div>
                  )}
                </div>
              </section>
              {playing.feedback && (
                <div className="feedback">
                  <Check size={18} />
                  {playing.feedback}
                </div>
              )}
              <References
                references={[
                  ...playing.feedback_references,
                  ...playing.node.references,
                ]}
              />
              <p className="fine-print">
                {detail.demo
                  ? "原创示例剧情"
                  : playing.mode === "cloud"
                    ? "基于已确认知识点的云端生成剧情"
                    : "基于已确认知识点的模板化 Demo 剧情"}{" "}
                · 版本 {playing.story_revision}。 角色与场景为 AI
                生成演示素材，表情通过文字提示。
              </p>
            </>
          )}
          {view === "wrong" && (
            <>
              <div className="page-heading">
                <div>
                  <p className="eyebrow">LEARN, AND GROW</p>
                  <h1>错题手记</h1>
                  <p>
                    今天待复习 {wrong.filter((a) => !a.reviewed).length}{" "}
                    题。答对后标记为已复习。
                  </p>
                </div>
              </div>
              {!wrong.length ? (
                <div className="empty">
                  <BookMarked size={32} />
                  <h3>还没有错题</h3>
                  <p>剧情挑战中的错题会自动保存在这里。</p>
                </div>
              ) : (
                wrong.map((a) => (
                  <ReviewCard
                    key={a.id}
                    attempt={a}
                    onReviewed={() =>
                      api<Wrong[]>("/wrong-answers").then(setWrong)
                    }
                  />
                ))
              )}
            </>
          )}
        </main>
      </div>
      {email && (
        <Companion
          characters={characterProfiles}
          courses={courses}
          activeCourseId={detail?.id}
          characterId={characterId}
          onCharacterChange={setCharacterId}
        />
      )}
      {auth && (
        <div className="modal-overlay">
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label={auth === "login" ? "登录" : "注册"}
          >
            <button
              className="modal-close"
              aria-label="关闭"
              onClick={() => setAuth(null)}
            >
              <X size={20} />
            </button>
            <Flower2 size={35} className="modal-flower" />
            <p className="eyebrow">WELCOME TO GALSTUDY</p>
            <h2>
              {auth === "login" ? "欢迎回到故事里" : "从这里，开启新的篇章"}
            </h2>
            <p>登录后，课程与存档将保存在你的账号下。</p>
            <form onSubmit={authenticate}>
              <label>
                邮箱
                <input
                  type="email"
                  name="email"
                  required
                  maxLength={254}
                  autoComplete="email"
                  placeholder="you@example.com"
                />
              </label>
              <label>
                密码
                <input
                  type="password"
                  name="password"
                  required
                  minLength={10}
                  maxLength={128}
                  autoComplete={
                    auth === "login" ? "current-password" : "new-password"
                  }
                  placeholder="至少 10 个字符"
                />
              </label>
              <button className="primary" disabled={busy}>
                {busy
                  ? "请稍候…"
                  : auth === "login"
                    ? "登录，继续旅程"
                    : "创建账号"}
                <ArrowRight size={16} />
              </button>
            </form>
            {notice && (
              <p role="alert" className="error-text">
                {notice}
              </p>
            )}
            <button
              className="auth-switch"
              onClick={() => {
                setAuth(auth === "login" ? "register" : "login");
                setNotice("");
              }}
            >
              {auth === "login" ? "第一次来？创建账号" : "已有账号？前往登录"}
            </button>
            <small className="fine-print">
              本地 Demo · 邮箱暂不验证 · 请勿使用其他平台的密码
            </small>
          </section>
        </div>
      )}
      {newCourse && (
        <div className="modal-overlay">
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label="新建学习项目"
          >
            <button
              className="modal-close"
              aria-label="关闭"
              onClick={() => setNewCourse(false)}
            >
              <X size={20} />
            </button>
            <h2>新的故事，从哪里开始？</h2>
            <p>为你的课程取一个名字，随后上传学习资料。</p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const data = new FormData(e.currentTarget);
                run(async () => {
                  const c = await api<Course>("/courses", {
                    method: "POST",
                    body: JSON.stringify({ title: data.get("title") }),
                  });
                  setNewCourse(false);
                  await loadCourses();
                  await refresh(c.id);
                  setView("course");
                });
              }}
            >
              <label>
                课程名称
                <input
                  autoFocus
                  name="title"
                  required
                  maxLength={120}
                  placeholder="例如，大学物理 · 力学篇"
                />
              </label>
              <button className="primary" disabled={busy}>
                创建学习项目 <ArrowRight size={16} />
              </button>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}

function References({
  references,
}: {
  references: z.infer<typeof referenceSchema>[];
}) {
  const unique = Array.from(
    new Map(references.map((ref) => [ref.point_id, ref])).values(),
  );
  if (!unique.length) return null;
  return (
    <section className="references" aria-label="知识来源">
      {unique.map((ref) => (
        <details key={ref.point_id}>
          <summary>
            <FileText size={13} />
            {ref.file} · {ref.location}
          </summary>
          <p>{ref.quote}</p>
        </details>
      ))}
    </section>
  );
}

function ReviewCard({
  attempt,
  onReviewed,
}: {
  attempt: Wrong;
  onReviewed: () => Promise<void>;
}) {
  const [question, setQuestion] = useState<{
    question: string;
    choices: { id: string; label: string }[];
  } | null>(null);
  const [selected, setSelected] = useState("");
  const [result, setResult] = useState<{
    correct: boolean;
    explanation: string;
    references: z.infer<typeof referenceSchema>[];
  } | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  async function openReview() {
    setLoading(true);
    setError("");
    setResult(null);
    setSelected("");
    try {
      setQuestion(await api(`/wrong-answers/${attempt.id}/review`));
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }
  async function answer(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      setResult(
        await api(`/wrong-answers/${attempt.id}/review`, {
          method: "POST",
          body: JSON.stringify({ choice: selected }),
        }),
      );
      await onReviewed();
    } catch (e) {
      setError(e instanceof Error ? e.message : "提交失败");
    } finally {
      setLoading(false);
    }
  }
  return (
    <article className="panel wrong-item">
      <h3>{attempt.question}</h3>
      <p>你的选择 · {attempt.answer}</p>
      <button className="secondary" disabled={loading} onClick={openReview}>
        {attempt.reviewed ? "再次练习" : "开始复习"}
      </button>
      {attempt.reviewed && (
        <span className="reviewed">
          <Check size={14} /> 已复习
        </span>
      )}
      {question && (
        <form onSubmit={answer} className="review-form">
          {question.choices.map((choice) => (
            <label key={choice.id}>
              <input
                type="radio"
                name={"answer-" + attempt.id}
                value={choice.id}
                checked={selected === choice.id}
                onChange={() => setSelected(choice.id)}
                required
              />
              {choice.label}
            </label>
          ))}
          <button className="primary" disabled={loading || !selected}>
            提交复习答案
          </button>
        </form>
      )}
      {result && (
        <>
          <div role="status" className="feedback">
            {result.correct ? "回答正确。" : "再看看原文吧。"}
            {result.explanation}
          </div>
          <References references={result.references} />
        </>
      )}
      {!question && (
        <details className="answer-details">
          <summary>查看原题解析</summary>
          <p>{attempt.explanation}</p>
        </details>
      )}
      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
    </article>
  );
}

function PointEditor({
  point,
  disabled,
  onSave,
  onDelete,
}: {
  point: Point;
  disabled: boolean;
  onSave: (text: string, confirmed: boolean) => void;
  onDelete: () => void;
}) {
  const [text, setText] = useState(point.text);
  useEffect(() => setText(point.text), [point.text]);
  return (
    <article className="point">
      <div className="point-meta">
        <span>
          <FileText size={13} /> {point.file} · {point.location}
          {" · "}
          {point.mode === "cloud"
            ? "云端草稿"
            : point.mode === "manual"
              ? "手工补充"
              : "Demo摘录"}
          {point.kind !== "excerpt" &&
            ` · ${{ definition: "定义", concept: "概念", pitfall: "易错点", exercise: "习题" }[point.kind] || point.kind}`}
        </span>
        {point.confirmed && (
          <span className="confirmed">
            <Check size={13} /> 已确认
          </span>
        )}
      </div>
      <textarea
        aria-label="知识点内容"
        value={text}
        maxLength={5000}
        onChange={(e) => setText(e.target.value)}
      />
      {point.source && (
        <details>
          <summary>查看来源原文</summary>
          <p>{point.source}</p>
        </details>
      )}
      <div className="point-actions">
        <button
          disabled={disabled || !text.trim()}
          onClick={() => onSave(text, false)}
        >
          保存草稿
        </button>
        <button
          className="confirm-button"
          disabled={disabled || !text.trim()}
          onClick={() => onSave(text, true)}
        >
          <Check size={14} /> 确认知识点
        </button>
        <button
          className="delete-button"
          disabled={disabled}
          onClick={onDelete}
        >
          删除
        </button>
      </div>
    </article>
  );
}
