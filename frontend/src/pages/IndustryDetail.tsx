import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AlertTriangle, ArrowLeft, BookOpenText, CheckCircle2, Database, Layers3, RefreshCw, ShieldAlert, TrendingUp, UsersRound } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { api, type IndustrySummary, type SemiconductorQuote } from "@/lib/api";
import { analyzeIndustryReport, type ReportTable } from "@/lib/industryReport";

function quote(value: number | null): string {
  return value == null ? "—" : value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}

function column(table: ReportTable, name: string): number {
  return table.headers.findIndex((header) => header.includes(name));
}

function read(row: string[], index: number): string {
  return index < 0 ? "—" : row[index] || "—";
}

function DataTable({ table, compact = false }: { table: ReportTable; compact?: boolean }) {
  if (!table.rows.length) return <p className="text-sm text-muted-foreground">该报告暂未提供可视化表格数据。</p>;
  return <div className="overflow-x-auto"><table className="min-w-full text-sm"><thead className="bg-muted/40 text-left text-xs font-medium text-muted-foreground"><tr>{table.headers.map((header) => <th key={header} className="whitespace-nowrap px-4 py-3 first:pl-0 last:pr-0">{header}</th>)}</tr></thead><tbody>{table.rows.map((row, rowIndex) => <tr key={`${row[0]}-${rowIndex}`} className="border-t border-border/70 align-top"><>{row.map((cell, cellIndex) => <td key={`${cell}-${cellIndex}`} className={`${compact ? "py-2.5" : "py-3"} px-4 leading-6 first:pl-0 last:pr-0 ${cellIndex === 0 ? "font-medium text-foreground" : "text-muted-foreground"}`}>{cell}</td>)}</></tr>)}</tbody></table></div>;
}

