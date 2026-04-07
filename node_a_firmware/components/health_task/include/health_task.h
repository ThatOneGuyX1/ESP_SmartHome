#ifndef HEALTH_TASK_H
#define HEALTH_TASK_H

#include "esp_err.h"

/**
 * Start the device health reporting task.
 * Creates a FreeRTOS task that periodically reports chip temperature,
 * free heap, uptime, and RSSI via HEALTH frames over the mesh.
 *
 * Reporting interval is configured via CONFIG_HEALTH_REPORT_INTERVAL_MS (default 120000).
 */
esp_err_t health_task_start(void);

/**
 * Send a single health report immediately (no task created).
 * Intended for deep-sleep nodes that need to report health before sleeping.
 */
esp_err_t health_report_once(void);

#endif /* HEALTH_TASK_H */
