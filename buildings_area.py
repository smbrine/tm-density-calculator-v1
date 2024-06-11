import requests
from shapely.geometry import Point, Polygon, shape
import geopandas as gpd
from shapely.ops import unary_union

# Define the Overpass API endpoint
overpass_url = (
    "http://overpass-api.de/api/interpreter"
)

# Define the Overpass API query to get residential areas within Moscow
overpass_query_residential = """
[out:json];
area[name="Moscow"]->.searchArea;
(
  way["landuse"="residential"](area.searchArea);
  relation["landuse"="residential"](area.searchArea);
);
out body;
>;
out skel qt;
"""

# Make the request to the Overpass API
response_residential = requests.get(
    overpass_url,
    params={"data": overpass_query_residential},
)
data_residential = response_residential.json()

# Parse the boundary data
elements_residential = data_residential[
    "elements"
]


# Function to convert way nodes to coordinates
def get_way_coords(way, nodes_dict):
    return [
        (
            nodes_dict[node_id]["lon"],
            nodes_dict[node_id]["lat"],
        )
        for node_id in way["nodes"]
    ]


# Create a dictionary of nodes for quick lookup
nodes_dict = {
    element["id"]: element
    for element in elements_residential
    if element["type"] == "node"
}

# Collect residential area polygons
residential_areas = []
for element in elements_residential:
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
            residential_areas.append(
                Polygon(coords)
            )
    elif (
        element["type"] == "relation"
        and "tags" in element
        and element["tags"].get("landuse")
        == "residential"
    ):
        for member in element["members"]:
            if member["type"] == "way":
                way = next(
                    (
                        el
                        for el in elements_residential
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
                        residential_areas.append(
                            Polygon(coords)
                        )

# Union all residential area polygons to handle multipolygons
residential_area_union = unary_union(
    residential_areas
)

# Query to get buildings within the residential area
overpass_query_buildings = """
[out:json];
(
  way["building"](poly:"{}");
);
out body;
>;
out skel qt;
""".format(
    " ".join(
        f"{lat} {lon}"
        for lon, lat in residential_area_union.exterior.coords
    )
)

# Make the request to the Overpass API
response_buildings = requests.get(
    overpass_url,
    params={"data": overpass_query_buildings},
)
data_buildings = response_buildings.json()

# Parse the building data
elements_buildings = data_buildings["elements"]

# Create a dictionary of nodes for quick lookup
nodes_dict_buildings = {
    element["id"]: element
    for element in elements_buildings
    if element["type"] == "node"
}

# Collect building polygons
building_polygons = []
for element in elements_buildings:
    if (
        element["type"] == "way"
        and "tags" in element
        and "building" in element["tags"]
    ):
        coords = get_way_coords(
            element, nodes_dict_buildings
        )
        if coords:
            building_polygons.append(
                Polygon(coords)
            )


# Function to calculate the total area of building polygons
def calculate_total_building_area(
    building_polygons,
):
    gdf_buildings = gpd.GeoDataFrame(
        {"geometry": building_polygons},
        crs="EPSG:4326",
    )
    gdf_buildings_utm = gdf_buildings.to_crs(
        epsg=32637
    )  # Reproject to UTM for accurate area calculation
    total_area_sq_meters = (
        gdf_buildings_utm.geometry.area.sum()
    )
    return (
        total_area_sq_meters / 1e6
    )  # Convert to square kilometers


# Calculate the total area of buildings
total_building_area_km2 = (
    calculate_total_building_area(
        building_polygons
    )
)
print(
    f"Total area of buildings within the residential areas in Moscow: {total_building_area_km2:.2f} square kilometers"
)
