"use client";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Upload, Sparkles, RefreshCw, Check, Trash2 } from "lucide-react";
import { api } from "../../lib/api";
import { alipayCheckoutUrl, paymentModeLabel } from "../../lib/payment";
import styles from "./Workshop.module.css";

type Product = {
  id: string;
  title: string;
  price_cents: number;
  pack: { expressions: number; poses: number };
  image_mode: string;
  payment_mode: string;
  reference_retention_days: number;
};
type Reference = {
  id: string;
  status: string;
  expires_at: number;
  url: string;
};
type Order = {
  id: string;
  status: string;
  amount_cents: number;
  mode: string;
  checkout?: { url?: string | null; notice: string };
  refund?: { id: string; status: string; updated_at: number } | null;
  entitlement: { id: string; status: string } | null;
};
type Job = {
  id: string;
  name: string;
  status: string;
  mode: string;
  attempts: number;
  max_attempts: number;
  error: string;
};
type Character = {
  id: string;
  name: string;
  persona: string;
  mode: string;
  assets: { kind: string; label: string; url: string; placeholder: boolean }[];
};
const statusLabels: Record<string, string> = {
  pending: "待付款",
  paid: "已付款",
  refund_pending: "退款处理中",
  refunded: "已退款",
  payment_review: "付款状态需核对",
  held: "暂停使用",
  refunding: "退款冻结中",
  unknown: "结果待确认",
  succeeded: "退款成功",
  closed: "订单已关闭",
  failed: "失败",
  available: "可用",
  reserved: "生成中",
  consumed: "已使用",
  pending_review: "待审核",
  approved: "已通过",
  rejected: "已拒绝",
  queued: "排队中",
  submitting: "提交工作流",
  generating: "生成中",
  reviewing: "结果待审核",
  complete: "已交付",
  cancelled: "已取消",
};

