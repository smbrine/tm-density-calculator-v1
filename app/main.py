import asyncio
import json
import logging

from grpc import aio as grpc_aio
from grpc_reflection.v1alpha import reflection

from app import settings
from proto import (
    density_calculator_service_pb2,
    density_calculator_service_pb2_grpc,
)
from tools import DensityCalculator

dc = DensityCalculator(debug=settings.DEBUG)
logging.basicConfig(
    level=(
        logging.DEBUG
        if settings.DEBUG
        else logging.ERROR
    )
)


class DensityCalculatorServiceServicer(
    density_calculator_service_pb2_grpc.DensityCalculatorServiceServicer
):
    async def CalculateDensity(
        self, request, context
    ):
        lat, lon = (
            request.latitude,
            request.longitude,
        )

        res_area = await dc.find_closest_residential_area(
            lat, lon
        )
        if res_area:
            buildings = await dc.get_buildings_within_bbox(
                res_area
            )
            res_area_size = await dc.calculate_features_total_area(
                [res_area], debug=True
            )
            buildings_size = await dc.calculate_features_total_area(
                buildings["features"]
            )

            buildings_total_area = await dc.calculate_buildings_total_area(
                buildings
            )
            houses = {
                "features": [
                    building
                    for building in buildings[
                        "features"
                    ]
                    if building["properties"][
                        "tags"
                    ].get("building")
                    == "apartments"
                ]
            }
            total_flats = 0
            for house in houses["features"]:
                if num_flats_in_house := house[
                    "properties"
                ]["tags"].get("building:flats"):
                    num_flats_in_house = int(
                        num_flats_in_house
                    )
                else:
                    num_flats_in_house = (
                        await dc.calculate_geodesic_area(
                            house
                        )
                        * int(
                            house["properties"][
                                "tags"
                            ].get(
                                "building:levels"
                            )
                            or 1
                        )
                        / 35
                    )
                total_flats += num_flats_in_house
            non_houses = {
                "features": [
                    building
                    for building in buildings[
                        "features"
                    ]
                    if building["properties"][
                        "tags"
                    ].get("building")
                    != "apartments"
                ]
            }
            living_buildings_total_area = await dc.calculate_buildings_total_area(
                houses
            )
            living_buildings_area = await dc.calculate_features_total_area(
                houses["features"]
            )
            non_living_buildings_area = await dc.calculate_features_total_area(
                non_houses["features"]
            )
            maximum_people = total_flats * 3
            built_percent = (
                buildings_size / res_area_size
            ) * 100
            return density_calculator_service_pb2.CalculateDensityResponse(
                is_residential_found=res_area
                is not None,
                residential_area=json.dumps(
                    res_area, ensure_ascii=False
                ),
                residential_area_size=res_area_size,
                is_building_found=len(
                    buildings["features"]
                )
                != 0,
                buildings=json.dumps(
                    buildings, ensure_ascii=False
                ),
                living_buildings_area=living_buildings_area,
                non_living_buildings_area=non_living_buildings_area,
                buildings_area_size=buildings_size,
                built_percent=built_percent,
                buildings_density=buildings_total_area
                / (res_area_size / 10_000),
                living_buildings_density=living_buildings_total_area
                / (res_area_size / 10_000),
                max_people=int(maximum_people),
                people_density=int(maximum_people / (res_area_size / 10_000)),
                free_area_per_person=(
                    res_area_size - buildings_size
                )
                / (maximum_people or 1),
            )
        else:
            return density_calculator_service_pb2.CalculateDensityResponse(
                is_residential_found=False,
                residential_area="",
                residential_area_size=0,
                is_building_found=False,
                buildings="",
                living_buildings_area=0,
                non_living_buildings_area=0,
                buildings_area_size=0,
                built_percent=0,
                buildings_density=0,
                living_buildings_density=0,
                max_people=0,
                people_density=0,
                free_area_per_person=0,
            )


async def serve():
    server = grpc_aio.server(
        options=[
            (
                "grpc.max_send_message_length",
                50 * 1024 * 1024,
            ),
            (
                "grpc.max_receive_message_length",
                50 * 1024 * 1024,
            ),
        ]
    )
    density_calculator_service_pb2_grpc.add_DensityCalculatorServiceServicer_to_server(
        DensityCalculatorServiceServicer(),
        server,
    )
    listen_addr = f"[::]:{settings.BIND_PORT}"
    service_names = (
        density_calculator_service_pb2.DESCRIPTOR.services_by_name[
            "DensityCalculatorService"
        ].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(
        service_names, server
    )

    server.add_insecure_port(listen_addr)
    await server.start()
    try:
        await server.wait_for_termination()
    finally:
        await server.stop(0)


if __name__ == "__main__":
    asyncio.run(serve())