function Allocation({ table }: { table: ReportTable }) {
  const weightIndex = column(table, "权重");
  const directionIndex = column(table, "方向");
  const companyIndex = column(table, "代表公司");
  if (!table.rows.length || weightIndex < 0) return null;
  return <section className="rounded-2xl border border-border/70 bg-card p-6 lg:col-span-5"><h2 className="flex items-center gap-2 text-sm font-medium"><TrendingUp className="h-4 w-4 text-primary" /> 组合结构</h2><div className="mt-5 space-y-4">{table.rows.map((row) => { const weight = Number.parseFloat(read(row, weightIndex)) || 0; return <div key={`${read(row, directionIndex)}-${read(row, weightIndex)}`}><div className="flex items-baseline justify-between gap-4 text-sm"><span className="font-medium">{read(row, directionIndex)}</span><span className="shrink-0 tabular-nums text-muted-foreground">{read(row, weightIndex)}</span></div><div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary transition-[width] duration-700" style={{ width: `${Math.min(weight * 3.5, 100)}%` }} /></div><p className="mt-1 text-xs text-muted-foreground">{read(row, companyIndex)}</p></div>; })}</div></section>;
}

function ChainCards({ table }: { table: ReportTable }) {
  const segment = column(table, "环节");
  const bottleneck = column(table, "核心卡点");
  const technology = column(table, "核心科技");
  const valuation = column(table, "估值方法");
  const companies = column(table, "代表公司");
  if (!table.rows.length) return null;
  return <section className="mt-6"><div className="flex items-center gap-2 text-lg font-semibold tracking-[-0.02em]"><Layers3 className="h-4 w-4 text-primary" /> 产业链卡位</div><p className="mt-1 text-sm text-muted-foreground">从成本、技术与估值锚理解每个环节的投资逻辑。</p><div className="mt-4 grid grid-flow-dense gap-3 md:grid-cols-2 xl:grid-cols-4">{table.rows.map((row) => <article key={read(row, segment)} className="group rounded-xl border border-border/70 bg-card p-5 transition-colors hover:border-primary/40 hover:bg-muted/20"><h3 className="font-semibold">{read(row, segment)}</h3><dl className="mt-4 space-y-3 text-xs leading-5"><div><dt className="text-muted-foreground">核心卡点</dt><dd className="mt-0.5 text-foreground">{read(row, bottleneck)}</dd></div><div><dt className="text-muted-foreground">技术 / 能力</dt><dd className="mt-0.5 text-foreground">{read(row, technology)}</dd></div><div><dt className="text-muted-foreground">估值锚</dt><dd className="mt-0.5 text-foreground">{read(row, valuation)}</dd></div></dl><p className="mt-4 border-t border-border/70 pt-3 text-xs text-muted-foreground">{read(row, companies)}</p></article>)}</div></section>;
}

function Tiers({ table }: { table: ReportTable }) {
  const tier = column(table, "梯队");
  const companies = column(table, "公司");
  const position = column(table, "产业链定位");
  const reason = column(table, "入选理由");
  if (!table.rows.length) return null;
  return <section className="rounded-2xl border border-border/70 bg-card p-6 lg:col-span-7"><div className="flex items-center gap-2 text-sm font-medium"><UsersRound className="h-4 w-4 text-primary" /> 公司梯队</div><div className="mt-4 divide-y divide-border/70">{table.rows.map((row, index) => <div key={`${read(row, tier)}-${index}`} className="grid gap-2 py-4 sm:grid-cols-[86px_minmax(0,1fr)]"><div className="text-xs font-medium text-primary">{read(row, tier)}</div><div><div className="font-medium">{read(row, companies)}</div><p className="mt-1 text-xs text-muted-foreground">{read(row, position)}</p><p className="mt-2 text-sm leading-6 text-muted-foreground">{read(row, reason)}</p></div></div>)}</div></section>;
}

function Triggers({ triggers }: { triggers: ReturnType<typeof analyzeIndustryReport>["triggers"] }) {
  const blocks = [{ title: "证伪条件", rows: triggers.falsify, color: "text-danger" }, { title: "加仓触发器", rows: triggers.add, color: "text-primary" }, { title: "降仓触发器", rows: triggers.reduce, color: "text-warning" }];
  return <section className="mt-6 grid gap-3 lg:grid-cols-3">{blocks.map((block) => <article key={block.title} className="rounded-2xl border border-border/70 bg-card p-5"><h2 className={`text-sm font-semibold ${block.color}`}>{block.title}</h2><ol className="mt-4 space-y-3 text-sm leading-6 text-muted-foreground">{block.rows.length ? block.rows.map((item, index) => <li key={item} className="flex gap-3"><span className="shrink-0 text-foreground/60">{index + 1}</span><span>{item}</span></li>) : <li>该报告未列示相关触发条件。</li>}</ol></article>)}</section>;
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
    void api.getIndustries().then((payload) => { if (alive) setIndustry(payload.industries.find((item) => item.slug === slug) ?? null); });
    void api.getIndustryReport(slug).then((payload) => { if (alive) setReport(payload.content); });
    return () => { alive = false; };
  }, [slug]);

  const dashboard = useMemo(() => analyzeIndustryReport(report), [report]);
  const segments = useMemo(() => [...new Set(rows.map((row) => row.segment))], [rows]);
  const visibleRows = useMemo(() => rows.filter((row) => !segment || row.segment === segment), [rows, segment]);

  async function refresh() {
    setLoading(true); setError(null);
    try { const payload = await api.getIndustryQuotes(slug); setRows(payload.rows); setUpdatedAt(payload.updated_at); setSegment(""); }
    catch (err: unknown) { setError(err instanceof Error ? err.message : "当前行业数据刷新失败"); }
    finally { setLoading(false); }
  }

  if (!industry) return <div className="p-8 text-muted-foreground">加载行业研究框架…</div>;

  return <main className="mx-auto w-full max-w-7xl overflow-x-hidden px-4 py-6 md:px-8 md:py-8">
    <Link to="/industry-research" className="inline-flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground"><ArrowLeft className="h-4 w-4" /> 行业研究中心</Link>
    <section className="mt-5 overflow-hidden rounded-2xl border border-border/70 bg-card"><div className="grid gap-6 px-6 py-7 lg:grid-cols-[minmax(0,1fr)_300px] lg:items-end lg:px-8"><div><p className="text-sm font-medium text-primary">行业研究</p><h1 className="mt-2 max-w-5xl text-3xl font-semibold tracking-[-0.035em] text-balance md:text-4xl">{industry.name}</h1><p className="mt-3 max-w-3xl text-sm leading-7 text-muted-foreground">{dashboard.conclusion || industry.summary}</p></div>{industry.refreshable ? <div className="rounded-xl border border-border/70 bg-background/70 p-4"><div className="flex items-center gap-2 text-sm font-medium"><Database className="h-4 w-4 text-primary" /> 公司数据 · 当前行业</div><p className="mt-1 text-xs leading-5 text-muted-foreground">{updatedAt ? `更新于 ${new Date(updatedAt).toLocaleString("zh-CN")}` : "行情仅在当前行业范围刷新"}</p><button type="button" onClick={() => void refresh()} disabled={loading} className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-md bg-foreground px-4 py-2.5 text-sm font-medium text-background transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"><RefreshCw className={loading ? "h-4 w-4 animate-spin" : "h-4 w-4"} />{loading ? "正在刷新" : `刷新${industry.name}行情`}</button></div> : null}</div><div className="grid border-t border-border/70 bg-muted/20 sm:grid-cols-3"><div className="px-6 py-4 text-sm"><span className="block text-xs text-muted-foreground">报告日期</span><span className="mt-1 block font-medium">{dashboard.date ?? "—"}</span></div><div className="border-t border-border/70 px-6 py-4 text-sm sm:border-l sm:border-t-0"><span className="block text-xs text-muted-foreground">研究结构</span><span className="mt-1 block font-medium">结论、产业链、机会与风控</span></div><div className="border-t border-border/70 px-6 py-4 text-sm sm:border-l sm:border-t-0"><span className="block text-xs text-muted-foreground">行情范围</span><span className="mt-1 block font-medium">{industry.refreshable ? "支持单行业刷新" : "公司池待接入"}</span></div></div></section>
    {error ? <div className="mt-5 flex items-start gap-3 rounded-xl border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{error}</div> : null}
    <section className="mt-6 grid grid-flow-dense gap-4 lg:grid-cols-12"><article className="rounded-2xl border border-border/70 bg-card p-6 lg:col-span-7"><h2 className="flex items-center gap-2 text-sm font-medium"><BookOpenText className="h-4 w-4 text-primary" /> 核心结论</h2><p className="mt-4 max-w-3xl text-[15px] leading-8 text-foreground">{dashboard.conclusion || "正在提取报告核心结论…"}</p></article><article className="rounded-2xl border border-border/70 bg-card p-6 lg:col-span-5"><h2 className="flex items-center gap-2 text-sm font-medium"><CheckCircle2 className="h-4 w-4 text-primary" /> Vibe 审查</h2><div className="mt-4"><DataTable table={dashboard.review} compact /></div></article>{dashboard.allocation.rows.length ? <Allocation table={dashboard.allocation} /> : null}<article className="rounded-2xl border border-border/70 bg-card p-6 lg:col-span-7"><h2 className="flex items-center gap-2 text-sm font-medium"><ShieldAlert className="h-4 w-4 text-primary" /> 投资机会排序</h2><div className="mt-4"><DataTable table={dashboard.opportunities} compact /></div></article></section>
    <ChainCards table={dashboard.chain} />
    <section className="mt-6 grid gap-4 lg:grid-cols-12"><Tiers table={dashboard.companies} /><article className="rounded-2xl border border-border/70 bg-card p-6 lg:col-span-5"><div className="text-sm font-medium">研究使用方式</div><p className="mt-4 text-sm leading-7 text-muted-foreground">先用组合权重和机会排序确定研究优先级，再用产业链卡点验证逻辑，最后以公司梯队和行情数据确认个股落点。完整报告保留在底部作为原始依据。</p></article></section>
    <Triggers triggers={dashboard.triggers} />
    {industry.refreshable ? <section className="mt-6 overflow-hidden rounded-2xl border border-border/70 bg-card"><div className="flex flex-col gap-3 border-b border-border/70 px-6 py-5 sm:flex-row sm:items-end sm:justify-between"><div><h2 className="text-lg font-semibold tracking-[-0.02em]">公司数据跟踪</h2><p className="mt-1 text-sm text-muted-foreground">点击刷新后仅更新 {industry.name} 公司池。</p></div>{rows.length ? <span className="text-sm text-muted-foreground">已加载 {rows.length} 家公司</span> : null}</div>{segments.length ? <div className="flex gap-2 overflow-x-auto border-b border-border/70 px-6 py-3"><button type="button" onClick={() => setSegment("")} className={`shrink-0 rounded-md px-3 py-1.5 text-xs font-medium ${!segment ? "bg-foreground text-background" : "bg-muted text-muted-foreground hover:text-foreground"}`}>全部</button>{segments.map((item) => <button type="button" key={item} onClick={() => setSegment(item)} className={`shrink-0 rounded-md px-3 py-1.5 text-xs font-medium ${segment === item ? "bg-foreground text-background" : "bg-muted text-muted-foreground hover:text-foreground"}`}>{item}</button>)}</div> : null}<div className="overflow-x-auto"><table className="min-w-full text-sm"><thead className="bg-muted/40 text-left text-xs font-medium text-muted-foreground"><tr><th className="px-6 py-3">产业链环节</th><th className="px-4 py-3">公司</th><th className="px-4 py-3">代码</th><th className="px-4 py-3 text-right">最新价</th><th className="px-6 py-3 text-right">涨跌幅</th></tr></thead><tbody>{visibleRows.length ? visibleRows.map((row) => <tr key={row.code} className="border-t border-border/70 transition-colors hover:bg-muted/30"><td className="px-6 py-3 text-muted-foreground">{row.segment}</td><td className="px-4 py-3 font-medium">{row.name}</td><td className="px-4 py-3 text-muted-foreground">{row.code}</td><td className="px-4 py-3 text-right tabular-nums">{quote(row.price)}</td><td className={`px-6 py-3 text-right tabular-nums ${row.change_pct != null && row.change_pct > 0 ? "text-danger" : row.change_pct != null && row.change_pct < 0 ? "text-success" : ""}`}>{row.change_pct == null ? "—" : `${row.change_pct > 0 ? "+" : ""}${row.change_pct.toFixed(2)}%`}</td></tr>) : <tr><td colSpan={5} className="px-6 py-12 text-center text-sm text-muted-foreground">点击上方按钮加载当前行业公司池。</td></tr>}</tbody></table></div></section> : null}
    <details className="mt-6 rounded-2xl border border-border/70 bg-card"><summary className="cursor-pointer list-none px-6 py-5 text-sm font-medium marker:content-none">完整深度投研报告<span className="ml-2 text-xs font-normal text-muted-foreground">保留原始章节、表格与全部内容</span></summary><div className="border-t border-border/70 px-6 py-7"><div className="prose prose-slate max-w-none dark:prose-invert"><ReactMarkdown remarkPlugins={[remarkGfm]}>{report || "正在加载深度投研报告…"}</ReactMarkdown></div></div></details>
  </main>;
}
