from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any


WIND_SKILL_DIR = Path("/Users/phoebe/.agents/skills/wind-mcp-skill")
WIND_CLI = WIND_SKILL_DIR / "scripts/cli.mjs"
NODE = Path(
    os.getenv(
        "VIBE_NODE",
        "/Users/phoebe/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node",
    )
)

WIND_INDEXES = "中文简称,最新成交价,涨跌幅,成交额,总市值2,市盈率(TTM),市净率(LF)"
IFIND_INDICATORS = "latest,changeRatio,amount,totalMarketValue,pe_ttm,pb"

COMPANIES: list[dict[str, str]] = [
    {"code": "688981.SH", "ifind": "688981.SH", "name": "中芯国际", "segment": "制造/代工"},
    {"code": "688347.SH", "ifind": "688347.SH", "name": "华虹公司", "segment": "制造/代工"},
    {"code": "688249.SH", "ifind": "688249.SH", "name": "晶合集成", "segment": "制造/代工"},
    {"code": "688396.SH", "ifind": "688396.SH", "name": "华润微", "segment": "制造/代工"},
    {"code": "002371.SZ", "ifind": "002371.SZ", "name": "北方华创", "segment": "半导体设备"},
    {"code": "688012.SH", "ifind": "688012.SH", "name": "中微公司", "segment": "半导体设备"},
    {"code": "688072.SH", "ifind": "688072.SH", "name": "拓荆科技", "segment": "半导体设备"},
    {"code": "688120.SH", "ifind": "688120.SH", "name": "华海清科", "segment": "半导体设备"},
    {"code": "688082.SH", "ifind": "688082.SH", "name": "盛美上海", "segment": "半导体设备"},
    {"code": "688019.SH", "ifind": "688019.SH", "name": "安集科技", "segment": "材料/零部件"},
    {"code": "300666.SZ", "ifind": "300666.SZ", "name": "江丰电子", "segment": "材料/零部件"},
    {"code": "688126.SH", "ifind": "688126.SH", "name": "沪硅产业", "segment": "材料/零部件"},
    {"code": "688234.SH", "ifind": "688234.SH", "name": "天岳先进", "segment": "材料/零部件"},
    {"code": "688256.SH", "ifind": "688256.SH", "name": "寒武纪", "segment": "设计/IP/AI"},
    {"code": "688008.SH", "ifind": "688008.SH", "name": "澜起科技", "segment": "设计/IP/AI"},
    {"code": "603501.SH", "ifind": "603501.SH", "name": "韦尔股份", "segment": "设计/IP/AI"},
    {"code": "688521.SH", "ifind": "688521.SH", "name": "芯原股份", "segment": "设计/IP/AI"},
    {"code": "688099.SH", "ifind": "688099.SH", "name": "晶晨股份", "segment": "设计/IP/AI"},
    {"code": "600584.SH", "ifind": "600584.SH", "name": "长电科技", "segment": "封测/先进封装"},
    {"code": "002156.SZ", "ifind": "002156.SZ", "name": "通富微电", "segment": "封测/先进封装"},
    {"code": "002185.SZ", "ifind": "002185.SZ", "name": "华天科技", "segment": "封测/先进封装"},
    {"code": "688362.SH", "ifind": "688362.SH", "name": "甬矽电子", "segment": "封测/先进封装"},
    {"code": "301269.SZ", "ifind": "301269.SZ", "name": "华大九天", "segment": "EDA/FPGA"},
    {"code": "688206.SH", "ifind": "688206.SH", "name": "概伦电子", "segment": "EDA/FPGA"},
    {"code": "688107.SH", "ifind": "688107.SH", "name": "安路科技", "segment": "EDA/FPGA"},
]

_DOTENV_LOADED = False
_AGENT_DIR = Path(__file__).resolve().parents[2]
_SOURCE_DIR = _AGENT_DIR.parent
_WORKSPACE_DIR = _SOURCE_DIR.parent


