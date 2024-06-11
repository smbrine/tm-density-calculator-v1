import requests
from shapely.geometry import (
    Point,
    Polygon,
    MultiPolygon,
)
import geopandas as gpd
from shapely.ops import unary_union


def get_overpass_data(
    query,
    url="http://overpass-api.de/api/interpreter",
):
    response = requests.get(
        url, params={"data": query}
    )
    response.raise_for_status()  # Ensure we catch any HTTP errors
    return response.json()


def parse_elements(data):
    return data["elements"]


def create_nodes_dict(elements):
    return {
        element["id"]: element
        for element in elements
        if element["type"] == "node"
    }


def get_way_coords(way, nodes_dict):
    return [
        (
            nodes_dict[node_id]["lon"],
            nodes_dict[node_id]["lat"],
        )
        for node_id in way["nodes"]
        if node_id in nodes_dict
    ]


def collect_residential_areas(
    elements, nodes_dict
):
    residential_areas = []
    for element in elements:
        if (
            element["type"] == "way"
            and "tags" in element
            and element["tags"].get("landuse")
            == "residential"
        ):
            coords = get_way_coords(
                element, nodes_dict
            )
            if coords:
                try:
                    residential_areas.append(
                        Polygon(coords)
                    )
                except ValueError as e:
                    print(
                        f"Invalid polygon with coords: {coords} - Error: {e}"
                    )
        elif (
            element["type"] == "relation"
            and "tags" in element
            and element["tags"].get("landuse")
            == "residential"
        ):
            member_polygons = []
            for member in element["members"]:
                if member["type"] == "way":
                    way = next(
                        (
                            el
                            for el in elements
                            if el["id"]
                            == member["ref"]
                        ),
                        None,
                    )
                    if way:
                        coords = get_way_coords(
                            way, nodes_dict
                        )
                        if coords:
                            try:
                                member_polygons.append(
                                    Polygon(
                                        coords
                                    )
                                )
                            except (
                                ValueError
                            ) as e:
                                print(
                                    f"Invalid member polygon with coords: {coords} - Error: {e}"
                                )
            if member_polygons:
                try:
                    residential_areas.append(
                        unary_union(
                            member_polygons
                        )
                    )
                except ValueError as e:
                    print(
                        f"Union error with member polygons: {member_polygons} - Error: {e}"
                    )
    return residential_areas


def get_union_of_areas(polygons):
    if not polygons:
        return None
    try:
        return unary_union(polygons)
    except ValueError as e:
        print(
            f"Union error with polygons: {polygons} - Error: {e}"
        )
        return None


def is_within_residential_area(
    lat, lon, residential_union
):
    if not residential_union:
        return False
    point = Point(lon, lat)
    return residential_union.contains(point)


def convert_to_geodataframe(
    polygon, crs="EPSG:4326"
):
    return gpd.GeoDataFrame(
        {"geometry": [polygon]}, crs=crs
    )


def reproject_to_utm(gdf, epsg):
    return gdf.to_crs(epsg=epsg)


def calculate_area_sq_kilometers(gdf):
    area_sq_meters = gdf.geometry.area[0]
    return area_sq_meters / 1e6


def get_residential_area_query(city_name):
    return f"""
    [out:json];
    area[name="{city_name}"]->.searchArea;
    (
      way["landuse"="residential"](area.searchArea);
      relation["landuse"="residential"](area.searchArea);
    );
    out body;
    >;
    out skel qt;
    """


def process_residential_areas(
    city_name, coord_lat, coord_lon
):
    query = get_residential_area_query(city_name)
    data = get_overpass_data(query)

    # Debug: Print the raw data received
    print(f"Raw data from Overpass API: {data}")

    elements = parse_elements(data)
    nodes_dict = create_nodes_dict(elements)

    # Debug: Print the number of nodes and elements
    print(
        f"Total nodes: {len(nodes_dict)}, Total elements: {len(elements)}"
    )

    residential_areas = collect_residential_areas(
        elements, nodes_dict
    )

    # Debug: Print the number of residential areas collected
    print(
        f"Collected {len(residential_areas)} residential areas"
    )

    residential_union = get_union_of_areas(
        residential_areas
    )

    if is_within_residential_area(
        coord_lat, coord_lon, residential_union
    ):
        print(
            f"The coordinate ({coord_lat}, {coord_lon}) falls within a residential area in {city_name}."
        )
    else:
        print(
            f"The coordinate ({coord_lat}, {coord_lon}) does not fall within a residential area in {city_name}."
        )

    if residential_union:
        gdf = convert_to_geodataframe(
            residential_union
        )
        gdf_utm = reproject_to_utm(
            gdf, epsg=32637
        )  # Assuming the UTM zone for Moscow
        area_sq_kilometers = (
            calculate_area_sq_kilometers(gdf_utm)
        )
        print(
            f"Total residential area in {city_name}: {area_sq_kilometers:.2f} square kilometers"
        )
    else:
        print(
            f"No residential areas found for {city_name}."
        )


# Example usage
city_name = "Moscow"
coord_lat, coord_lon = 55.8963, 37.3989
process_residential_areas(
    city_name, coord_lat, coord_lon
)
