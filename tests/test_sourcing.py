"""Tests for distributor sourcing (wireviz.wv_sourcing).

The HTTP transport is faked, so these exercise response mapping, price-break
selection, caching, and BOM enrichment without network or credentials.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz.wv_sourcing import (  # noqa: E402
    DigiKeyProvider,
    MouserProvider,
    PartInfo,
    PriceBreak,
    SourcingCache,
    enrich_bom,
    total_cost,
)


# --- fake transports -------------------------------------------------------

DIGIKEY_TOKEN = {"access_token": "tok123", "expires_in": 600}

DIGIKEY_PRODUCT = {
    "Product": {
        "Manufacturer": {"Name": "Molex"},
        "Description": {"ProductDescription": "CONN HEADER 4POS"},
        "DatasheetUrl": "https://example.com/ds.pdf",
        "ProductUrl": "https://digikey.com/p/123",
        "QuantityAvailable": 5000,
        "ProductStatus": {"Status": "Active"},
        "ProductVariations": [
            {
                "DigiKeyProductNumber": "WM1234-ND",
                "StandardPricing": [
                    {"BreakQuantity": 1, "UnitPrice": 0.50},
                    {"BreakQuantity": 10, "UnitPrice": 0.40},
                    {"BreakQuantity": 100, "UnitPrice": 0.30},
                ],
            }
        ],
    }
}


def digikey_transport(method, url, headers, body):
    if url.endswith("/oauth2/token"):
        return 200, DIGIKEY_TOKEN
    if "productdetails" in url:
        return 200, DIGIKEY_PRODUCT
    return 404, {"error": "not found"}


MOUSER_RESPONSE = {
    "SearchResults": {
        "Parts": [
            {
                "Manufacturer": "TE Connectivity",
                "Description": "Ring terminal",
                "MouserPartNumber": "571-1234",
                "DataSheetUrl": "https://example.com/te.pdf",
                "ProductDetailUrl": "https://mouser.com/p/571-1234",
                "AvailabilityInStock": "1200",
                "LifecycleStatus": "Active",
                "PriceBreaks": [
                    {"Quantity": 1, "Price": "$0.25", "Currency": "USD"},
                    {"Quantity": 50, "Price": "$0.18", "Currency": "USD"},
                ],
            }
        ]
    }
}


def mouser_transport(method, url, headers, body):
    return 200, MOUSER_RESPONSE


# --- provider availability -------------------------------------------------


def test_provider_unavailable_without_credentials():
    dk = DigiKeyProvider(client_id=None, client_secret=None, transport=digikey_transport)
    assert not dk.available()
    info = dk.lookup("X")
    assert info.found is False and info.error


def test_digikey_mapping():
    dk = DigiKeyProvider(
        client_id="id", client_secret="secret", transport=digikey_transport
    )
    assert dk.available()
    info = dk.lookup("0022232041")
    assert info.found
    assert info.manufacturer == "Molex"
    assert info.distributor_pn == "WM1234-ND"
    assert info.stock == 5000
    assert info.lifecycle == "Active"
    assert len(info.price_breaks) == 3


def test_digikey_price_break_selection():
    dk = DigiKeyProvider(client_id="id", client_secret="secret", transport=digikey_transport)
    info = dk.lookup("0022232041")
    assert info.unit_price_at(1) == 0.50
    assert info.unit_price_at(5) == 0.50
    assert info.unit_price_at(10) == 0.40
    assert info.unit_price_at(250) == 0.30


def test_mouser_mapping():
    m = MouserProvider(api_key="key", transport=mouser_transport)
    info = m.lookup("571-1234")
    assert info.found
    assert info.manufacturer == "TE Connectivity"
    assert info.stock == 1200
    assert info.unit_price_at(50) == 0.18
    assert info.unit_price_at(1) == 0.25


def test_unit_price_below_smallest_break():
    info = PartInfo(
        mpn="x", found=True, price_breaks=[PriceBreak(10, 1.0), PriceBreak(100, 0.8)]
    )
    # qty 1 is below the smallest break (10) -> fall back to smallest break price
    assert info.unit_price_at(1) == 1.0


def test_cache_roundtrip(tmp_path):
    cache_file = tmp_path / "cache.json"
    cache = SourcingCache(cache_file)
    info = PartInfo(mpn="ABC", found=True, distributor="digikey", price_breaks=[PriceBreak(1, 2.0)])
    cache.put(info)
    cache.save()
    # reload from disk
    cache2 = SourcingCache(cache_file)
    got = cache2.get("digikey", "ABC")
    assert got is not None and got.found
    assert got.price_breaks[0].unit_price == 2.0


class CountingProvider:
    """Provider that records how many lookups actually hit it."""

    name = "digikey"

    def __init__(self):
        self.calls = 0

    def available(self):
        return True

    def lookup(self, mpn):
        self.calls += 1
        return PartInfo(mpn=mpn, found=True, distributor="digikey", price_breaks=[PriceBreak(1, 1.5)])


def test_enrich_bom_and_total_cost():
    bom = [
        {"mpn": "AAA", "qty": 2, "designators": ["X1"]},
        {"mpn": "BBB", "qty": 3, "designators": ["X2"]},
        {"mpn": "", "qty": 1, "designators": ["W1"]},  # no MPN -> unsourced
    ]
    provider = CountingProvider()
    lines = enrich_bom(bom, provider)
    assert provider.calls == 2  # only the two with MPNs
    aaa = next(ln for ln in lines if ln.mpn == "AAA")
    assert aaa.unit_price == 1.5
    assert aaa.extended_price == 3.0  # 1.5 * 2
    # total = 1.5*2 + 1.5*3 = 7.5
    assert total_cost(lines) == 7.5


def test_enrich_dedupes_repeated_mpn():
    bom = [
        {"mpn": "SAME", "qty": 1},
        {"mpn": "SAME", "qty": 4},
    ]
    provider = CountingProvider()
    enrich_bom(bom, provider)
    assert provider.calls == 1  # second row reuses the first lookup


def test_enrich_uses_cache_before_provider(tmp_path):
    cache = SourcingCache(tmp_path / "c.json")
    cache.put(PartInfo(mpn="CACHED", found=True, distributor="digikey", price_breaks=[PriceBreak(1, 9.0)]))
    provider = CountingProvider()
    lines = enrich_bom([{"mpn": "CACHED", "qty": 1}], provider, cache=cache)
    assert provider.calls == 0  # served from cache
    assert lines[0].unit_price == 9.0


if __name__ == "__main__":
    import traceback

    class _TmpPath:
        def __truediv__(self, other):
            import tempfile

            return Path(tempfile.mkdtemp()) / other

    tests = []
    for k, v in sorted(globals().items()):
        if k.startswith("test_"):
            tests.append(v)
    passed = 0
    for t in tests:
        try:
            if "tmp_path" in t.__code__.co_varnames[: t.__code__.co_argcount]:
                import tempfile

                t(Path(tempfile.mkdtemp()))
            else:
                t()
            passed += 1
            print(f"ok   {t.__name__}")
        except Exception:
            print(f"FAIL {t.__name__}")
            traceback.print_exc()
    print(f"\n{passed}/{len(tests)} sourcing tests passed")
    sys.exit(0 if passed == len(tests) else 1)
