#include "health_task.h"
#include "max17048.h"
#include "mesh_comm.h"
#include "message.h"
#include "common.h"

#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#ifndef CONFIG_HEALTH_REPORT_INTERVAL_MS
#define CONFIG_HEALTH_REPORT_INTERVAL_MS 120000
#endif

#define HEALTH_TASK_STACK_SIZE  4096
#define HEALTH_TASK_PRIORITY    (tskIDLE_PRIORITY + 1)

/* Track whether the fuel gauge was successfully initialized */
static bool s_fuel_gauge_ok = false;

/* Collect and send a single health report. Used by both the task loop and one-shot API. */
static esp_err_t health_send_once(void)
{
    uint32_t heap_free = esp_get_free_heap_size();
    uint32_t uptime_ms = common_get_uptime_ms();

    /* Battery readings from MAX17048 (0 if not available) */
    uint16_t battery_mv  = max17048_read_voltage_mv();
    uint8_t  battery_soc = max17048_read_soc();

    /*
     * ESP32 (original) has no accessible internal temp sensor via driver API.
     * Use the DHT20 ambient temperature from the sensor task as a proxy,
     * or report a fixed "not available" value. The DHT20 is close enough
     * on the same board to be useful.
     * TODO: Read DHT20 temp here if cross-task sharing is added.
     */
    int16_t chip_temp_c100 = 0;  /* 0 = not available on ESP32 original */

    /* Get real RSSI from last received mesh frame */
    int8_t rssi = mesh_comm_get_last_rssi();

    ESP_LOGI(TAG_HEALTH, "Health: battery=%u mV (%u%%) chip_temp=%.2f°C "
             "heap=%lu bytes uptime=%lu ms rssi=%d dBm",
             battery_mv, battery_soc,
             chip_temp_c100 / 100.0f,
             (unsigned long)heap_free,
             (unsigned long)uptime_ms,
             rssi);

    mesh_frame_t frame = {0};
    memcpy(frame.header.dst_mac, GATEWAY_MAC, 6);
    frame.header.ttl = MESH_DEFAULT_TTL;

    health_payload_t payload = {
        .battery_mv  = battery_mv,
        .battery_soc = battery_soc,
        .chip_temp_c = chip_temp_c100,
        .rssi_dbm    = rssi,
        .heap_free   = heap_free,
        .uptime_ms   = uptime_ms,
    };
    health_payload_pack(&frame, &payload);

    esp_err_t ret = mesh_comm_send(&frame);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG_HEALTH, "Failed to send HEALTH frame");
    } else {
        ESP_LOGD(TAG_HEALTH, "HEALTH frame sent");
    }
    return ret;
}

static void health_task(void *arg)
{
    (void)arg;

    /* Initialize MAX17048 fuel gauge (non-fatal if it fails) */
    esp_err_t fg_ret = max17048_init();
    s_fuel_gauge_ok = (fg_ret == ESP_OK);

    ESP_LOGI(TAG_HEALTH, "Health task running (interval=%d ms, fuel_gauge=%s)",
             CONFIG_HEALTH_REPORT_INTERVAL_MS,
             s_fuel_gauge_ok ? "YES" : "NO");

    while (1) {
        health_send_once();
        vTaskDelay(pdMS_TO_TICKS(CONFIG_HEALTH_REPORT_INTERVAL_MS));
    }
}

esp_err_t health_report_once(void)
{
    return health_send_once();
}

esp_err_t health_task_start(void)
{
    BaseType_t ret = xTaskCreate(
        health_task,
        "health_task",
        HEALTH_TASK_STACK_SIZE,
        NULL,
        HEALTH_TASK_PRIORITY,
        NULL
    );

    if (ret != pdPASS) {
        ESP_LOGE(TAG_HEALTH, "Failed to create health task");
        return ESP_ERR_NO_MEM;
    }

    ESP_LOGI(TAG_HEALTH, "Health task started (interval=%d ms)",
             CONFIG_HEALTH_REPORT_INTERVAL_MS);
    return ESP_OK;
}
