import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Cpu, Loader2, RefreshCcw, ShieldCheck } from "lucide-react";

import { api, type SemiconductorHealth, type SemiconductorQuote } from "@/lib/api";
import { cn } from "@/lib/utils";

const SEGMENTS = [
  "制造/代工",
  "半导体设备",
  "材料/零部件",
  "设计/IP/AI",
  "封测/先进封装",
  "EDA/FPGA",
];

const CHAINS = [
  { title: "制造 / 代工", text: "产能利用率、先进制程进展、客户结构和资本开支纪律。", tags: ["中芯国际", "华虹公司", "晶合集成"] },
  { title: "半导体设备", text: "订单、客户复购、验收周期和平台化扩品类。", tags: ["北方华创", "中微公司", "拓荆科技"] },
  { title: "材料 / 零部件", text: "验证周期、导入份额、良率影响和海外替代空间。", tags: ["安集科技", "江丰电子", "沪硅产业"] },
  { title: "设计 / IP / AI", text: "产品迭代、客户粘性、生态迁移和单位经济性。", tags: ["寒武纪", "澜起科技", "韦尔股份"] },
  { title: "封测 / 先进封装", text: "稼动率、先进封装产能、客户集中度和价格弹性。", tags: ["长电科技", "通富微电", "华天科技"] },
  { title: "EDA / FPGA", text: "工具链验证、授权模式、国产生态适配和研发效率。", tags: ["华大九天", "概伦电子", "安路科技"] },
];

const EVIDENCE = [
  ["产业链位置", "是否位于国产替代、AI 算力、先进封装或成熟制程扩产的关键节点。"],
  ["订单证据", "合同负债、发出商品、客户验证和头部客户复购能否互相印证。"],
  ["技术证据", "良率、性能、制程节点、平台化能力是否能解释份额提升。"],
  ["财务证据", "毛利率、费用率、现金流和存货周转是否支持增长质量。"],
  ["估值证据", "盈利预测、订单覆盖和情景估值能否形成可证伪区间。"],
];

function number(value: number | null, digits = 2): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("zh-CN", { maximumFractionDigits: digits });
}

function money(value: number | null): string {
  if (value === null || value === undefined) return "—";
  if (Math.abs(value) >= 1e8) return `${number(value / 1e8)} 亿`;
  if (Math.abs(value) >= 1e4) return `${number(value / 1e4)} 万`;
  return number(value);
}

function statusText(health: SemiconductorHealth | null): string {
  if (!health) return "检测数据源中";
  if (health.ifind_configured) return "iFinD 已配置，刷新优先使用 iFinD";
  if (health.wind_cli) return "iFinD 未配置，刷新将尝试 Wind";
  return "数据源未就绪";
}

