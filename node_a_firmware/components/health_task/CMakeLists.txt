idf_component_register(
    SRCS "health_task.c" "max17048.c"
    INCLUDE_DIRS "include"
    REQUIRES mesh_comm message common driver esp_timer
)
