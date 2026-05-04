#ifndef SENSOR_TASK_H
#define SENSOR_TASK_H

#include <stdint.h>
#include "esp_err.h"

/**
 * Start the sensor sampling task (or one-shot deep-sleep cycle).
 *
 * Behavior depends on CONFIG_NODE_ALWAYS_ON_RELAY:
 *   - Enabled:  creates a FreeRTOS task with a vTaskDelay loop (radio stays on).
 *   - Disabled: performs a single read, sends data, then enters deep sleep.
 *               Wakes via timer (CONFIG_SENSOR_SAMPLE_INTERVAL_MS) or PIR ext1.
 */
esp_err_t sensor_task_start(void);

/**
 * Update temperature alert thresholds at runtime.
 * Values are in °C × 100 (e.g., 3500 = 35.00°C).
 * Can be called from a mesh command handler to implement dynamic thresholds.
 */
void sensor_task_set_temp_thresholds(int16_t high_c100, int16_t low_c100);

/**
 * Read current temperature alert thresholds.
 * Pass NULL for any value you don't need.
 */
void sensor_task_get_temp_thresholds(int16_t *high_c100, int16_t *low_c100);

#endif /* SENSOR_TASK_H */