export function SemiconductorResearch() {
  const [health, setHealth] = useState<SemiconductorHealth | null>(null);
  const [rows, setRows] = useState<SemiconductorQuote[]>([]);
  const [segment, setSegment] = useState("");
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [successCount, setSuccessCount] = useState(0);
  const [errorCount, setErrorCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.getSemiconductorHealth()
      .then((next) => { if (alive) setHealth(next); })
      .catch((err: unknown) => {
        if (alive) setError(err instanceof Error ? err.message : "数据源检测失败");
      });
    return () => { alive = false; };
  }, []);

  const visibleRows = useMemo(
    () => rows.filter((row) => !segment || row.segment === segment),
    [rows, segment],
  );

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const payload = await api.getSemiconductorQuotes();
      setRows(payload.rows || []);
      setUpdatedAt(payload.updated_at);
      setSuccessCount(payload.success_count);
      setErrorCount(payload.error_count);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "半导体数据刷新失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-6 md:px-8">
      <section className="overflow-hidden rounded-2xl border border-border/70 bg-card">
        <div className="border-b border-border/70 bg-background/70 px-6 py-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div className="space-y-3">
              <div className="inline-flex items-center gap-2 rounded-full border border-border/70 bg-background px-3 py-1 text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
                <Cpu className="h-3.5 w-3.5" />
                Semiconductor Research
              </div>
              <div>
                <h1 className="text-3xl font-semibold tracking-tight">半导体行业研究</h1>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
                  覆盖制造、设备、材料、设计、封测和 EDA，围绕产业链位置、订单、技术、财务和估值五条证据链做中长期跟踪。
                </p>
              </div>
            </div>

            <div className="flex flex-col gap-3 lg:items-end">
              <div className="rounded-xl border border-border/70 bg-background px-4 py-3 text-sm">
                <div className="flex items-center gap-2 font-medium">
                  {loading ? (
                    <Loader2 className="h-4 w-4 animate-spin text-primary" />
                  ) : (
                    <ShieldCheck className="h-4 w-4 text-primary" />
                  )}
                  {loading ? "正在刷新半导体数据" : statusText(health)}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {updatedAt
                    ? `更新时间 ${new Date(updatedAt).toLocaleString("zh-CN")} · 成功 ${successCount} · 失败 ${errorCount}`
                    : "点击刷新后从主后端读取行情与估值字段"}
                </p>
              </div>
              <button
                type="button"
                disabled={loading}
                onClick={() => void refresh()}
                className="inline-flex items-center justify-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />}
                刷新全部数据
              </button>
            </div>
          </div>
        </div>

        <div className="grid gap-3 border-b border-border/70 bg-background/50 px-6 py-4 md:grid-cols-3">
          <div>
            <div className="text-2xl font-semibold">6</div>
            <div className="text-xs text-muted-foreground">核心产业链环节</div>
          </div>
          <div>
            <div className="text-2xl font-semibold">25</div>
            <div className="text-xs text-muted-foreground">跟踪公司池</div>
          </div>
          <div>
            <div className="text-2xl font-semibold">5</div>
            <div className="text-xs text-muted-foreground">证据链评分维度</div>
          </div>
        </div>
      </section>

      {error ? (
        <div className="flex items-start gap-3 rounded-2xl border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>{error}</div>
        </div>
      ) : null}

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {CHAINS.map((item) => (
          <article key={item.title} className="rounded-2xl border border-border/70 bg-card p-5">
            <h2 className="text-base font-semibold">{item.title}</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.text}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              {item.tags.map((tag) => (
                <span key={tag} className="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground">
                  {tag}
                </span>
              ))}
            </div>
          </article>
        ))}
      </section>

      <section className="grid gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
        <div className="rounded-2xl border border-border/70 bg-card p-5">
          <h2 className="text-lg font-semibold">五条证据链</h2>
          <div className="mt-4 space-y-3">
            {EVIDENCE.map(([title, text], index) => (
              <div key={title} className="rounded-xl border border-border/70 bg-background/70 p-4">
                <div className="text-xs font-medium uppercase tracking-wide text-primary">
                  {String(index + 1).padStart(2, "0")} / 15分
                </div>
                <div className="mt-1 font-medium">{title}</div>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">{text}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="overflow-hidden rounded-2xl border border-border/70 bg-card">
          <div className="flex flex-col gap-3 border-b border-border/70 px-5 py-4 md:flex-row md:items-end md:justify-between">
            <div>
              <h2 className="text-lg font-semibold">公司数据跟踪</h2>
              <p className="mt-1 text-xs text-muted-foreground">
                行情、成交额、市值、PE 和 PB 仅用于研究辅助，正式结论需回到终端原始口径复核。
              </p>
            </div>
            <select
              value={segment}
              onChange={(event) => setSegment(event.target.value)}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none transition focus:border-primary/50 focus:ring-2 focus:ring-primary/20 md:w-48"
              aria-label="产业链环节"
            >
              <option value="">全部环节</option>
              {SEGMENTS.map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[920px] text-left text-sm">
              <thead className="bg-muted/60 text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">环节</th>
                  <th className="px-4 py-3 font-medium">公司</th>
                  <th className="px-4 py-3 font-medium">代码</th>
                  <th className="px-4 py-3 font-medium">现价</th>
                  <th className="px-4 py-3 font-medium">涨跌幅</th>
                  <th className="px-4 py-3 font-medium">成交额</th>
                  <th className="px-4 py-3 font-medium">市值</th>
                  <th className="px-4 py-3 font-medium">PE(TTM)</th>
                  <th className="px-4 py-3 font-medium">PB</th>
                  <th className="px-4 py-3 font-medium">来源</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {visibleRows.length === 0 ? (
                  <tr>
                    <td colSpan={10} className="px-4 py-10 text-center text-muted-foreground">
                      {rows.length === 0 ? "点击“刷新全部数据”加载公司池。" : "暂无匹配数据"}
                    </td>
                  </tr>
                ) : (
                  visibleRows.map((row) => {
                    const direction = (row.change_pct ?? 0) > 0 ? "up" : (row.change_pct ?? 0) < 0 ? "down" : "";
                    return (
                      <tr key={row.code} title={row.error || undefined} className="hover:bg-muted/40">
                        <td className="px-4 py-3 text-muted-foreground">{row.segment}</td>
                        <td className="px-4 py-3 font-medium">{row.name}</td>
                        <td className="px-4 py-3 text-muted-foreground">{row.code}</td>
                        <td className="px-4 py-3">{number(row.price)}</td>
                        <td className={cn(
                          "px-4 py-3 font-medium",
                          direction === "up" && "text-success",
                          direction === "down" && "text-danger",
                        )}>
                          {row.change_pct == null ? "—" : `${number(row.change_pct)}%`}
                        </td>
                        <td className="px-4 py-3">{money(row.amount)}</td>
                        <td className="px-4 py-3">{money(row.market_cap)}</td>
                        <td className="px-4 py-3">{number(row.pe_ttm)}</td>
                        <td className="px-4 py-3">{number(row.pb)}</td>
                        <td className="px-4 py-3">
                          {row.error ? (
                            <span className="rounded-full bg-danger/10 px-2 py-1 text-xs font-medium text-danger">失败</span>
                          ) : (
                            <span className="rounded-full bg-primary/10 px-2 py-1 text-xs font-medium text-primary">{row.source}</span>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <footer className="pb-6 text-center text-xs tracking-wide text-muted-foreground">
        数据刷新仅用于研究辅助，不构成交易建议
      </footer>
    </div>
  );
}
