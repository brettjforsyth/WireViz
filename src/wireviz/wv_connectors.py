# -*- coding: utf-8 -*-
"""Connector-type library and CAD asset resolution.

A connector can declare a ``connector_type`` (e.g. ``deutsch_dt_4``). That type
is a preference used two ways:

1. **Metadata** — the built-in library fills in a connector's manufacturer,
   series, default pin count, gender, and datasheet pointer when they are not
   given explicitly.
2. **CAD assets** — the type is the key used to locate a 2D image and a 3D
   model of the connector, which the renderers display instead of the plain
   schematic box.

Asset resolution order (first hit wins per asset):

1. a local file you provide, named ``<type><ext>`` in a ``cad_dir``
   (2D: .png/.jpg/.svg/.webp; 3D: .glb/.gltf/.step/.stl);
2. an asset reference stored on the library entry (a path or URL);
3. an optional ``image_provider`` callback (e.g. a distributor product photo).

Only **generic** metadata ships in the library — no proprietary manufacturer
CAD or images are bundled. You supply the actual assets (via ``cad_dir`` or a
provider); the library just knows how to find and describe them.
"""

import copy
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".svg", ".webp")
MODEL_EXTS = (".glb", ".gltf", ".step", ".stp", ".stl")

# type_key -> generic metadata + optional asset references (paths or URLs).
# image_2d / model_3d default to None: you supply assets via cad_dir or a
# provider. pincount is fixed where the family/size is, else None.
CONNECTOR_LIBRARY: Dict[str, dict] = {
    "deutsch_dt_2": {
        "description": "Deutsch DT 2-way",
        "manufacturer": "TE Connectivity", "series": "DT",
        "pincount": 2, "gender": "socket",
        "image_2d": None, "model_3d": None,
    },
    "deutsch_dt_4": {
        "description": "Deutsch DT 4-way",
        "manufacturer": "TE Connectivity", "series": "DT",
        "pincount": 4, "gender": "socket",
        "image_2d": None, "model_3d": None,
    },
    "deutsch_dtm_6": {
        "description": "Deutsch DTM 6-way",
        "manufacturer": "TE Connectivity", "series": "DTM",
        "pincount": 6, "gender": "socket",
        "image_2d": None, "model_3d": None,
    },
    "molex_microfit_4": {
        "description": "Molex Micro-Fit 3.0, 4 circuit",
        "manufacturer": "Molex", "series": "Micro-Fit 3.0",
        "pincount": 4, "gender": "receptacle",
        "image_2d": None, "model_3d": None,
    },
    "molex_minifit_6": {
        "description": "Molex Mini-Fit Jr., 6 circuit",
        "manufacturer": "Molex", "series": "Mini-Fit Jr.",
        "pincount": 6, "gender": "receptacle",
        "image_2d": None, "model_3d": None,
    },
    "jst_ph_3": {
        "description": "JST PH, 3 pin",
        "manufacturer": "JST", "series": "PH",
        "pincount": 3, "gender": "receptacle",
        "image_2d": None, "model_3d": None,
    },
    "dsub_9": {
        "description": "D-subminiature DE-9",
        "manufacturer": "generic", "series": "D-Sub",
        "pincount": 9, "gender": None,
        "image_2d": None, "model_3d": None,
    },
    "te_superseal_1_5_3": {
        "description": "TE Superseal 1.5, 3 way",
        "manufacturer": "TE Connectivity", "series": "Superseal 1.5",
        "pincount": 3, "gender": "socket",
        "image_2d": None, "model_3d": None,
    },
}

# metadata keys the library can back-fill onto a connector
_FILLABLE = ("manufacturer", "pincount", "gender")


@dataclass
class ConnectorAssets:
    image_2d: Optional[str] = None  # path or URL to a 2D image
    model_3d: Optional[str] = None  # path or URL to a 3D model
    source_2d: Optional[str] = None  # 'local' | 'library' | 'provider'
    source_3d: Optional[str] = None


def normalize_type(connector_type: str) -> str:
    """Canonicalise a type string to a filename-safe key.

    'Deutsch DT-4' / 'deutsch_dt_4' / 'DEUTSCH DT 4' all map to 'deutsch_dt_4'.
    """
    key = str(connector_type).strip().lower()
    key = re.sub(r"[\s\-/.]+", "_", key)
    key = re.sub(r"[^a-z0-9_]", "", key)
    return re.sub(r"_+", "_", key).strip("_")


def register_connector(type_key: str, **metadata) -> None:
    """Add or replace a connector-type entry."""
    CONNECTOR_LIBRARY[normalize_type(type_key)] = metadata


def list_connectors() -> List[tuple]:
    return sorted((k, v.get("description", "")) for k, v in CONNECTOR_LIBRARY.items())


def get_connector(type_key: str) -> Optional[dict]:
    return CONNECTOR_LIBRARY.get(normalize_type(type_key))


def _find_local(cad_dir, key, exts) -> Optional[str]:
    d = Path(cad_dir)
    for ext in exts:
        f = d / f"{key}{ext}"
        if f.exists():
            return str(f)
    return None


def resolve_connector_assets(
    connector_type: Optional[str],
    cad_dir: Optional[str] = None,
    image_provider: Optional[Callable[[str, Optional[dict]], Optional[str]]] = None,
) -> ConnectorAssets:
    """Resolve the 2D image and 3D model for a connector type (see module doc)."""
    assets = ConnectorAssets()
    if not connector_type:
        return assets
    key = normalize_type(connector_type)
    entry = CONNECTOR_LIBRARY.get(key)

    # 1) local files by naming convention
    if cad_dir:
        img = _find_local(cad_dir, key, IMAGE_EXTS)
        if img:
            assets.image_2d, assets.source_2d = img, "local"
        model = _find_local(cad_dir, key, MODEL_EXTS)
        if model:
            assets.model_3d, assets.source_3d = model, "local"

    # 2) library asset references
    if entry:
        if not assets.image_2d and entry.get("image_2d"):
            assets.image_2d, assets.source_2d = entry["image_2d"], "library"
        if not assets.model_3d and entry.get("model_3d"):
            assets.model_3d, assets.source_3d = entry["model_3d"], "library"

    # 3) provider for the 2D image (e.g. distributor product photo)
    if not assets.image_2d and image_provider:
        url = image_provider(connector_type, entry)
        if url:
            assets.image_2d, assets.source_2d = url, "provider"

    return assets


def library_defaults(connector_type: str) -> dict:
    """Return the metadata a connector type contributes, for back-filling."""
    entry = get_connector(connector_type)
    if not entry:
        return {}
    return {k: entry[k] for k in _FILLABLE if entry.get(k) is not None}


def apply_connector_types(data: dict) -> dict:
    """Back-fill connector metadata from the library for any connector that
    declares a ``connector_type`` (or inherits the global ``options`` default).

    Only fills attributes the connector did not set itself, so explicit values
    always win. Returns a copy; the input is not mutated.
    """
    if not isinstance(data, dict) or "connectors" not in data:
        return data
    default_type = (data.get("options") or {}).get("connector_type")
    result = copy.deepcopy(data)
    for name, attrs in (result.get("connectors") or {}).items():
        if not isinstance(attrs, dict):
            continue
        ctype = attrs.get("connector_type", default_type)
        if not ctype:
            continue
        attrs.setdefault("connector_type", ctype)
        for k, v in library_defaults(ctype).items():
            attrs.setdefault(k, v)
    return result
