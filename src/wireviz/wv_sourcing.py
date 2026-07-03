# -*- coding: utf-8 -*-
"""Distributor sourcing for WireViz BOMs.

Enriches a harness BOM with live data from electronics distributors — unit
price, price breaks, stock, datasheet/product links, and lifecycle status —
so a design can be costed and ordered without leaving the tool. Neither of the
commercial harness tools we benchmarked integrates real distributor APIs, so
this is a deliberate differentiator.

Design:
- ``PartInfo`` is a distributor-neutral result record.
- ``DistributorProvider`` is the interface; ``DigiKeyProvider`` and
  ``MouserProvider`` implement it against their public APIs.
- The HTTP layer is a small injectable ``transport`` callable so the
  response-mapping logic is unit-testable without network or credentials.
- ``SourcingCache`` persists lookups to a JSON file so repeated runs don't
  re-hit the APIs (and offline runs still show previously-fetched data).
- Everything degrades gracefully: with no credentials the providers report
  ``available() == False`` and enrichment simply leaves sourcing fields empty.

Credentials come from the environment:
    DigiKey:  DIGIKEY_CLIENT_ID, DIGIKEY_CLIENT_SECRET
    Mouser:   MOUSER_API_KEY
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

# A transport maps (method, url, headers, body_bytes) -> (status_code, parsed_json).
Transport = Callable[[str, str, Dict[str, str], Optional[bytes]], Tuple[int, dict]]


def urllib_transport(
    method: str, url: str, headers: Dict[str, str], body: Optional[bytes]
) -> Tuple[int, dict]:
    """Default transport backed by urllib (stdlib, no extra dependency)."""
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = {"error": raw}
        return e.code, parsed


@dataclass
class PriceBreak:
    quantity: int
    unit_price: float
    currency: str = "USD"


@dataclass
class PartInfo:
    mpn: str
    found: bool = False
    distributor: Optional[str] = None
    manufacturer: Optional[str] = None
    description: Optional[str] = None
    distributor_pn: Optional[str] = None
    datasheet_url: Optional[str] = None
    product_url: Optional[str] = None
    stock: Optional[int] = None
    lifecycle: Optional[str] = None
    price_breaks: List[PriceBreak] = field(default_factory=list)
    error: Optional[str] = None

    def unit_price_at(self, qty: float) -> Optional[float]:
        """Unit price for the largest price break whose quantity is <= qty."""
        applicable = [pb for pb in self.price_breaks if pb.quantity <= max(qty, 1)]
        if not applicable:
            # qty below the smallest break: fall back to the smallest break
            if self.price_breaks:
                return min(self.price_breaks, key=lambda pb: pb.quantity).unit_price
            return None
        return max(applicable, key=lambda pb: pb.quantity).unit_price

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict) -> "PartInfo":
        breaks = [PriceBreak(**pb) for pb in d.get("price_breaks", [])]
        d = {**d, "price_breaks": breaks}
        return cls(**d)


class SourcingCache:
    """A tiny JSON-file cache of PartInfo keyed by 'distributor:mpn'."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else None
        self._data: Dict[str, dict] = {}
        if self.path and self.path.exists():
            try:
                self._data = json.loads(self.path.read_text())
            except (ValueError, OSError):
                self._data = {}

    @staticmethod
    def _key(distributor: str, mpn: str) -> str:
        return f"{distributor}:{mpn}"

    def get(self, distributor: str, mpn: str) -> Optional[PartInfo]:
        d = self._data.get(self._key(distributor, mpn))
        return PartInfo.from_json(d) if d else None

    def put(self, info: PartInfo) -> None:
        if not info.distributor:
            return
        self._data[self._key(info.distributor, info.mpn)] = info.to_json()

    def save(self) -> None:
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, indent=2))


class DistributorProvider(ABC):
    name: str = "distributor"

    @abstractmethod
    def available(self) -> bool:
        """True if credentials are present and the provider can be queried."""

    @abstractmethod
    def lookup(self, mpn: str) -> PartInfo:
        """Look up a manufacturer part number and return distributor-neutral info."""


