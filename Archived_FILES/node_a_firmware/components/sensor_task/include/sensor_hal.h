#ifndef SENSOR_HAL_H
#define SENSOR_HAL_H

#include <stdint.h>
#include "esp_err.h"

/**
 * Hardware Abstraction Layer for Node A sensors.
 *
 * This interface decouples the sensor task from specific hardware.
 * Two implementations exist:
 *   - sensor_hal_mock.c: generates simulated data (for pre-hardware testing)
 *   - sensor_hal_real.c: reads real DHT20, BH1750, and PIR via I2C/GPIO
 *
 * Selected at build time via CONFIG_USE_MOCK_SENSORS in Kconfig.
 */

/**
 * Sensor reading structure.
 */
typedef struct {
    int16_t  temperature;    /* °C × 100 (e.g., 2350 = 23.50°C) */
    uint16_t humidity;       /* %RH × 100 */
    uint16_t light_level;    /* lux */
    uint8_t  occupancy;      /* 0 = vacant, 1 = occupied */
} sensor_readings_t;

/**
 * Initialize sensor hardware (or mock subsystem).
 * Must be called once before reading.
 */
esp_err_t sensor_hal_init(void);

/**
 * Read environmental sensors (temperature, humidity, light).
 */
esp_err_t sensor_hal_read_env(int16_t *temp, uint16_t *humidity, uint16_t *light);

/**
 * Get current occupancy state from PIR sensor.
 * Returns 0 (vacant) or 1 (occupied).
 */
uint8_t sensor_hal_get_occupancy(void);

#endif /* SENSOR_HAL_H */
