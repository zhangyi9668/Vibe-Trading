import { useEffect, useState } from "react";
import { ArrowUpRight, Cpu, Layers3, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import { api, type IndustrySummary } from "@/lib/api";

export function IndustryResearch() {
  const [industries, setIndustries] = useState<IndustrySummary[]>([]);

  useEffect(() => { void api.getIndustries().then((payload) => setIndustries(payload.industries)).catch(() => {}); }, []);

  return <div className="mx-auto max-w-7xl px-8 py-8">
    <header className="mb-8 flex items-end justify-between border-b border-border pb-6">
      <div><p className="text-sm font-medium text-primary">INDUSTRY RESEARCH</p><h1 className="mt-2 text-3xl font-semibold tracking-tight">行业研究中心</h1><p className="mt-2 text-sm text-muted-foreground">全部产业链框架直出；进入行业后查看研究框架与单行业数据。</p></div>
      <div className="text-right text-sm text-muted-foreground"><div className="text-2xl font-semibold text-foreground">{industries.length || 13}</div>产业链框架</div>
    </header>
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      <Link to="/semiconductor-research" className="group rounded-xl border border-primary/35 bg-primary/5 p-5 transition hover:border-primary/70 hover:bg-primary/10">
        <div className="flex items-start justify-between"><span className="rounded-md bg-primary/15 px-2 py-1 text-xs font-medium text-primary">实时工作台</span><ArrowUpRight className="h-4 w-4 text-muted-foreground transition group-hover:text-primary" /></div>
        <div className="mt-6 flex items-center gap-2"><Cpu className="h-4 w-4 text-primary" /><h2 className="text-lg font-semibold">半导体行业研究工作台</h2></div><p className="mt-2 min-h-10 text-sm leading-5 text-muted-foreground">保留原有行情刷新、产业链证据链与公司池跟踪页面。</p>
        <div className="mt-5 flex items-center gap-2 text-xs text-muted-foreground"><RefreshCw className="h-3.5 w-3.5 text-primary" />进入后刷新半导体行情</div>
      </Link>
      {industries.map((industry) => <Link key={industry.slug} to={`/industry-research/${industry.slug}`} className="group rounded-xl border border-border bg-card p-5 transition hover:border-primary/50 hover:bg-muted/30">
        <div className="flex items-start justify-between"><span className="rounded-md bg-primary/10 px-2 py-1 text-xs font-medium text-primary">{industry.refreshable ? "数据可刷新" : "框架已入库"}</span><ArrowUpRight className="h-4 w-4 text-muted-foreground transition group-hover:text-primary" /></div>
        <h2 className="mt-6 text-lg font-semibold">{industry.name}</h2><p className="mt-2 min-h-10 text-sm leading-5 text-muted-foreground">{industry.summary}</p>
        <div className="mt-5 flex items-center gap-2 text-xs text-muted-foreground">{industry.refreshable ? <RefreshCw className="h-3.5 w-3.5 text-primary" /> : <Layers3 className="h-3.5 w-3.5" />}{industry.refreshable ? "进入后刷新当前行业数据" : "研究框架待接入数据池"}</div>
      </Link>)}
    </div>
  </div>;
}
