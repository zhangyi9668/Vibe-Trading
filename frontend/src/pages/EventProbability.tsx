import { useDeferredValue, useEffect, useState } from "react";
import {
  AlertTriangle,
  Gauge,
  Loader2,
  RefreshCcw,
  Waves,
} from "lucide-react";

import { ProbabilityTrend } from "@/components/charts/ProbabilityTrend";
import {
  api,
  type EventProbabilityResult,
  type ProbabilityHistorySeriesRequest,
  type ProbabilityOverview,
  type ProbabilityRefreshState,
  type ProbabilitySource,
  type ProbabilityTopic,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const TOPIC_ORDER: ProbabilityTopic[] = [
  "monetary_policy",
  "macro_economy",
  "geopolitics",
  "political_elections",
  "indices_commodities",
  "ai_technology",
  "crypto",
  "sports",
  "entertainment",
  "other",
];

const TOPIC_LABELS: Record<ProbabilityTopic, string> = {
  monetary_policy: "货币政策",
  macro_economy: "宏观经济",
  geopolitics: "地缘政治",
  political_elections: "政治选举",
  indices_commodities: "指数与商品",
  ai_technology: "AI 科技",
  crypto: "加密市场",
  sports: "体育",
  entertainment: "娱乐",
  other: "其他",
};

const EMPTY_OVERVIEW: ProbabilityOverview = {
  as_of: null,
  events: [],
  sources: [],
  translation_cache_size: 0,
  refresh: {
    status: "idle",
    kind: null,
    stage: null,
    progress_current: 0,
    progress_total: 0,
    started_at: null,
    finished_at: null,
    error: null,
    translation: { new_translations: 0, cache_hits: 0, pending: 0 },
  },
};

const MAX_GROUPED_RESULTS = 5;

function formatPercent(value: number | null): string {
  if (value === null) {
    return "—";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function formatSignedPercent(value: number | null): string {
  if (value === null) {
    return "—";
  }
  const percentage = value * 100;
  const sign = percentage > 0 ? "+" : "";
  return `${sign}${percentage.toFixed(1)}%`;
}

function formatCompactNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

function sortResultsByVolume(results: EventProbabilityResult[]): EventProbabilityResult[] {
  return [...results].sort((left, right) => right.volume_24h - left.volume_24h);
}

function resultLabel(result: EventProbabilityResult): string {
  return result.label_zh || result.label;
}

function resultSeries(results: EventProbabilityResult[]): ProbabilityHistorySeriesRequest[] {
  return results
    .filter((result): result is EventProbabilityResult & { token_id: string } =>
      Boolean(result.token_id),
    )
    .map((result) => ({
      label: resultLabel(result),
      token_id: result.token_id,
    }));
}

function statusLabel(state: ProbabilityRefreshState): string {
  if (state.status === "running" || state.status === "queued") {
    return state.kind === "full" ? "全量刷新进行中" : "快速刷新进行中";
  }
  if (state.status === "error") {
    return "刷新异常";
  }
  if (state.status === "done") {
    return "数据已更新";
  }
  return "使用缓存快照";
}

function isRefreshActive(state: ProbabilityRefreshState): boolean {
  return state.status === "queued" || state.status === "running";
}

export function EventProbability() {
  const [overview, setOverview] = useState<ProbabilityOverview>(EMPTY_OVERVIEW);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [keyword, setKeyword] = useState("");
  const deferredKeyword = useDeferredValue(keyword);
  const [source, setSource] = useState<ProbabilitySource | "all">("all");
  const [topic, setTopic] = useState<ProbabilityTopic>("monetary_policy");
  const [minChange, setMinChange] = useState("0");

  useEffect(() => {
    let alive = true;
    api
      .getEventProbabilityOverview()
      .then((nextOverview) => {
        if (alive) {
          setOverview(nextOverview);
        }
      })
      .catch((err: unknown) => {
        if (alive) {
          setError(err instanceof Error ? err.message : "事件概率加载失败");
        }
      })
      .finally(() => {
        if (alive) {
          setLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!isRefreshActive(overview.refresh)) {
      return;
    }
    const timer = window.setInterval(() => {
      api
        .getEventProbabilityRefreshStatus()
        .then((refresh) => {
          setOverview((current) => ({ ...current, refresh }));
          if (refresh.status === "done" || refresh.status === "error") {
            return api.getEventProbabilityOverview().then((nextOverview) => {
              setOverview(nextOverview);
            });
          }
          return undefined;
        })
        .catch((err: unknown) => {
          setError(err instanceof Error ? err.message : "刷新状态获取失败");
        });
    }, 1500);
    return () => {
      window.clearInterval(timer);
    };
  }, [overview.refresh]);

  const availableTopics = TOPIC_ORDER.filter((topicKey) =>
    overview.events.some((row) => row.topic === topicKey),
  );

  useEffect(() => {
    if (availableTopics.length > 0 && !availableTopics.includes(topic)) {
      setTopic(availableTopics[0]);
    }
  }, [availableTopics, topic]);

  const filteredEvents = overview.events.filter((row) => {
    const normalizedKeyword = deferredKeyword.trim().toLowerCase();
    if (normalizedKeyword) {
      const haystack = [
        row.question,
        row.question_zh ?? "",
        row.pick_label ?? "",
      ]
        .join(" ")
        .toLowerCase();
      if (!haystack.includes(normalizedKeyword)) {
        return false;
      }
    }

    if (source !== "all" && row.source !== source) {
      return false;
    }
    if (row.topic !== topic) {
      return false;
    }

    const threshold = Number(minChange);
    if (threshold > 0) {
      const change = Math.abs(row.change_24h ?? 0);
      if (change < threshold) {
        return false;
      }
    }
    return true;
  }).sort((left, right) => right.volume_24h - left.volume_24h);

  async function startRefresh(kind: "quick" | "full") {
    try {
      const refresh = await api.startEventProbabilityRefresh(kind);
      setOverview((current) => ({ ...current, refresh }));
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "刷新启动失败");
    }
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-6 md:px-8">
      <section className="overflow-hidden rounded-3xl border border-border/60 bg-card">
        <div className="relative border-b border-border/70 bg-gradient-to-br from-primary/10 via-background to-info/10 px-6 py-8">
          <div className="absolute inset-y-0 right-0 w-48 bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.16),transparent_65%)]" />
          <div className="relative flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div className="space-y-3">
              <div className="inline-flex items-center gap-2 rounded-full border border-border/70 bg-background/80 px-3 py-1 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                <Gauge className="h-3.5 w-3.5" />
                Event Probability
              </div>
              <div>
                <h1 className="text-3xl font-semibold tracking-tight">事件概率</h1>
                <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
                  聚合 Polymarket 与 Kalshi 的公开预测市场，按模块观察宏观叙事、政策预期与风险温度。
                </p>
              </div>
            </div>

            <div className="flex flex-col items-start gap-3 md:items-end">
              <div className="rounded-2xl border border-border/70 bg-background/80 px-4 py-3 text-sm shadow-sm">
                <div className="flex items-center gap-2 font-medium">
                  {isRefreshActive(overview.refresh) ? (
                    <Loader2 className="h-4 w-4 animate-spin text-primary" />
                  ) : (
                    <Waves className="h-4 w-4 text-primary" />
                  )}
                  {statusLabel(overview.refresh)}
                </div>
                {overview.refresh.stage ? (
                  <p className="mt-1 text-xs text-muted-foreground">
                    阶段：{overview.refresh.stage}
                    {overview.refresh.progress_total > 0
                      ? ` · ${overview.refresh.progress_current}/${overview.refresh.progress_total}`
                      : ""}
                  </p>
                ) : null}
              </div>

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={isRefreshActive(overview.refresh)}
                  onClick={() => void startRefresh("quick")}
                  className="inline-flex items-center gap-2 rounded-full bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <RefreshCcw className="h-4 w-4" />
                  快速刷新
                </button>
                <button
                  type="button"
                  disabled={isRefreshActive(overview.refresh)}
                  onClick={() => void startRefresh("full")}
                  className="inline-flex items-center gap-2 rounded-full border border-border bg-background px-4 py-2 text-sm font-medium transition hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
                >
                  全量刷新
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="border-b border-border/70 bg-background/70 px-6 py-4">
          <div className="flex gap-2 overflow-x-auto pb-1" aria-label="事件模块">
            {availableTopics.map((topicKey) => (
              <button
                key={topicKey}
                type="button"
                onClick={() => setTopic(topicKey)}
                aria-pressed={topic === topicKey}
                className={cn(
                  "shrink-0 rounded-full border px-4 py-2 text-sm font-medium transition",
                  topic === topicKey
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                {TOPIC_LABELS[topicKey]}
              </button>
            ))}
          </div>
        </div>

        <div className="grid gap-3 border-b border-border/70 bg-background/70 px-6 py-4 md:grid-cols-4">
          <div className="md:col-span-2">
            <label htmlFor="event-search" className="mb-1 block text-xs font-medium text-muted-foreground">
              搜索
            </label>
            <input
              id="event-search"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              placeholder="搜索事件、英文标题或标签"
              className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none transition focus:border-primary/50 focus:ring-2 focus:ring-primary/20"
            />
          </div>
          <div>
            <label htmlFor="event-source" className="mb-1 block text-xs font-medium text-muted-foreground">
              来源
            </label>
            <select
              id="event-source"
              aria-label="来源"
              value={source}
              onChange={(event) =>
                setSource(event.target.value as ProbabilitySource | "all")
              }
              className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none transition focus:border-primary/50 focus:ring-2 focus:ring-primary/20"
            >
              <option value="all">全部来源</option>
              <option value="polymarket">Polymarket</option>
              <option value="kalshi">Kalshi</option>
            </select>
          </div>
          <div>
            <div>
              <label htmlFor="event-min-change" className="mb-1 block text-xs font-medium text-muted-foreground">
                最小 24h 波动
              </label>
              <select
                id="event-min-change"
                aria-label="最小 24h 波动"
                value={minChange}
                onChange={(event) => setMinChange(event.target.value)}
                className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none transition focus:border-primary/50 focus:ring-2 focus:ring-primary/20"
              >
                <option value="0">不过滤</option>
                <option value="0.02">2%</option>
                <option value="0.05">5%</option>
                <option value="0.1">10%</option>
              </select>
            </div>
          </div>
        </div>
      </section>

      {error ? (
        <div className="flex items-start gap-3 rounded-2xl border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>{error}</div>
        </div>
      ) : null}

      {loading ? (
        <div className="rounded-2xl border border-border/70 bg-card px-6 py-12 text-center text-sm text-muted-foreground">
          正在加载事件概率缓存…
        </div>
      ) : filteredEvents.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border/70 bg-card px-6 py-12 text-center text-sm text-muted-foreground">
          当前筛选条件下没有可展示的事件
        </div>
      ) : (
          <section className="rounded-2xl border border-border/70 bg-card shadow-sm">
            <div className="flex items-center justify-between border-b border-border/70 px-5 py-4">
              <div>
                <h2 className="text-lg font-semibold">{TOPIC_LABELS[topic]}</h2>
                <p className="text-xs text-muted-foreground">
                  按 24h 成交额排序 · {filteredEvents.length} 个事件
                </p>
              </div>
            </div>

            <div className="divide-y divide-border/60">
              {filteredEvents.map((row, index) => {
                const isGroupedPolymarket =
                  row.source === "polymarket" && row.results.length > 0;
                const groupedResults = isGroupedPolymarket
                  ? sortResultsByVolume(row.results).slice(0, MAX_GROUPED_RESULTS)
                  : [];
                const groupedSeries = resultSeries(groupedResults);
                const singleSeries: ProbabilityHistorySeriesRequest[] =
                  row.token_id_yes
                    ? [
                        {
                          label: row.pick_label || row.outcomes[0] || "Yes",
                          token_id: row.token_id_yes,
                        },
                      ]
                    : [];
                return (
                  <article key={`${row.source}-${row.slug}`} className="px-5 py-4">
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                      <div className="min-w-0 flex-1 space-y-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span
                            className={cn(
                              "inline-flex rounded-full px-2.5 py-1 text-xs font-medium",
                              row.source === "polymarket"
                                ? "bg-primary/10 text-primary"
                                : "bg-info/10 text-info",
                            )}
                          >
                            {row.source}
                          </span>
                          <span className="rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
                            成交额 #{index + 1}
                          </span>
                          {row.series_ticker ? (
                            <span className="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground">
                              {row.series_ticker}
                            </span>
                          ) : null}
                          {row.pick_label ? (
                            <span className="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground">
                              {row.pick_label}
                            </span>
                          ) : null}
                        </div>

                        <div className="space-y-1">
                          {row.question_zh ? (
                            <>
                              <h3 className="text-base font-semibold leading-snug text-foreground">
                                {row.question_zh}
                              </h3>
                              <p className="text-sm text-muted-foreground">
                                {row.question}
                              </p>
                            </>
                          ) : (
                            <h3 className="text-base font-semibold leading-snug text-foreground">
                              {row.question}
                            </h3>
                          )}
                        </div>
                      </div>

                      {!isGroupedPolymarket ? (
                        <div className="grid min-w-[240px] grid-cols-2 gap-3 rounded-2xl border border-border/70 bg-background/70 p-4 text-sm">
                          <div>
                            <div className="text-xs uppercase tracking-wide text-muted-foreground">
                              概率
                            </div>
                            <div className="mt-1 text-lg font-semibold">
                              {formatPercent(row.prob_yes)}
                            </div>
                          </div>
                          <div>
                            <div className="text-xs uppercase tracking-wide text-muted-foreground">
                              24h
                            </div>
                            <div
                              className={cn(
                                "mt-1 text-lg font-semibold",
                                (row.change_24h ?? 0) > 0 && "text-success",
                                (row.change_24h ?? 0) < 0 && "text-danger",
                              )}
                            >
                              {formatSignedPercent(row.change_24h)}
                            </div>
                          </div>
                          <div>
                            <div className="text-xs uppercase tracking-wide text-muted-foreground">
                              成交额
                            </div>
                            <div className="mt-1 font-medium">
                              {formatCompactNumber(row.volume_24h)}
                            </div>
                          </div>
                          <div>
                            <div className="text-xs uppercase tracking-wide text-muted-foreground">
                              到期
                            </div>
                            <div className="mt-1 font-medium">
                              {row.end_date
                                ? new Date(row.end_date).toLocaleDateString("zh-CN")
                                : "—"}
                            </div>
                          </div>
                        </div>
                      ) : null}
                    </div>

                    {isGroupedPolymarket ? (
                      <div className="mt-4 grid gap-2">
                        {groupedResults.map((result) => (
                          <div
                            key={result.token_id || result.label}
                            className="grid gap-3 rounded-2xl border border-border/70 bg-background/70 p-4 text-sm md:grid-cols-[minmax(0,1fr)_repeat(3,96px)] md:items-center"
                          >
                            <div className="min-w-0">
                              <div className="font-medium text-foreground">
                                {resultLabel(result)}
                              </div>
                              {result.label_zh ? (
                                <div className="mt-1 text-xs text-muted-foreground">
                                  {result.label}
                                </div>
                              ) : null}
                            </div>
                            <div>
                              <div className="text-xs uppercase tracking-wide text-muted-foreground">
                                概率
                              </div>
                              <div className="mt-1 font-semibold">
                                {formatPercent(result.probability)}
                              </div>
                            </div>
                            <div>
                              <div className="text-xs uppercase tracking-wide text-muted-foreground">
                                24h
                              </div>
                              <div
                                className={cn(
                                  "mt-1 font-semibold",
                                  (result.change_24h ?? 0) > 0 && "text-success",
                                  (result.change_24h ?? 0) < 0 && "text-danger",
                                )}
                              >
                                {formatSignedPercent(result.change_24h)}
                              </div>
                            </div>
                            <div>
                              <div className="text-xs uppercase tracking-wide text-muted-foreground">
                                成交额
                              </div>
                              <div className="mt-1 font-medium">
                                {formatCompactNumber(result.volume_24h)}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : null}

                    {isGroupedPolymarket && groupedSeries.length > 0 ? (
                      <div className="mt-4 rounded-2xl border border-border/70 bg-background/70 p-4">
                        <ProbabilityTrend series={groupedSeries} />
                      </div>
                    ) : row.source === "polymarket" && singleSeries.length > 0 ? (
                      <div className="mt-4 rounded-2xl border border-border/70 bg-background/70 p-4">
                        <ProbabilityTrend series={singleSeries} />
                      </div>
                    ) : null}
                  </article>
                );
              })}
            </div>
          </section>
      )}

      <footer className="pb-6 text-center text-xs tracking-wide text-muted-foreground">
        风险温度计，不构成交易信号
      </footer>
    </div>
  );
}
