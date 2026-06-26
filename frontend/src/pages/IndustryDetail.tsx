import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AlertTriangle, ArrowLeft, BookOpenText, CheckCircle2, Database, Layers3, RefreshCw } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { api, type IndustrySummary, type SemiconductorQuote } from "@/lib/api";

function reportSection(report: string, names: string[]): string {
  const match = report.match(new RegExp(`^##\\s*(?:${names.join("|")}).*?\\n([\\s\\S]*?)(?=^##\\s|\\s*$)`, "m"));
  return match?.[1].trim() ?? "";
}

function openingParagraph(report: string): string {
  const content = report.replace(/^#.*$/m, "").trim();
  return content.split(/\n\s*\n/).find((part) => part.trim() && !part.trim().startsWith("#"))?.trim() ?? "";
}

function quote(value: number | null): string {
  return value == null ? "—" : value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}

export function IndustryDetail() {
  const { slug = "" } = useParams();
  const [industry, setIndustry] = useState<IndustrySummary | null>(null);
  const [rows, setRows] = useState<SemiconductorQuote[]>([]);
  const [report, setReport] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [segment, setSegment] = useState("");

  useEffect(() => {
    let alive = true;
    void api.getIndustries().then((payload) => {
      if (alive) setIndustry(payload.industries.find((item) => item.slug === slug) ?? null);
    });
    void api.getIndustryReport(slug).then((payload) => {
      if (alive) setReport(payload.content);
    });
    return () => { alive = false; };
  }, [slug]);

  const segments = useMemo(() => [...new Set(rows.map((row) => row.segment))], [rows]);
  const visibleRows = useMemo(() => rows.filter((row) => !segment || row.segment === segment), [rows, segment]);
  const conclusion = reportSection(report, ["核心结论", "投资结论", "投资要点"]) || openingParagraph(report);
  const chain = reportSection(report, ["产业链分层", "产业链", "产业链结构"]);
  const evidence = reportSection(report, ["证据链", "跟踪框架", "跟踪要点"]);
  const risks = reportSection(report, ["风险提示", "主要风险"]);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const payload = await api.getIndustryQuotes(slug);
      setRows(payload.rows);
      setUpdatedAt(payload.updated_at);
      setSegment("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "当前行业数据刷新失败");
    } finally {
      setLoading(false);
    }
  }

  if (!industry) return <div className="p-8 text-muted-foreground">加载行业研究框架…</div>;

  return (
    <main className="mx-auto w-full max-w-7xl overflow-x-hidden px-4 py-6 md:px-8 md:py-8">
      <Link to="/industry-research" className="inline-flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> 行业研究中心
      </Link>

      <section className="mt-5 overflow-hidden rounded-2xl border border-border/70 bg-card">
        <div className="grid gap-6 px-6 py-7 lg:grid-cols-[minmax(0,1fr)_300px] lg:items-end lg:px-8">
          <div>
            <p className="text-sm font-medium text-primary">行业研究</p>
            <h1 className="mt-2 max-w-5xl text-3xl font-semibold tracking-[-0.035em] text-balance md:text-4xl">{industry.name}行业研究</h1>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-muted-foreground">{industry.summary}</p>
          </div>
          {industry.refreshable ? (
            <div className="rounded-xl border border-border/70 bg-background/70 p-4">
              <div className="flex items-center gap-2 text-sm font-medium"><Database className="h-4 w-4 text-primary" /> 公司数据 · 当前行业</div>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">{updatedAt ? `更新于 ${new Date(updatedAt).toLocaleString("zh-CN")}` : "行情仅在当前行业范围刷新"}</p>
              <button type="button" onClick={() => void refresh()} disabled={loading} className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-md bg-foreground px-4 py-2.5 text-sm font-medium text-background transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50">
                <RefreshCw className={loading ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
                {loading ? "正在刷新" : `刷新${industry.name}行情`}
              </button>
            </div>
          ) : null}
        </div>
        <div className="grid border-t border-border/70 bg-muted/20 sm:grid-cols-3">
          <div className="px-6 py-4 text-sm"><span className="block text-xs text-muted-foreground">研究内容</span><span className="mt-1 block font-medium">产业链、证据链与公司跟踪</span></div>
          <div className="border-t border-border/70 px-6 py-4 text-sm sm:border-l sm:border-t-0"><span className="block text-xs text-muted-foreground">报告状态</span><span className="mt-1 block font-medium">深度投研框架已加载</span></div>
          <div className="border-t border-border/70 px-6 py-4 text-sm sm:border-l sm:border-t-0"><span className="block text-xs text-muted-foreground">行情范围</span><span className="mt-1 block font-medium">{industry.refreshable ? "支持单行业刷新" : "公司池待接入"}</span></div>
        </div>
      </section>

      {error ? <div className="mt-5 flex items-start gap-3 rounded-xl border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{error}</div> : null}

      <section className="mt-6 grid grid-flow-dense gap-4 lg:grid-cols-12">
        <article className="rounded-2xl border border-border/70 bg-card p-6 lg:col-span-8">
          <div className="flex items-center gap-2 text-sm font-medium"><BookOpenText className="h-4 w-4 text-primary" /> 核心结论</div>
          <div className="mt-4 max-w-3xl text-[15px] leading-8 text-foreground [&_p]:mt-0 [&_ul]:my-4 [&_ul]:space-y-2">
            {conclusion ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{conclusion}</ReactMarkdown> : <p>正在提取报告中的核心结论…</p>}
          </div>
        </article>
        <aside className="rounded-2xl border border-border/70 bg-card p-6 lg:col-span-4">
          <div className="flex items-center gap-2 text-sm font-medium"><CheckCircle2 className="h-4 w-4 text-primary" /> 阅读顺序</div>
          <ol className="mt-4 space-y-3 text-sm leading-6 text-muted-foreground"><li><span className="mr-2 font-medium text-foreground">结论</span>先判断行业位置与关键变量。</li><li><span className="mr-2 font-medium text-foreground">证据</span>再确认订单、技术和财务信号。</li><li><span className="mr-2 font-medium text-foreground">数据</span>最后刷新公司池，观察市场反馈。</li></ol>
        </aside>
        <article className="rounded-2xl border border-border/70 bg-card p-6 lg:col-span-7">
          <div className="flex items-center gap-2 text-sm font-medium"><Layers3 className="h-4 w-4 text-primary" /> 产业链与证据链</div>
          <div className="mt-4 max-w-none text-sm leading-7 text-muted-foreground [&_h1]:hidden [&_h2]:hidden [&_p]:mt-0 [&_ul]:my-3 [&_table]:w-full [&_table]:text-left [&_th]:border-b [&_th]:border-border [&_th]:pb-2 [&_td]:border-b [&_td]:border-border/60 [&_td]:py-2">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{chain || evidence || "报告中的产业链及证据链内容将在此呈现。"}</ReactMarkdown>
          </div>
        </article>
        <article className="rounded-2xl border border-border/70 bg-card p-6 lg:col-span-5">
          <div className="text-sm font-medium">风险与验证</div>
          <div className="mt-4 text-sm leading-7 text-muted-foreground [&_p]:mt-0 [&_ul]:my-0 [&_ul]:space-y-2"><ReactMarkdown remarkPlugins={[remarkGfm]}>{risks || evidence || "关注报告中列示的关键变量，并在后续数据刷新中持续验证。"}</ReactMarkdown></div>
        </article>
      </section>

      {industry.refreshable ? <section className="mt-6 overflow-hidden rounded-2xl border border-border/70 bg-card">
        <div className="flex flex-col gap-3 border-b border-border/70 px-6 py-5 sm:flex-row sm:items-end sm:justify-between">
          <div><h2 className="text-lg font-semibold tracking-[-0.02em]">公司数据跟踪</h2><p className="mt-1 text-sm text-muted-foreground">点击刷新后仅更新 {industry.name} 公司池。</p></div>
          {rows.length ? <span className="text-sm text-muted-foreground">已加载 {rows.length} 家公司</span> : null}
        </div>
        {segments.length ? <div className="flex gap-2 overflow-x-auto border-b border-border/70 px-6 py-3"><button type="button" onClick={() => setSegment("")} className={`shrink-0 rounded-md px-3 py-1.5 text-xs font-medium ${!segment ? "bg-foreground text-background" : "bg-muted text-muted-foreground hover:text-foreground"}`}>全部</button>{segments.map((item) => <button type="button" key={item} onClick={() => setSegment(item)} className={`shrink-0 rounded-md px-3 py-1.5 text-xs font-medium ${segment === item ? "bg-foreground text-background" : "bg-muted text-muted-foreground hover:text-foreground"}`}>{item}</button>)}</div> : null}
        <div className="overflow-x-auto"><table className="min-w-full text-sm"><thead className="bg-muted/40 text-left text-xs font-medium text-muted-foreground"><tr><th className="px-6 py-3">产业链环节</th><th className="px-4 py-3">公司</th><th className="px-4 py-3">代码</th><th className="px-4 py-3 text-right">最新价</th><th className="px-6 py-3 text-right">涨跌幅</th></tr></thead><tbody>{visibleRows.length ? visibleRows.map((row) => <tr key={row.code} className="border-t border-border/70 transition-colors hover:bg-muted/30"><td className="px-6 py-3 text-muted-foreground">{row.segment}</td><td className="px-4 py-3 font-medium">{row.name}</td><td className="px-4 py-3 text-muted-foreground">{row.code}</td><td className="px-4 py-3 text-right tabular-nums">{quote(row.price)}</td><td className={`px-6 py-3 text-right tabular-nums ${row.change_pct != null && row.change_pct > 0 ? "text-danger" : row.change_pct != null && row.change_pct < 0 ? "text-success" : ""}`}>{row.change_pct == null ? "—" : `${row.change_pct > 0 ? "+" : ""}${row.change_pct.toFixed(2)}%`}</td></tr>) : <tr><td colSpan={5} className="px-6 py-12 text-center text-sm text-muted-foreground">点击上方按钮加载当前行业公司池。</td></tr>}</tbody></table></div>
      </section> : null}

      <details className="mt-6 rounded-2xl border border-border/70 bg-card">
        <summary className="cursor-pointer list-none px-6 py-5 text-sm font-medium marker:content-none">完整深度投研报告<span className="ml-2 text-xs font-normal text-muted-foreground">保留原始章节、表格与全部内容</span></summary>
        <div className="border-t border-border/70 px-6 py-7"><div className="prose prose-slate max-w-none dark:prose-invert"><ReactMarkdown remarkPlugins={[remarkGfm]}>{report || "正在加载深度投研报告…"}</ReactMarkdown></div></div>
      </details>
    </main>
  );
}
