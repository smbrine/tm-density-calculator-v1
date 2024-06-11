from typing import Any

import overpass
import shapely
from osm2geojson import json2geojson
from pyproj import Transformer
from shapely import Polygon, geometry
import json
from math import pi, sin

from shapely.geometry import shape

WGS84_RADIUS = 6378137


class DensityCalculator:
    def __init__(
        self,
        overpass_endpoint: str = "https://overpass-api.de/api/interpreter",
        debug: bool = False,
        debug_level=0,
    ):
        self.debug = debug
        self.debug_level = debug_level
        self._log(
            f"Running DensityCalculator in debug mode at level {debug_level}"
        )
        self.api = overpass.API(overpass_endpoint)
        self.transformer = Transformer.from_crs(
            "EPSG:4326", "EPSG:3857"
        )

    async def find_closest_residential_area(
        self,
        latitude: float,
        longitude: float,
        verbosity: str = "geom",
    ):
        search_coef = 0.001
        while search_coef < 0.1:
            res = (
                await self._req_closest_res_area(
                    latitude,
                    longitude,
                    verbosity,
                    search_coef,
                )
            )

            for feature in res["features"]:
                if (
                    feature["geometry"]["type"]
                    == "MultiPolygon"
                ):
                    poly = geometry.Polygon(
                        feature["geometry"][
                            "coordinates"
                        ][0][0]
                    )
                elif (
                    feature["geometry"]["type"]
                    == "Polygon"
                ):
                    poly = geometry.Polygon(
                        feature["geometry"][
                            "coordinates"
                        ][0]
                    )
                else:
                    try:
                        poly = geometry.Polygon(
                            feature["geometry"][
                                "coordinates"
                            ]
                        )
                    except TypeError as e:
                        print(feature)
                        raise e
                pt = geometry.Point(
                    longitude, latitude
                )
                if poly.contains(pt):
                    return feature
            search_coef *= 10

        return None

    async def _req_closest_res_area(
        self,
        latitude,
        longitude,
        verbosity,
        search_coef,
    ):
        query = [
            f"way[landuse]({latitude - search_coef},{longitude - search_coef},{latitude + search_coef},{longitude + search_coef});",
            f"relation[landuse]({latitude - search_coef},{longitude - search_coef},{latitude + search_coef},{longitude + search_coef});",
        ]
        try:
            out = {
                "type": "FeatureCollection",
                "features": [],
            }
            for q in query:
                res = self.api.get(
                    q,
                    verbosity=verbosity,
                    responseformat="json",
                )
                res = json2geojson(res)
                out["features"].extend(
                    res["features"]
                )
        except overpass.UnknownOverpassError as e:
            print(query)
            print(e)
            return {"features": []}
        return out

    async def get_bounding_box(
        self, features: list[dict]
    ):
        # multipoly = shapely.MultiPolygon([feature['geometry'].get('coordinates')[0] for feature in features])
        # return multipoly.bounds
        max_lat = max_lon = 0
        min_lat = min_lon = 0

        for feature in features or [features]:
            try:
                coordinates = feature["geometry"][
                    "coordinates"
                ]
            except KeyError as e:
                print(feature)
                raise e
            if (
                feature["geometry"]["type"]
                == "MultiPolygon"
            ):
                coordinates = coordinates[0][0]
            elif (
                feature["geometry"]["type"]
                == "Polygon"
            ):
                coordinates = coordinates[0]
            for lat, lon in coordinates:
                max_lat = max(lat, max_lat or lat)
                max_lon = max(lon, max_lon or lon)
                min_lat = min(lat, min_lat or lat)
                min_lon = min(lon, min_lon or lon)

        return max_lat, max_lon, min_lat, min_lon

    async def calculate_geodesic_area(
        self,
        feature: dict[str, dict[str, list]],
        debug=False,
    ):
        try:
            area = await self._calc_area(
                feature["geometry"]
            )
        except Exception as e:
            print(feature)
            raise e
        if area:
            return area
        else:
            raise ValueError(feature)

    async def calculate_buildings_total_area(
        self, buildings
    ):
        total_area = 0
        for building in buildings["features"]:
            levels = (
                1
                if not (
                    tags := building[
                        "properties"
                    ].get("tags")
                )
                else int(
                    tags.get("building:levels")
                    or 1
                )
            )
            total_area += (
                await self.calculate_geodesic_area(
                    building
                )
                * levels
            )
        return total_area

    async def get_buildings_within_bbox(
        self,
        bounding_polygon,
        verbosity: str = "geom",
    ):
        max_lat, max_lon, min_lat, min_lon = (
            await self.get_bounding_box(
                [bounding_polygon]
            )
        )
        # building_cats = ['apartments', 'yes', 'school', 'kindergarten', 'retail', 'hospital']
        query = [
            f"way[building]({min_lon},{min_lat},{max_lon},{max_lat});",
            f"relation[building]({min_lon},{min_lat},{max_lon},{max_lat});"
            # for bc in building_cats
        ]
        out = {
            "type": "FeatureCollection",
            "features": [],
        }
        geo = bounding_polygon["geometry"]
        main_poly: Polygon = shape(geo)
        for q in query:
            res = self.api.get(
                q,
                verbosity=verbosity,
                responseformat="json",
            )
            res = json2geojson(res)
            for feature in res["features"]:
                geo = feature["geometry"]
                poly: Polygon = shape(geo)
                if poly.covered_by(main_poly):
                    out["features"].append(
                        feature
                    )
        return out

    async def calculate_features_total_area(
        self,
        features: list[dict] = None,
        debug=False,
    ) -> float:
        total_area = 0
        for feature in features:
            total_area += await self.calculate_geodesic_area(
                feature, debug=debug
            )
        return total_area

    async def _calc_area(self, geometry):

        if isinstance(geometry, str):
            geometry = json.loads(geometry)

        assert isinstance(geometry, dict)

        _area = 0

        if geometry["type"] == "Polygon":
            return await self._polygon__area(
                geometry["coordinates"]
            )
        elif geometry["type"] == "MultiPolygon":
            for obj in geometry["coordinates"]:
                _area += (
                    await self._polygon__area(obj)
                )
        elif (
            geometry["type"]
            == "GeometryCollection"
        ):
            for obj in geometry["geometries"]:
                _area += await self._calc_area(
                    obj
                )
        elif geometry["type"] == "LineString":
            return await self._ring__area(
                geometry["coordinates"]
            )

        return _area

    async def _polygon__area(self, coordinates):
        assert isinstance(
            coordinates, (list, tuple)
        )

        _area = 0
        if len(coordinates) > 0:
            _area += abs(
                await self._ring__area(
                    coordinates[0]
                )
            )

            for i in range(1, len(coordinates)):
                _area -= abs(
                    await self._ring__area(
                        coordinates[i]
                    )
                )

        return _area

    def _rad(self, value):
        return value * pi / 180

    async def _ring__area(self, coordinates):
        """
        Calculate the approximate _area of the polygon were it projected onto
            the earth.  Note that this _area will be positive if ring is oriented
            clockwise, otherwise it will be negative.

        Reference:
            Robert. G. Chamberlain and William H. Duquette, "Some Algorithms for
            Polygons on a Sphere", JPL Publication 07-03, Jet Propulsion
            Laboratory, Pasadena, CA, June 2007 http://trs-new.jpl.nasa.gov/dspace/handle/2014/40409

        @Returns

        {float} The approximate signed geodesic _area of the polygon in square meters.
        """

        assert isinstance(
            coordinates, (list, tuple)
        )

        _area = 0
        coordinates_length = len(coordinates)

        if coordinates_length > 2:
            for i in range(0, coordinates_length):
                if i == (coordinates_length - 2):
                    lower_index = (
                        coordinates_length - 2
                    )
                    middle_index = (
                        coordinates_length - 1
                    )
                    upper_index = 0
                elif i == (
                    coordinates_length - 1
                ):
                    lower_index = (
                        coordinates_length - 1
                    )
                    middle_index = 0
                    upper_index = 1
                else:
                    lower_index = i
                    middle_index = i + 1
                    upper_index = i + 2

                p1 = coordinates[lower_index]
                p2 = coordinates[middle_index]
                p3 = coordinates[upper_index]

                _area += (
                    self._rad(p3[0])
                    - self._rad(p1[0])
                ) * sin(self._rad(p2[1]))

            _area = (
                _area
                * WGS84_RADIUS
                * WGS84_RADIUS
                / 2
            )

        return _area

    def _log(self, *msg: Any, level: int = 1):
        pass
        # if self.debug:
        # print(
        #     f"{self.__class__.__name__}: {str(msg)}\n"
        # )