class DigiKeyProvider(DistributorProvider):
    """DigiKey Product Information API v4 (OAuth2 client-credentials)."""

    name = "digikey"
    TOKEN_URL = "https://api.digikey.com/v1/oauth2/token"
    DETAILS_URL = "https://api.digikey.com/products/v4/search/{mpn}/productdetails"

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        transport: Transport = urllib_transport,
    ):
        self.client_id = client_id or os.environ.get("DIGIKEY_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("DIGIKEY_CLIENT_SECRET")
        self._transport = transport
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0

    def available(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 30:
            return self._token
        body = urllib.parse.urlencode(
            {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            }
        ).encode()
        status, data = self._transport(
            "POST",
            self.TOKEN_URL,
            {"Content-Type": "application/x-www-form-urlencoded"},
            body,
        )
        if status != 200 or "access_token" not in data:
            raise RuntimeError(f"DigiKey auth failed ({status}): {data}")
        self._token = data["access_token"]
        self._token_expiry = time.time() + float(data.get("expires_in", 600))
        return self._token

    def lookup(self, mpn: str) -> PartInfo:
        if not self.available():
            return PartInfo(mpn=mpn, error="no DigiKey credentials")
        try:
            token = self._get_token()
        except Exception as e:  # noqa: BLE001
            return PartInfo(mpn=mpn, distributor=self.name, error=str(e))
        headers = {
            "Authorization": f"Bearer {token}",
            "X-DIGIKEY-Client-Id": self.client_id,
            "Accept": "application/json",
        }
        url = self.DETAILS_URL.format(mpn=urllib.parse.quote(mpn, safe=""))
        status, data = self._transport("GET", url, headers, None)
        if status != 200:
            return PartInfo(
                mpn=mpn, distributor=self.name, error=f"HTTP {status}: {data}"
            )
        return self._map(mpn, data)

    def _map(self, mpn: str, data: dict) -> PartInfo:
        product = data.get("Product") or data.get("ProductDetails") or {}
        if not product:
            return PartInfo(mpn=mpn, distributor=self.name, found=False)
        breaks = []
        for v in product.get("ProductVariations", []) or []:
            for pb in v.get("StandardPricing", []) or []:
                breaks.append(
                    PriceBreak(
                        quantity=int(pb.get("BreakQuantity", 1)),
                        unit_price=float(pb.get("UnitPrice", 0.0)),
                    )
                )
            if breaks:
                break
        manufacturer = (product.get("Manufacturer") or {}).get("Name")
        return PartInfo(
            mpn=mpn,
            found=True,
            distributor=self.name,
            manufacturer=manufacturer,
            description=(product.get("Description") or {}).get("ProductDescription"),
            distributor_pn=(product.get("ProductVariations", [{}]) or [{}])[0].get(
                "DigiKeyProductNumber"
            ),
            datasheet_url=product.get("DatasheetUrl"),
            product_url=product.get("ProductUrl"),
            stock=product.get("QuantityAvailable"),
            lifecycle=(product.get("ProductStatus") or {}).get("Status"),
            price_breaks=sorted(breaks, key=lambda b: b.quantity),
        )


class MouserProvider(DistributorProvider):
    """Mouser Search API v1 (API-key)."""

    name = "mouser"
    SEARCH_URL = "https://api.mouser.com/api/v1/search/partnumber?apiKey={key}"

    def __init__(
        self, api_key: Optional[str] = None, transport: Transport = urllib_transport
    ):
        self.api_key = api_key or os.environ.get("MOUSER_API_KEY")
        self._transport = transport

    def available(self) -> bool:
        return bool(self.api_key)

    def lookup(self, mpn: str) -> PartInfo:
        if not self.available():
            return PartInfo(mpn=mpn, error="no Mouser API key")
        body = json.dumps(
            {"SearchByPartRequest": {"mouserPartNumber": mpn}}
        ).encode()
        url = self.SEARCH_URL.format(key=urllib.parse.quote(self.api_key, safe=""))
        status, data = self._transport(
            "POST", url, {"Content-Type": "application/json"}, body
        )
        if status != 200:
            return PartInfo(
                mpn=mpn, distributor=self.name, error=f"HTTP {status}: {data}"
            )
        return self._map(mpn, data)

    def _map(self, mpn: str, data: dict) -> PartInfo:
        parts = ((data.get("SearchResults") or {}).get("Parts")) or []
        if not parts:
            return PartInfo(mpn=mpn, distributor=self.name, found=False)
        p = parts[0]
        breaks = []
        for pb in p.get("PriceBreaks", []) or []:
            price = str(pb.get("Price", "0")).replace("$", "").replace(",", "").strip()
            try:
                unit = float(price)
            except ValueError:
                unit = 0.0
            breaks.append(
                PriceBreak(
                    quantity=int(pb.get("Quantity", 1)),
                    unit_price=unit,
                    currency=pb.get("Currency", "USD"),
                )
            )
        stock = p.get("AvailabilityInStock")
        try:
            stock = int(stock) if stock is not None else None
        except (ValueError, TypeError):
            stock = None
        return PartInfo(
            mpn=mpn,
            found=True,
            distributor=self.name,
            manufacturer=p.get("Manufacturer"),
            description=p.get("Description"),
            distributor_pn=p.get("MouserPartNumber"),
            datasheet_url=p.get("DataSheetUrl"),
            product_url=p.get("ProductDetailUrl"),
            stock=stock,
            lifecycle=p.get("LifecycleStatus"),
            price_breaks=sorted(breaks, key=lambda b: b.quantity),
        )


def _mpn_of(row: dict) -> Optional[str]:
    mpn = row.get("mpn")
    if isinstance(mpn, list):
        mpn = next((m for m in mpn if m), None)
    if mpn in (None, "", "N/A"):
        return None
    return str(mpn)


def _qty_of(row: dict) -> float:
    try:
        return float(row.get("qty", 1) or 1)
    except (ValueError, TypeError):
        return 1.0


@dataclass
class SourcedLine:
    row: dict
    mpn: Optional[str]
    qty: float
    info: Optional[PartInfo]

    @property
    def unit_price(self) -> Optional[float]:
        return self.info.unit_price_at(self.qty) if self.info and self.info.found else None

    @property
    def extended_price(self) -> Optional[float]:
        up = self.unit_price
        return round(up * self.qty, 4) if up is not None else None


def enrich_bom(
    bom_rows: List[dict],
    provider: DistributorProvider,
    cache: Optional[SourcingCache] = None,
) -> List[SourcedLine]:
    """Attach distributor sourcing info + extended pricing to each BOM row.

    Uses the cache first; only calls the provider for uncached MPNs and only if
    the provider is available. Rows without an MPN pass through unsourced.
    """
    results: List[SourcedLine] = []
    seen: Dict[str, PartInfo] = {}
    for row in bom_rows:
        mpn = _mpn_of(row)
        qty = _qty_of(row)
        info: Optional[PartInfo] = None
        if mpn:
            if mpn in seen:
                info = seen[mpn]
            else:
                if cache:
                    info = cache.get(provider.name, mpn)
                if info is None and provider.available():
                    info = provider.lookup(mpn)
                    if cache and info and (info.found or info.error is None):
                        cache.put(info)
                seen[mpn] = info
        results.append(SourcedLine(row=row, mpn=mpn, qty=qty, info=info))
    if cache:
        cache.save()
    return results


def total_cost(lines: List[SourcedLine]) -> Optional[float]:
    """Sum extended prices; None if nothing could be priced."""
    priced = [ln.extended_price for ln in lines if ln.extended_price is not None]
    return round(sum(priced), 4) if priced else None


SOURCED_COLUMNS = [
    "designators",
    "description",
    "mpn",
    "qty",
    "distributor",
    "distributor_pn",
    "stock",
    "lifecycle",
    "unit_price",
    "extended_price",
    "product_url",
]


def _row_designators(row: dict) -> str:
    d = row.get("designators") or row.get("Designators") or ""
    return ", ".join(map(str, d)) if isinstance(d, (list, tuple)) else str(d)


def sourced_to_csv(lines: List[SourcedLine]) -> str:
    """Render enriched BOM lines to a distributor-costed CSV."""
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(SOURCED_COLUMNS)
    for ln in lines:
        info = ln.info
        w.writerow(
            [
                _row_designators(ln.row),
                ln.row.get("description", ""),
                ln.mpn or "",
                ln.qty,
                (info.distributor if info else "") or "",
                (info.distributor_pn if info else "") or "",
                (info.stock if info else "") if info else "",
                (info.lifecycle if info else "") or "" if info else "",
                ln.unit_price if ln.unit_price is not None else "",
                ln.extended_price if ln.extended_price is not None else "",
                (info.product_url if info else "") or "",
            ]
        )
    grand = total_cost(lines)
    if grand is not None:
        w.writerow([""] * (len(SOURCED_COLUMNS) - 1) + [grand])
    return buf.getvalue()
