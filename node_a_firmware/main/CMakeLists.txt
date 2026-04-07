idf_component_register(
    SRCS "main.c"
    INCLUDE_DIRS "."
    REQUIRES mesh_comm sensor_task health_task common nvs_flash
)