export default function Workshop({
  onCatalogChanged,
  selectedCharacterId,
}: {
  onCatalogChanged: () => Promise<void>;
  selectedCharacterId: string | null;
}) {
  const [products, setProducts] = useState<Product[]>([]);
  const [references, setReferences] = useState<Reference[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [referenceId, setReferenceId] = useState("");
  const [orderId, setOrderId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [containsPerson, setContainsPerson] = useState(false);
  const product = products[0];
  const order = orders.find((item) => item.id === orderId);
  const reference = references.find((item) => item.id === referenceId);
  const refresh = useCallback(async () => {
    const [refs, orders, jobs, characters] = await Promise.all([
      api<Reference[]>("/workshop/references"),
      api<Order[]>("/workshop/orders"),
      api<Job[]>("/workshop/jobs"),
      api<Character[]>("/workshop/characters"),
    ]);
    setReferences(refs);
    setOrders(orders);
    setJobs(jobs);
    setCharacters(characters);
    setReferenceId((current) =>
      refs.some((item) => item.id === current) ? current : refs[0]?.id || "",
    );
    setOrderId((current) =>
      orders.some((item) => item.id === current)
        ? current
        : orders.find((item) => item.entitlement?.status === "available")?.id ||
          orders[0]?.id ||
          "",
    );
  }, []);
  useEffect(() => {
    api<Product[]>("/workshop/products")
      .then(setProducts)
      .catch((e) => setError(e.message));
    refresh().catch((e) => setError(e.message));
  }, [refresh]);
  useEffect(() => {
    if (
      !jobs.some((job) =>
        ["queued", "submitting", "generating", "reviewing"].includes(
          job.status,
        ),
      )
    )
      return;
    const timer = setInterval(
      () => refresh().catch((e) => setError(e.message)),
      1000,
    );
    return () => clearInterval(timer);
  }, [jobs, refresh]);
  async function run(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await action();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失败，请重试");
    } finally {
      setBusy(false);
    }
  }
  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget,
      data = new FormData(form);
    await run(async () => {
      const result = await api<{ id: string }>("/workshop/references", {
        method: "POST",
        body: data,
      });
      setReferenceId(result.id);
      form.reset();
      setContainsPerson(false);
    });
  }
  async function createJob(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    await run(async () => {
      await api("/workshop/jobs", {
        method: "POST",
        body: JSON.stringify({
          ...values,
          request_id: crypto.randomUUID(),
          entitlement_id: order?.entitlement?.id,
          reference_id: referenceId,
        }),
      });
    });
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">CHARACTER WORKSHOP</p>
          <h1>你的专属陪学伙伴</h1>
          <p>为新的学习旅程，准备一位同行的人。</p>
        </div>
        <span className={styles.badge}>
          {paymentModeLabel(product?.payment_mode ?? "mock")} ·{" "}
          {product?.image_mode === "comfyui" ? "ComfyUI 已配置" : "Mock 生图"}
        </span>
      </div>
      <div className={styles.notice}>
        {product?.payment_mode === "alipay_live"
          ? "当前新订单使用支付宝付款，请在支付宝页面核对金额。未使用的生成权益申请退款后会冻结，待查询确认结果。"
          : product?.payment_mode === "alipay_sandbox"
            ? "当前新订单使用支付宝沙箱，不产生真实扣款。"
            : "当前订单为付款模拟，不产生真实扣款。"}
        {product?.image_mode === "mock"
          ? "Mock角色包交付预设演示立绘，表情和姿态通过素材标签占位。参考图用于私有上传与审核流程。"
          : "角色包由已配置的生成服务处理，完成后仍需审核。"}
      </div>
      {error && (
        <div className="notice" role="alert">
          {error}
        </div>
      )}
      <div className={styles.grid}>
        <section className="panel">
          <h2>角色参考图</h2>
          <p>静态 PNG / JPEG / WebP · 最大5MB · 128至4096像素</p>
          <form className={styles.form} onSubmit={upload}>
            <label className={styles.upload}>
              <Upload size={25} />
              <span>选择参考图片</span>
              <input
                aria-label="角色参考图片"
                type="file"
                name="file"
                required
                accept="image/png,image/jpeg,image/webp"
              />
            </label>
            <label className={styles.checkbox}>
              <input
                type="checkbox"
                name="rights_confirmed"
                value="true"
                required
              />
              我拥有此图片的使用权，并同意用于角色生成。
            </label>
            <label className={styles.checkbox}>
              <input
                type="checkbox"
                name="contains_real_person"
                value="true"
                checked={containsPerson}
                onChange={(e) => setContainsPerson(e.target.checked)}
              />
              图片包含真实人物。
            </label>
            {containsPerson && (
              <label className={styles.checkbox}>
                <input
                  type="checkbox"
                  name="person_consent_confirmed"
                  value="true"
                  required
                />
                已取得被摄者对本次用途的适当同意。
              </label>
            )}
            <button className="secondary" disabled={busy}>
              <Upload size={15} /> 上传参考图
            </button>
          </form>
          <p className="fine-print">
            参考图最长保存 {product?.reference_retention_days || 7}{" "}
            天。删除参考图会取消未完成任务并恢复对应权益。已交付角色可在角色库单独删除。
          </p>
          <div className={styles.references}>
            {references.map((ref) => (
              <article
                key={ref.id}
                className={referenceId === ref.id ? styles.selected : ""}
              >
                <button
                  className={styles.referenceSelect}
                  onClick={() => setReferenceId(ref.id)}
                >
                  <img src={ref.url} alt="私有角色参考图" />
                  <span>
                    {statusLabels[ref.status]}
                    <small>
                      保留至{" "}
                      {new Date(ref.expires_at * 1000).toLocaleDateString(
                        "zh-CN",
                      )}
                    </small>
                  </span>
                </button>
                <div>
                  {product?.image_mode === "mock" &&
                    ref.status !== "approved" && (
                      <button
                        className="text-button"
                        disabled={busy}
                        onClick={() =>
                          run(async () => {
                            await api(`/workshop/references/${ref.id}/review`, {
                              method: "POST",
                              body: JSON.stringify({ approved: true }),
                            });
                          })
                        }
                      >
                        <Check size={13} /> 模拟审核通过
                      </button>
                    )}
                  <button
                    aria-label="删除参考图"
                    disabled={busy}
                    onClick={() =>
                      run(async () => {
                        await api("/workshop/references/" + ref.id, {
                          method: "DELETE",
                        });
                      })
                    }
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </article>
            ))}
          </div>
        </section>
        <section className="panel">
          <h2>专属角色静态包</h2>
          <div className={styles.product}>
            <Sparkles size={26} />
            <div>
              <strong>
                主立绘1张 · 表情{product?.pack.expressions ?? 6}项 · 姿态
                {product?.pack.poses ?? 3}项
              </strong>
              <small>单次购买一个角色生成权益</small>
            </div>
            <span>
              {product?.payment_mode === "mock" ? "演示价" : "价格"} ¥{((product?.price_cents || 0) / 100).toFixed(2)}
            </span>
          </div>
          <button
            className="secondary"
            disabled={busy || !product}
            onClick={() =>
              run(async () => {
                const created = await api<Order>("/workshop/orders", {
                  method: "POST",
                  body: JSON.stringify({
                    product_id: product.id,
                    request_id: crypto.randomUUID(),
                  }),
                });
                setOrderId(created.id);
              })
            }
          >
            {product?.payment_mode === "mock" ? "创建模拟订单" : "创建订单"}
          </button>
          {orders.length > 0 && (
            <div className={styles.form}>
              <label>
                选择订单
                <select
                  aria-label="角色包订单"
                  value={orderId}
                  onChange={(e) => setOrderId(e.target.value)}
                >
                  {orders.map((item) => (
                    <option key={item.id} value={item.id}>
                      订单 {item.id.slice(-6)} · {paymentModeLabel(item.mode)} · {statusLabels[item.status]}
                      {item.entitlement
                        ? " · 权益" + statusLabels[item.entitlement.status]
                        : ""}
                    </option>
                  ))}
                </select>
              </label>
              {order && (
                <div className={styles.order}>
                  <span>
                    {paymentModeLabel(order.mode)} · ¥{(order.amount_cents / 100).toFixed(2)} ·{" "}
                    {statusLabels[order.status]}
                    {order.entitlement
                      ? " · 权益" + statusLabels[order.entitlement.status]
                      : ""}
                  </span>
                  {order.mode === "mock" && order.status !== "paid" && (
                    <div>
                      <button
                        className="primary"
                        disabled={busy}
                        onClick={() =>
                          run(async () => {
                            await api(`/workshop/orders/${order.id}/simulate`, {
                              method: "POST",
                              body: JSON.stringify({ status: "paid" }),
                            });
                          })
                        }
                      >
                        模拟付款成功
                      </button>
                      <button
                        className="text-button"
                        disabled={busy}
                        onClick={() =>
                          run(async () => {
                            await api(`/workshop/orders/${order.id}/simulate`, {
                              method: "POST",
                              body: JSON.stringify({ status: "failed" }),
                            });
                          })
                        }
                      >
                        模拟付款失败
                      </button>
                    </div>
                  )}
                  {order.mode !== "mock" && (
                    <div>
                      <p>{order.checkout?.notice}</p>
                      {order.status === "pending" && alipayCheckoutUrl(order.mode, order.checkout?.url) && (
                        <a className="primary" href={alipayCheckoutUrl(order.mode, order.checkout?.url)!} target="_blank" rel="noopener noreferrer">
                          前往{paymentModeLabel(order.mode)}
                        </a>
                      )}
                      <button className="secondary" disabled={busy || product?.payment_mode !== order.mode}
                        onClick={() => run(async () => { await api(`/workshop/orders/${order.id}/refresh`, { method: "POST" }); })}>
                        查询付款状态
                      </button>
                      {order.status === "paid" && order.entitlement?.status === "available" && (
                        <>
                          <p>全额退款 ¥{(order.amount_cents / 100).toFixed(2)}，提交后将冻结未使用的生成权益。</p>
                          <button className="text-button" disabled={busy || product?.payment_mode !== order.mode}
                            onClick={() => run(async () => { await api(`/workshop/orders/${order.id}/refund`, { method: "POST" }); })}>
                            申请全额退款
                          </button>
                        </>
                      )}
                      {order.refund && order.refund.status !== "succeeded" && (
                        <>
                          <p>退款{statusLabels[order.refund.status] ?? "处理中"}。请等待至少10秒再查询，请勿重复付款或提交退款。</p>
                          <button className="secondary" disabled={busy || product?.payment_mode !== order.mode}
                            onClick={() => run(async () => { await api(`/workshop/refunds/${order.refund!.id}/refresh`, { method: "POST" }); })}>
                            查询退款状态
                          </button>
                        </>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
          <form className={styles.form} onSubmit={createJob}>
            <label>
              角色名字
              <input
                name="name"
                required
                maxLength={40}
                placeholder="为伙伴取一个名字"
              />
            </label>
            <label>
              角色人设
              <textarea
                name="persona"
                required
                maxLength={1000}
                placeholder="性格、表达风格，以及你希望怎样一起学习"
              />
            </label>
            <div className={styles.twoColumns}>
              <label>
                对你的称呼
                <input
                  name="address"
                  required
                  maxLength={40}
                  defaultValue="同学"
                />
              </label>
              <label>
                演示立绘
                <select name="demo_template">
                  <option value="shiori">小栞 · 温柔伙伴</option>
                  <option value="haruka">遥 · 推理搭档</option>
                  <option value="rin">凛 · 活力同伴</option>
                </select>
              </label>
            </div>
            <label>
              外观偏好
              <input
                name="appearance"
                maxLength={400}
                placeholder="服装、发色与姿态偏好"
              />
            </label>
            <label>
              选择参考图
              <select
                aria-label="生成参考图"
                value={referenceId}
                onChange={(e) => setReferenceId(e.target.value)}
              >
                <option value="">请选择已审核参考图</option>
                {references.map((ref, index) => (
                  <option key={ref.id} value={ref.id}>
                    参考图 {index + 1} · {statusLabels[ref.status]}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="primary"
              disabled={
                busy ||
                order?.entitlement?.status !== "available" ||
                (product?.image_mode !== "mock" && order?.mode !== "alipay_live") ||
                reference?.status !== "approved"
              }
            >
              <Sparkles size={16} /> 开始生成角色包
            </button>
            <small className="fine-print">
              选择已审核参考图及可用权益后开始。失败会恢复一次生成权益，每个任务最多尝试3次。
              {product?.image_mode !== "mock" && order?.mode !== "alipay_live" && "演示与沙箱权益不能用于真实角色生成，请使用正式付款环境。"}
            </small>
          </form>
        </section>
      </div>
      <section className={styles.section}>
        <div className="section-title">
          <h2>生成任务</h2>
          <button
            className="text-button"
            disabled={busy}
            onClick={() => run(refresh)}
          >
            <RefreshCw size={14} /> 刷新状态
          </button>
        </div>
        {!jobs.length && (
          <div className="empty">
            创建订单并完成相应付款流程后，即可开始第一个角色任务。
          </div>
        )}
        <div className={styles.jobs}>
          {jobs.map((job) => (
            <article className="panel" key={job.id}>
              <div>
                <h3>{job.name}</h3>
                <span>
                  {job.mode === "mock" ? "Mock · " : ""}
                  {statusLabels[job.status]}
                </span>
              </div>
              <p>
                已尝试 {job.attempts} / {job.max_attempts} 次
              </p>
              {job.error && <p className="error-text">{job.error}</p>}
              {job.status === "failed" && job.attempts < job.max_attempts && (
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      await api(`/workshop/jobs/${job.id}/retry`, {
                        method: "POST",
                      });
                    })
                  }
                >
                  重试生成任务
                </button>
              )}
              <ol className={styles.workflow}>
                {["queued", "generating", "reviewing", "complete"].map(
                  (status) => (
                    <li
                      key={status}
                      className={job.status === status ? styles.current : ""}
                    >
                      {statusLabels[status]}
                    </li>
                  ),
                )}
              </ol>
            </article>
          ))}
        </div>
      </section>
      <section className={styles.section}>
        <div className="section-title">
          <h2>我的角色库</h2>
          <button
            className="text-button"
            disabled={busy}
            onClick={() =>
              run(async () => {
                await api("/workshop/selection", {
                  method: "PUT",
                  body: JSON.stringify({ character_id: null }),
                });
                await onCatalogChanged();
              })
            }
          >
            使用剧情预设阵容
          </button>
        </div>
        <div className={styles.library}>
          {characters.map((character) => (
            <article className="panel" key={character.id}>
              <div className={styles.portrait}>
                <img src={character.assets[0]?.url} alt={character.name} />
                <span>
                  {character.mode === "mock" ? "Mock 演示角色" : "已审核角色"}
                </span>
              </div>
              <h3>{character.name}</h3>
              <p>{character.persona}</p>
              <details>
                <summary>角色包素材 · {character.assets.length}项</summary>
                <ul>
                  {character.assets.map((asset, index) => (
                    <li key={index}>
                      <a href={asset.url} download>
                        {asset.label}
                      </a>
                      {asset.placeholder && <small>共用演示立绘占位</small>}
                    </li>
                  ))}
                </ul>
              </details>
              <div className={styles.actions}>
                <button
                  className="secondary"
                  disabled={busy || selectedCharacterId === character.id}
                  onClick={() =>
                    run(async () => {
                      await api("/workshop/selection", {
                        method: "PUT",
                        body: JSON.stringify({ character_id: character.id }),
                      });
                      await onCatalogChanged();
                    })
                  }
                >
                  {selectedCharacterId === character.id
                    ? "当前陪学角色"
                    : "设为陪学角色"}
                </button>
                <button
                  className="text-button"
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      await api("/workshop/characters/" + character.id, {
                        method: "DELETE",
                      });
                      await onCatalogChanged();
                    })
                  }
                >
                  删除角色
                </button>
              </div>
            </article>
          ))}
        </div>
        {!characters.length && (
          <div className="empty">
            角色包审核交付后，会保存在这里。选择后可用于故事剧场和悬浮陪学。
          </div>
        )}
      </section>
    </>
  );
}
