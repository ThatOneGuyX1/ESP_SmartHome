if(CONFIG_USE_MOCK_SENSORS)
    set(HAL_SRC "sensor_hal_mock.c")
else()
    set(HAL_SRC "sensor_hal_real.c")
endif()

idf_component_register(
    SRCS "sensor_task.c" "${HAL_SRC}"
    INCLUDE_DIRS "include"
    REQUIRES mesh_comm message common
    PRIV_REQUIRES driver esp_timer
)
