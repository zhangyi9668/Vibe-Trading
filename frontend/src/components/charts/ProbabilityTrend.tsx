import { useEffect, useMemo, useRef, useState } from "react";

import {
  api,
  type ProbabilityHistorySeries,
  type ProbabilityHistorySeriesRequest,
} from "@/lib/api";
import { echarts } from "@/lib/echarts";
import { getChartTheme } from "@/lib/chart-theme";

interface ProbabilityTrendProps {
  series: ProbabilityHistorySeriesRequest[];
}

const LINE_COLORS = ["#8BC1FF", "#2D9CFF", "#FFC21A", "#FF861A", "#B78CFF"];

function formatPointValue(value: number): number {
  return Number((value * 100).toFixed(2));
}

function latestProbability(points: Array<{ t: number; p: number }>): number {
  return points.reduce((latest, point) => (point.t >= latest.t ? point : latest)).p;
}

function buildSeriesKey(series: ProbabilityHistorySeriesRequest[]): string {
  return JSON.stringify(
    series
      .slice(0, 5)
      .map(({ label, token_id }) => ({ label, token_id })),
  );
}

export function ProbabilityTrend({ series }: ProbabilityTrendProps) {
  const requestSeriesKey = buildSeriesKey(series);
  const requestSeries = useMemo(
    () => JSON.parse(requestSeriesKey) as ProbabilityHistorySeriesRequest[],
    [requestSeriesKey],
  );
  const visibilityRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(
    () => typeof IntersectionObserver === "undefined",
  );
  const [histories, setHistories] = useState<ProbabilityHistorySeries[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const successfulHistories = useMemo(
    () =>
      histories?.filter((history) => !history.error && history.points.length > 0) ??
      [],
    [histories],
  );
  const hasPartialError =
    histories !== null &&
    successfulHistories.length > 0 &&
    histories.some((history) => history.error);

  useEffect(() => {
    if (visible || !visibilityRef.current) {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "300px 0px" },
    );
    observer.observe(visibilityRef.current);
    return () => observer.disconnect();
  }, [requestSeries.length, visible]);

  useEffect(() => {
    if (!visible) {
      return;
    }
    if (requestSeries.length === 0) {
      setHistories([]);
      return;
    }
    let alive = true;
    setError(null);
    setHistories(null);
    api
      .getEventProbabilityHistories(requestSeries)
      .then((rows) => {
        if (alive) {
          setHistories(rows);
        }
      })
      .catch((err: unknown) => {
        if (alive) {
          setError(err instanceof Error ? err.message : "趋势数据加载失败");
        }
      });
    return () => {
      alive = false;
    };
  }, [requestSeries, visible]);

  useEffect(() => {
    if (!containerRef.current || successfulHistories.length === 0) {
      return;
    }

    const theme = getChartTheme();
    const chart = echarts.init(containerRef.current);
    chart.setOption({
      backgroundColor: "transparent",
      animationDuration: 500,
      grid: { left: 36, right: 20, top: 52, bottom: 30 },
      legend: {
        type: "scroll",
        top: 0,
        textStyle: { color: theme.textColor, fontSize: 12 },
      },
      tooltip: {
        trigger: "axis",
        backgroundColor: theme.tooltipBg,
        borderColor: theme.tooltipBorder,
        textStyle: { color: theme.tooltipText, fontSize: 12 },
        valueFormatter: (value: number | null) =>
          value === null ? "暂无数据" : `${value.toFixed(1)}%`,
      },
      xAxis: {
        type: "time",
        axisLabel: {
          color: theme.textColor,
          fontSize: 11,
          formatter: (value: number) =>
            new Date(value).toLocaleDateString("zh-CN", {
              month: "numeric",
              day: "numeric",
            }),
        },
        axisLine: {
          lineStyle: { color: theme.axisColor },
        },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 100,
        axisLabel: {
          color: theme.textColor,
          formatter: "{value}%",
        },
        splitLine: {
          lineStyle: {
            color: theme.gridColor,
          },
        },
      },
      series: successfulHistories.map((history, index) => {
        return {
          name: `${history.label} ${(latestProbability(history.points) * 100).toFixed(1)}%`,
          type: "line",
          smooth: true,
          showSymbol: false,
          connectNulls: true,
          lineStyle: {
            width: 2,
            color: LINE_COLORS[index],
          },
          data: history.points.map((point) => [
            point.t * 1000,
            formatPointValue(point.p),
          ]),
        };
      }),
    });

    const resizeObserver = new ResizeObserver(() => chart.resize());
    resizeObserver.observe(containerRef.current);
    return () => {
      resizeObserver.disconnect();
      chart.dispose();
    };
  }, [successfulHistories]);

  if (series.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border/70 bg-background/60 px-4 py-6 text-sm text-muted-foreground">
        暂无趋势数据
      </div>
    );
  }

  if (!visible) {
    return (
      <div
        ref={visibilityRef}
        className="rounded-lg border border-border/70 bg-background/70 px-4 py-6 text-sm text-muted-foreground"
      >
        趋势图将在进入屏幕时加载
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">
        {error}
      </div>
    );
  }

  if (histories === null) {
    return (
      <div className="rounded-lg border border-border/70 bg-background/70 px-4 py-6 text-sm text-muted-foreground">
        正在加载趋势数据…
      </div>
    );
  }

  if (successfulHistories.length === 0) {
    if (histories.some((history) => history.error)) {
      return (
        <div className="rounded-lg border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">
          趋势数据加载失败
        </div>
      );
    }
    return (
      <div className="rounded-lg border border-dashed border-border/70 bg-background/60 px-4 py-6 text-sm text-muted-foreground">
        暂无趋势数据
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {hasPartialError ? (
        <div className="rounded-lg border border-warning/30 bg-warning/5 px-3 py-2 text-xs text-warning">
          部分趋势数据不可用
        </div>
      ) : null}
      <div ref={containerRef} className="h-72 w-full" />
    </div>
  );
}
