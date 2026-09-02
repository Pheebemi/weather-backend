"""
Shared loader for GRID3 operational ward boundaries.

GRID3 (data.grid3.org) is the primary ward-boundary source named in
CLAUDE.md; the HDX COD admin3 layer is the backup. GRID3 v3.0 carries no
pcodes, so ward codes are derived deterministically here — the importer
and the farmland batch job both call this, so a ward's code means the same
thing in both.
"""

import re
import unicodedata

import geopandas as gpd

GRID3_WARDS_HDX_URL = (
    "https://data.humdata.org/dataset/db8702fe-7d11-484e-aed5-31b3fc32850c/"
    "resource/37e5f2c6-ec94-4060-932d-755b99dd963e/download/grid3_nga_operational_wards_v3_0.gpkg"
)

NORTHERN_STATES = [
    "Adamawa", "Bauchi", "Benue", "Borno", "Gombe", "Jigawa", "Kaduna",
    "Kano", "Katsina", "Kebbi", "Kogi", "Kwara", "Nasarawa", "Niger",
    "Plateau", "Sokoto", "Taraba", "Yobe", "Zamfara",
]


def normalize(name: str) -> str:
    """Fold spelling/spacing/accent variants so names can be compared."""
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = text.encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _slug(name: str, length: int) -> str:
    return normalize(name)[:length] or "x"


def load_grid3_wards(path, states=None) -> gpd.GeoDataFrame:
    """
    Read the GRID3 ward geopackage and attach a stable `ward_code`.

    Sorted before coding so the generated codes are reproducible across
    runs, and de-duplicated with a numeric suffix where two wards in one
    LGA normalize to the same slug.
    """
    gdf = gpd.read_file(path)
    if states is not None:
        gdf = gdf[gdf["state"].isin(states)]
    gdf = gdf.sort_values(["state", "lga", "ward"]).reset_index(drop=True)

    codes, seen = [], {}
    for row in gdf.itertuples():
        base = f"{row.statecode}-{_slug(row.lga, 14)}-{_slug(row.ward, 18)}"
        seen[base] = seen.get(base, 0) + 1
        codes.append(base if seen[base] == 1 else f"{base}-{seen[base]}")
    gdf["ward_code"] = codes
    return gdf
