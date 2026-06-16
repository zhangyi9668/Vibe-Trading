import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { echarts } from "@/lib/echarts";
import { getChartTheme } from "@/lib/chart-theme";

interface ProbabilityTrendProps {
  tokenId: string;
}

export function ProbabilityTrend({ tokenId }: ProbabilityTrendProps) {
  const visibilityRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(
    () => typeof IntersectionObserver === "undefined",
  );
  const [points, setPoints] = useState<Array<{ t: number; p: number }> | null>(null);
  const [error, setError] = useState<string | null>(null);

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
  }, [visible]);

  useEffect(() => {
    if (!visible) {
      return;
    }
    let alive = true;
    setError(null);
    setPoints(null);
    api
      .getEventProbabilityHistory(tokenId)
      .then((rows) => {
        if (alive) {
          setPoints(rows);
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
  }, [tokenId, visible]);

  useEffect(() => {
    if (!containerRef.current || !points || points.length === 0) {
      return;
    }

    const theme = getChartTheme();
    const chart = echarts.init(containerRef.current);
    chart.setOption({
      backgroundColor: "transparent",
      animationDuration: 500,
      grid: { left: 36, right: 20, top: 20, bottom: 30 },
      tooltip: {
        trigger: "axis",
        backgroundColor: theme.tooltipBg,
        borderColor: theme.tooltipBorder,
        textStyle: { color: theme.tooltipText, fontSize: 12 },
        valueFormatter: (value: number) => `${value.toFixed(1)}%`,
      },
      xAxis: {
        type: "category",
        data: points.map((point) =>
          new Date(point.t * 1000).toLocaleDateString("zh-CN", {
            month: "numeric",
            day: "numeric",
          }),
        ),
        axisLabel: {
          color: theme.textColor,
          fontSize: 11,
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
      series: [
        {
          type: "line",
          smooth: true,
          showSymbol: false,
          lineStyle: {
            width: 2,
            color: theme.infoColor,
          },
          areaStyle: {
            color: `${theme.infoColor}22`,
          },
          data: points.map((point) => Number((point.p * 100).toFixed(2))),
        },
      ],
    });

    const resizeObserver = new ResizeObserver(() => chart.resize());
    resizeObserver.observe(containerRef.current);
    return () => {
      resizeObserver.disconnect();
      chart.dispose();
    };
  }, [points]);

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

  if (points === null) {
    return (
      <div className="rounded-lg border border-border/70 bg-background/70 px-4 py-6 text-sm text-muted-foreground">
        正在加载趋势数据…
      </div>
    );
  }

  if (points.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border/70 bg-background/60 px-4 py-6 text-sm text-muted-foreground">
        暂无趋势数据
      </div>
    );
  }

  return <div ref={containerRef} className="h-56 w-full" />;
}
