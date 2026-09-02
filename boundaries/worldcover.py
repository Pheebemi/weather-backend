"""
Shared access to ESA WorldCover land-cover data.

WorldCover v200 (2021, 10m) ships as public Cloud-Optimized GeoTIFFs on
AWS Open Data — no Google Earth Engine account or credentials needed. Only
the pixels covering a given geometry are fetched, via HTTP range requests.
"""

import math

import numpy as np
import rasterio
from rasterio.mask import mask
from rasterio.merge import merge

TILE_URL = (
    "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
    "ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
)

# Class codes — https://esa-worldcover.org/en/data-access
TREE_COVER = 10
CROPLAND = 40
NODATA = 0

SOURCE_LABEL = "ESA WorldCover v200 2021 (10m, satellite-derived, auto-generated)"


def tiles_for_bounds(bounds) -> list[str]:
    """WorldCover ships 3°x3° tiles named by their south-west corner."""
    minx, miny, maxx, maxy = bounds
    tiles = []
    for lat in range(int(math.floor(miny / 3) * 3), int(math.floor(maxy / 3) * 3) + 1, 3):
        for lon in range(int(math.floor(minx / 3) * 3), int(math.floor(maxx / 3) * 3) + 1, 3):
            ns, ew = ("N" if lat >= 0 else "S"), ("E" if lon >= 0 else "W")
            tiles.append(f"{ns}{abs(lat):02d}{ew}{abs(lon):03d}")
    return tiles


def class_percentages(geometry, classes: set[int]) -> float:
    """Percent of a geometry's WorldCover pixels falling in `classes`."""
    sources = [
        rasterio.open("/vsicurl/" + TILE_URL.format(tile=t))
        for t in tiles_for_bounds(geometry.bounds)
    ]
    try:
        if len(sources) == 1:
            image, _ = mask(sources[0], [geometry], crop=True, filled=True, nodata=NODATA)
        else:
            image, _ = merge(sources, bounds=geometry.bounds, nodata=NODATA)
        band = image[0]
        valid = band[band != NODATA]
        if valid.size == 0:
            raise ValueError("no WorldCover pixels covered this geometry")
        return 100.0 * np.count_nonzero(np.isin(valid, list(classes))) / valid.size
    finally:
        for src in sources:
            src.close()
