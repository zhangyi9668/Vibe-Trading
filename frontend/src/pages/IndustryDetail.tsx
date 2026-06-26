import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import { api, type IndustrySummary, type SemiconductorQuote } from "@/lib/api";

export function IndustryDetail() {
  const { slug = "" } = useParams();
  const [industry, setIndustry] = useState<IndustrySummary | null>(null);
  const [rows, setRows] = useState<SemiconductorQuote[]>([]);
  const [loading, setLoading] = useState(false);
  useEffect(() => { void api.getIndustries().then((p) => setIndustry(p.industries.find((x) => x.slug === slug) ?? null)); }, [slug]);
  async function refresh() { setLoading(true); try { setRows((await api.getIndustryQuotes(slug)).rows); } finally { setLoading(false); } }
  if (!industry) return <div className="p-8 text-muted-foreground">加载行业研究框架…</div>;
  return <div className="mx-auto max-w-7xl px-8 py-8"><Link to="/industry-research" className="text-sm text-primary">← 行业研究中心</Link><div className="mt-5 flex items-end justify-between border-b border-border pb-6"><div><p className="text-sm font-medium text-primary">TRIAL INDUSTRY</p><h1 className="mt-2 text-3xl font-semibold">{industry.name}</h1><p className="mt-2 text-muted-foreground">{industry.summary}</p></div><button onClick={() => void refresh()} disabled={loading} className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"><RefreshCw className={loading ? "h-4 w-4 animate-spin" : "h-4 w-4"}/>刷新当前行业</button></div><section className="mt-6 overflow-hidden rounded-xl border border-border bg-card"><div className="border-b border-border px-5 py-4 font-medium">公司数据跟踪</div><table className="w-full text-sm"><thead className="bg-muted/50 text-left text-muted-foreground"><tr><th className="px-5 py-3">环节</th><th>公司</th><th>代码</th><th>现价</th><th>涨跌幅</th></tr></thead><tbody>{rows.length ? rows.map((r) => <tr key={r.code} className="border-t border-border"><td className="px-5 py-3">{r.segment}</td><td>{r.name}</td><td>{r.code}</td><td>{r.price ?? "—"}</td><td>{r.change_pct == null ? "—" : `${r.change_pct}%`}</td></tr>) : <tr><td colSpan={5} className="px-5 py-10 text-center text-muted-foreground">点击刷新当前行业加载公司池。</td></tr>}</tbody></table></section></div>;
}
