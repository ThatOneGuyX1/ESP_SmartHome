idf_component_register(
    SRCS "mesh_comm.c"
    INCLUDE_DIRS "include"
    REQUIRES esp_wifi esp_event message common
)