def _ensure_dotenv() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    try:
        from dotenv import load_dotenv
    except Exception:
        load_dotenv = None
    for candidate in (
        Path.home() / ".vibe-trading" / ".env",
        _AGENT_DIR / ".env",
        _SOURCE_DIR / ".env",
        _WORKSPACE_DIR / ".env",
        Path.cwd() / ".env",
    ):
        if not candidate.exists():
            continue
        if load_dotenv is not None:
            load_dotenv(dotenv_path=candidate, override=False)
        else:
            for raw in candidate.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if key:
                    os.environ.setdefault(key, value.strip().strip('"').strip("'"))
    _DOTENV_LOADED = True


def parse_number(value: Any) -> float | None:
    if value in (None, "", "--", "nan"):
        return None
    try:
        return float(str(value).replace(",", "").replace("%", ""))
    except ValueError:
        return None


class SemiconductorQuoteService:
    def __init__(self, companies: list[dict[str, str]] | None = None) -> None:
        _ensure_dotenv()
        self.companies = companies or COMPANIES

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "wind_cli": WIND_CLI.exists(),
            "ifind_configured": self.ifind_configured(),
        }

    def ifind_configured(self) -> bool:
        return bool(os.getenv("IFIND_ACCESS_TOKEN") or os.getenv("IFIND_REFRESH_TOKEN"))

    def source_order(self) -> list[str]:
        return ["ifind", "wind"] if self.ifind_configured() else ["wind", "ifind"]

    def call_wind(self, company: dict[str, str]) -> dict[str, Any]:
        if not WIND_CLI.exists() or not NODE.exists():
            raise RuntimeError("Wind CLI 或 Node 运行时不存在")
        params = {"windcode": company["code"], "indexes": WIND_INDEXES}
        result = subprocess.run(
            [
                str(NODE),
                str(WIND_CLI),
                "call",
                "stock_data",
                "get_stock_price_indicators",
                json.dumps(params, ensure_ascii=False),
            ],
            cwd=WIND_SKILL_DIR,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError((result.stdout or result.stderr).strip()[:300])
        outer = json.loads(result.stdout)
        if outer.get("isError"):
            raise RuntimeError(str(outer)[:300])
        inner = json.loads(outer["content"][0]["text"])
        if inner.get("error"):
            raise RuntimeError(str(inner["error"])[:300])
        data = inner.get("data") or {}
        columns = [item["name"] for item in data.get("columns", [])]
        rows = data.get("rows") or []
        if not rows:
            raise RuntimeError("Wind 返回空数据")
        row = dict(zip(columns, rows[0]))
        return {
            "code": company["code"],
            "name": row.get("中文简称") or company["name"],
            "segment": company["segment"],
            "price": parse_number(row.get("最新成交价")),
            "change_pct": parse_number(row.get("涨跌幅")),
            "amount": parse_number(row.get("成交额")),
            "market_cap": parse_number(row.get("总市值2")),
            "pe_ttm": parse_number(row.get("市盈率(TTM)")),
            "pb": parse_number(row.get("市净率(LF)")),
            "source": "Wind",
            "error": None,
        }

    def get_ifind_token(self, force_refresh: bool = False) -> str:
        access_token = os.getenv("IFIND_ACCESS_TOKEN")
        if access_token and not force_refresh:
            return access_token
        refresh_token = os.getenv("IFIND_REFRESH_TOKEN")
        if not refresh_token:
            raise RuntimeError("iFinD Token 未配置")
        base = os.getenv("IFIND_BASE_URL", "https://quantapi.51ifind.com/api/v1").rstrip("/")
        request = urllib.request.Request(
            f"{base}/get_access_token",
            method="POST",
            headers={"Content-Type": "application/json", "refresh_token": refresh_token},
            data=b"{}",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        token = (payload.get("data") or {}).get("access_token")
        if not token:
            raise RuntimeError("iFinD 无法取得 access_token")
        os.environ["IFIND_ACCESS_TOKEN"] = str(token)
        return str(token)

    def _ifind_post(self, body: dict[str, Any]) -> dict[str, Any]:
        base = os.getenv("IFIND_BASE_URL", "https://quantapi.51ifind.com/api/v1").rstrip("/")
        data = json.dumps(body).encode("utf-8")
        token = self.get_ifind_token()
        request = urllib.request.Request(
            f"{base}/real_time_quotation",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "access_token": token,
                "ifindlang": "cn",
            },
            data=data,
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code != 401:
                raise
            token = self.get_ifind_token(force_refresh=True)
            retry = urllib.request.Request(
                f"{base}/real_time_quotation",
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "access_token": token,
                    "ifindlang": "cn",
                },
                data=data,
            )
            with urllib.request.urlopen(retry, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))

    def _ifind_payload_to_row(self, company: dict[str, str], row: dict[str, Any]) -> dict[str, Any]:
        table = row.get("table")
        if isinstance(table, dict):
            normalized = dict(row)
            for key, value in table.items():
                normalized[key] = value[0] if isinstance(value, list) and value else value
            row = normalized
        return {
            "code": company["code"],
            "name": company["name"],
            "segment": company["segment"],
            "price": parse_number(row.get("latest")),
            "change_pct": parse_number(row.get("changeRatio")),
            "amount": parse_number(row.get("amount")),
            "market_cap": parse_number(row.get("totalMarketValue")),
            "pe_ttm": parse_number(row.get("pe_ttm")),
            "pb": parse_number(row.get("pb")),
            "source": "iFinD",
            "error": None,
        }

    def call_ifind(self, company: dict[str, str]) -> dict[str, Any]:
        payload = self._ifind_post({"codes": company["ifind"], "indicators": IFIND_INDICATORS})
        if payload.get("errorcode") not in (0, "0", None):
            raise RuntimeError(payload.get("errmsg") or "iFinD 返回错误")
        tables = payload.get("tables") or []
        if not tables:
            raise RuntimeError("iFinD 返回空数据")
        return self._ifind_payload_to_row(company, tables[0])

    def call_ifind_batch(self, companies: list[dict[str, str]]) -> list[dict[str, Any]]:
        payload = self._ifind_post(
            {
                "codes": ",".join(company["ifind"] for company in companies),
                "indicators": IFIND_INDICATORS,
            }
        )
        if payload.get("errorcode") not in (0, "0", None):
            raise RuntimeError(payload.get("errmsg") or "iFinD 返回错误")
        tables = payload.get("tables") or []
        if not tables:
            raise RuntimeError("iFinD 返回空数据")
        by_code = {
            str(row.get("thscode") or row.get("code") or row.get("stockcode") or ""): row
            for row in tables
            if isinstance(row, dict)
        }
        rows = []
        for index, company in enumerate(companies):
            row = by_code.get(company["ifind"]) or (tables[index] if index < len(tables) else None)
            if not isinstance(row, dict):
                raise RuntimeError(f"iFinD 缺少 {company['code']} 数据")
            rows.append(self._ifind_payload_to_row(company, row))
        return rows

    def fetch_company(self, company: dict[str, str]) -> dict[str, Any]:
        errors = []
        callers = {"ifind": self.call_ifind, "wind": self.call_wind}
        labels = {"ifind": "iFinD", "wind": "Wind"}
        for source in self.source_order():
            try:
                return callers[source](company)
            except Exception as exc:
                errors.append(f"{labels[source]}: {exc}")
        return {
            "code": company["code"],
            "name": company["name"],
            "segment": company["segment"],
            "price": None,
            "change_pct": None,
            "amount": None,
            "market_cap": None,
            "pe_ttm": None,
            "pb": None,
            "source": "不可用",
            "error": " | ".join(errors),
        }

    def fetch_all(self, max_workers: int = 4) -> dict[str, Any]:
        if self.ifind_configured():
            try:
                rows = self.call_ifind_batch(self.companies)
                return {
                    "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "success_count": sum(1 for row in rows if not row["error"]),
                    "error_count": sum(1 for row in rows if row["error"]),
                    "rows": rows,
                }
            except Exception:
                pass
        rows = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.fetch_company, item): item for item in self.companies}
            for future in as_completed(futures):
                rows.append(future.result())
        order = {item["code"]: index for index, item in enumerate(self.companies)}
        rows.sort(key=lambda row: order[row["code"]])
        return {
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "success_count": sum(1 for row in rows if not row["error"]),
            "error_count": sum(1 for row in rows if row["error"]),
            "rows": rows,
        }
