import overpass

latitude = 55.8962
longitude = 37.3992

api = overpass.API()

response = api.get(
    f'way[landuse="residential"]({latitude - .001},{longitude - .001},{latitude + .001},{longitude + .001});',
    verbosity="geom",
)
