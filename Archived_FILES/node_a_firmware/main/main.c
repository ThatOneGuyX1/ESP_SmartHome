#include <string.h>
#include "esp_log.h"
#include "esp_event.h"
#include "esp_wifi.h"
#include "nvs_flash.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "common.h"
#include "mesh_comm.h"
#include "message.h"
#include "sensor_task.h"
#include "health_task.h"

/* ── Command handler — processes COMMAND frames from the gateway ──── */
static void command_handler(const mesh_frame_t *frame)
{
    if (frame->header.msg_type != MSG_TYPE_COMMAND) {
        return;  /* only handle COMMAND frames */
    }

    if (frame->header.payload_len < 1) {
        ESP_LOGW(TAG_MAIN, "COMMAND frame with empty payload");
        return;
    }

    const command_payload_t *cmd = (const command_payload_t *)frame->payload;

    switch (cmd->command_id) {
    case CMD_SET_TEMP_THRESHOLDS: {
        if (frame->header.payload_len < 5) {
            ESP_LOGW(TAG_MAIN, "SET_TEMP_THRESHOLDS: payload too short");
            break;
        }
        /* data[0-1] = high threshold (little-endian int16)
         * data[2-3] = low threshold  (little-endian int16) */
        int16_t high, low;
        memcpy(&high, &cmd->data[0], sizeof(int16_t));
        memcpy(&low,  &cmd->data[2], sizeof(int16_t));

        ESP_LOGI(TAG_MAIN, "CMD: Set temp thresholds high=%.2f°C low=%.2f°C",
                 high / 100.0f, low / 100.0f);
        sensor_task_set_temp_thresholds(high, low);
        break;
    }

    case CMD_SET_SAMPLE_INTERVAL: {
        if (frame->header.payload_len < 5) {
            ESP_LOGW(TAG_MAIN, "SET_SAMPLE_INTERVAL: payload too short");
            break;
        }
        uint32_t interval_ms;
        memcpy(&interval_ms, &cmd->data[0], sizeof(uint32_t));
        ESP_LOGI(TAG_MAIN, "CMD: Set sample interval to %lu ms",
                 (unsigned long)interval_ms);
        /* TODO: implement runtime interval change (requires task notification) */
        break;
    }

    case CMD_REQUEST_READING:
        ESP_LOGI(TAG_MAIN, "CMD: Immediate reading requested");
        /* TODO: trigger an immediate sensor read via task notification */
        break;

    default:
        ESP_LOGW(TAG_MAIN, "CMD: Unknown command_id=0x%02X", cmd->command_id);
        break;
    }
}

void app_main(void)
{
    ESP_LOGI(TAG_MAIN, "========================================");
    ESP_LOGI(TAG_MAIN, "  Node A — Occupancy/Temp/Light Sensor");
    ESP_LOGI(TAG_MAIN, "  ECE 568 Smart Home Mesh Network");
    ESP_LOGI(TAG_MAIN, "========================================");

    /* 1. Initialize NVS (required by Wi-Fi/ESP-NOW) */
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG_MAIN, "NVS partition erased and re-initialized");
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);
    ESP_LOGI(TAG_MAIN, "NVS initialized");

    /* 2. Initialize Wi-Fi in STA mode (ESP-NOW uses Wi-Fi PHY, no AP connection) */
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    wifi_init_config_t wifi_cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&wifi_cfg));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_start());

    /* Set Wi-Fi channel for ESP-NOW */
    ESP_ERROR_CHECK(esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE));
    ESP_LOGI(TAG_MAIN, "Wi-Fi STA initialized on channel %d", ESPNOW_CHANNEL);

    /* 3. Initialize ESP-NOW mesh communication */
    mesh_comm_config_t mesh_cfg = {
        .channel = ESPNOW_CHANNEL,
        .get_next_hop = NULL,  /* Use default stub (gateway MAC) */
    };
    ret = mesh_comm_init(&mesh_cfg);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG_MAIN, "Mesh comm init failed: %s", esp_err_to_name(ret));
        ESP_LOGE(TAG_MAIN, "Cannot continue without mesh. Restarting...");
        esp_restart();
    }

    /* Register command handler for incoming COMMAND frames */
    mesh_comm_register_recv_cb(command_handler);

    /* 4. Broadcast DISCOVERY beacon so the mesh knows we exist */
    {
        mesh_frame_t disc = {0};
        memcpy(disc.header.dst_mac, BROADCAST_MAC, 6);
        disc.header.ttl = MESH_DEFAULT_TTL;

        discovery_payload_t disc_data = {
            .node_type      = NODE_TYPE_SENSOR_A,
            .distance_level = 0xFF,  /* unknown until routing assigns it */
            .capabilities   = 0x0F,  /* temp(0) + humidity(1) + light(2) + PIR(3) */
        };
        discovery_payload_pack(&disc, &disc_data);

        esp_err_t disc_ret = mesh_comm_send(&disc);
        if (disc_ret != ESP_OK) {
            ESP_LOGW(TAG_MAIN, "Discovery beacon send failed (expected if no peers yet)");
        } else {
            ESP_LOGI(TAG_MAIN, "Discovery beacon broadcast");
        }
    }

    /* 5. Send one-shot health report (so deep-sleep nodes report before sleeping) */
    health_report_once();

    /* 6. Start sensor task (in deep-sleep mode this never returns) */
    ret = sensor_task_start();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG_MAIN, "Sensor task start failed: %s", esp_err_to_name(ret));
    }

    /* 7. Start periodic health task (only reached in always-on mode) */
    ret = health_task_start();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG_MAIN, "Health task start failed: %s", esp_err_to_name(ret));
    }

    ESP_LOGI(TAG_MAIN, "Node A booted successfully");
    ESP_LOGI(TAG_MAIN, "Free heap: %lu bytes", (unsigned long)esp_get_free_heap_size());
}
