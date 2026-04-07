/*
 * test_listener — Minimal ESP-NOW receiver for testing Node A
 *
 * Flash this to your second ESP32. It will:
 *   1. Print its own MAC address (you need this for Node A's GATEWAY_MAC)
 *   2. Listen for any ESP-NOW frames and hex-dump them
 *   3. Parse Node A's SENSOR_DATA payloads and print human-readable values
 */

#include <string.h>
#include "esp_log.h"
#include "esp_event.h"
#include "esp_wifi.h"
#include "esp_now.h"
#include "esp_mac.h"
#include "nvs_flash.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define TAG "LISTENER"
#define ESPNOW_CHANNEL 1

/* Message types from Node A's protocol */
#define MSG_TYPE_SENSOR_DATA 0x01
#define MSG_TYPE_ALERT       0x02
#define MSG_TYPE_HEALTH      0x03
#define MSG_TYPE_DISCOVERY   0x04
#define MSG_TYPE_COMMAND     0x06

/* Command IDs */
#define CMD_SET_TEMP_THRESHOLDS  0x01

/* Header size: 6+6+1+2+1+4+1 = 21 bytes + payload_len(1) = 22 bytes, then payload, then 1 byte CRC */
#define HEADER_SIZE 22

static void parse_sensor_data(const uint8_t *payload, uint8_t len)
{
    if (len < 7) {
        ESP_LOGW(TAG, "  SENSOR_DATA payload too short (%u bytes)", len);
        return;
    }
    /* Little-endian: low byte first, high byte second */
    int16_t  temp     = (int16_t)(payload[0] | (payload[1] << 8));
    uint16_t humidity = (uint16_t)(payload[2] | (payload[3] << 8));
    uint16_t light    = (uint16_t)(payload[4] | (payload[5] << 8));
    uint8_t  occ      = payload[6];

    ESP_LOGI(TAG, "  SENSOR_DATA:");
    ESP_LOGI(TAG, "    Temperature : %.2f °C", temp / 100.0f);
    ESP_LOGI(TAG, "    Humidity    : %.2f %%RH", humidity / 100.0f);
    ESP_LOGI(TAG, "    Light       : %u lux", light);
    ESP_LOGI(TAG, "    Occupancy   : %s", occ ? "OCCUPIED" : "VACANT");
}

static void parse_health(const uint8_t *payload, uint8_t len)
{
    /* Health payload struct (little-endian, packed):
     * uint16_t battery_mv     [0-1]
     * uint8_t  battery_soc    [2]
     * int16_t  chip_temp_c    [3-4]
     * int8_t   rssi_dbm       [5]
     * uint32_t heap_free      [6-9]
     * uint32_t uptime_ms      [10-13]
     */
    if (len < 14) {
        ESP_LOGW(TAG, "  HEALTH payload too short (%u bytes)", len);
        return;
    }
    uint16_t battery_mv  = (uint16_t)(payload[0] | (payload[1] << 8));
    uint8_t  battery_pct = payload[2];
    int16_t  chip_temp   = (int16_t)(payload[3] | (payload[4] << 8));
    int8_t   rssi        = (int8_t)payload[5];
    uint32_t heap_free   = (uint32_t)(payload[6] | (payload[7] << 8) |
                                       (payload[8] << 16) | (payload[9] << 24));
    uint32_t uptime_ms   = (uint32_t)(payload[10] | (payload[11] << 8) |
                                       (payload[12] << 16) | (payload[13] << 24));

    ESP_LOGI(TAG, "  HEALTH:");
    ESP_LOGI(TAG, "    Battery     : %u mV (%u%%)", battery_mv, battery_pct);
    ESP_LOGI(TAG, "    Chip temp   : %.2f °C", chip_temp / 100.0f);
    ESP_LOGI(TAG, "    RSSI        : %d dBm", rssi);
    ESP_LOGI(TAG, "    Free heap   : %lu bytes", (unsigned long)heap_free);
    ESP_LOGI(TAG, "    Uptime      : %lu ms", (unsigned long)uptime_ms);
}

static void recv_cb(const esp_now_recv_info_t *info, const uint8_t *data, int len)
{
    ESP_LOGI(TAG, "═══════════════════════════════════════");
    ESP_LOGI(TAG, "RX %d bytes from " "%02X:%02X:%02X:%02X:%02X:%02X"
             "  RSSI: %d dBm",
             len,
             info->src_addr[0], info->src_addr[1], info->src_addr[2],
             info->src_addr[3], info->src_addr[4], info->src_addr[5],
             info->rx_ctrl->rssi);

    /* Hex dump the raw frame */
    ESP_LOG_BUFFER_HEX_LEVEL(TAG, data, len, ESP_LOG_INFO);

    /* Try to parse the header (little-endian, matches mesh_header_t) */
    if (len >= HEADER_SIZE + 1) {
        uint8_t msg_type    = data[12];
        uint16_t seq        = (uint16_t)(data[13] | (data[14] << 8));  /* little-endian */
        uint8_t ttl         = data[15];
        /* timestamp at bytes 16-19 (little-endian uint32) */
        uint32_t timestamp  = (uint32_t)(data[16] | (data[17] << 8) |
                                          (data[18] << 16) | (data[19] << 24));
        /*
         * Node A's MESH_HEADER_SIZE = 22 (21 bytes of fields + 1 padding
         * from memcpy of the packed struct). Payload starts at byte 22.
         * payload_len is still at byte 20 (last real header field).
         */
        uint8_t payload_len = data[20];
        const uint8_t *payload = &data[22];

        ESP_LOGI(TAG, "  msg_type=0x%02X  seq=%u  ttl=%u  ts=%lu ms  payload_len=%u",
                 msg_type, seq, ttl, (unsigned long)timestamp, payload_len);

        switch (msg_type) {
        case MSG_TYPE_SENSOR_DATA:
            parse_sensor_data(payload, payload_len);
            break;
        case MSG_TYPE_HEALTH:
            parse_health(payload, payload_len);
            break;
        case MSG_TYPE_ALERT:
            if (payload_len >= 3) {
                uint8_t alert_code = payload[0];
                uint16_t alert_val = (uint16_t)(payload[1] | (payload[2] << 8));
                if (alert_code == 0x10) {
                    ESP_LOGI(TAG, "  OCCUPANCY ALERT: %s",
                             alert_val ? "OCCUPIED" : "VACANT");
                } else {
                    ESP_LOGI(TAG, "  TEMP ALERT: code=%u value=%u", alert_code, alert_val);
                }
            } else {
                ESP_LOGI(TAG, "  ALERT received (short payload)");
            }
            break;
        case MSG_TYPE_DISCOVERY:
            if (payload_len >= 3) {
                ESP_LOGI(TAG, "  DISCOVERY: node_type=0x%02X level=%u caps=0x%02X",
                         payload[0], payload[1], payload[2]);
            }
            break;
        default:
            ESP_LOGI(TAG, "  (unknown type 0x%02X)", msg_type);
            break;
        }
    }
    ESP_LOGI(TAG, "═══════════════════════════════════════");
}

static void send_cb(const esp_now_send_info_t *info, esp_now_send_status_t status)
{
    (void)info;
    ESP_LOGI(TAG, "TX callback: %s", status == ESP_NOW_SEND_SUCCESS ? "OK" : "FAIL");
}

/* Send a COMMAND frame to Node A to change its temperature thresholds */
static void send_threshold_command(int16_t high_c100, int16_t low_c100)
{
    uint8_t node_a_mac[] = {0x00, 0x4B, 0x12, 0xBE, 0xCE, 0xD4};

    /*
     * Build a raw frame matching Node A's wire format:
     * [0-5]  src_mac (our MAC)
     * [6-11] dst_mac (Node A)
     * [12]   msg_type = 0x06 (COMMAND)
     * [13-14] seq (don't care)
     * [15]   ttl = 5
     * [16-19] timestamp (0)
     * [20]   payload_len = 9 (command_payload_t)
     * [21]   padding byte (MESH_HEADER_SIZE = 22)
     * [22]   command_id = 0x01 (SET_TEMP_THRESHOLDS)
     * [23-24] high threshold (int16 LE)
     * [25-26] low threshold (int16 LE)
     * [27-30] padding (data[4-7])
     * [31]   CRC-8
     */
    uint8_t frame[32] = {0};

    /* src_mac = our MAC */
    esp_read_mac(frame, ESP_MAC_WIFI_STA);
    /* dst_mac = Node A */
    memcpy(&frame[6], node_a_mac, 6);
    /* msg_type */
    frame[12] = MSG_TYPE_COMMAND;
    /* seq = 0 */
    /* ttl */
    frame[15] = 5;
    /* timestamp = 0 */
    /* payload_len = 9 (1 byte cmd_id + 8 bytes data) */
    frame[20] = 9;
    /* padding byte at [21] */
    /* command_id */
    frame[22] = CMD_SET_TEMP_THRESHOLDS;
    /* high threshold (little-endian) */
    memcpy(&frame[23], &high_c100, 2);
    /* low threshold (little-endian) */
    memcpy(&frame[25], &low_c100, 2);

    /* CRC-8 over bytes 0..30 (header + payload) */
    uint8_t crc = 0;
    for (int i = 0; i < 31; i++) {
        crc ^= frame[i];
        for (int j = 0; j < 8; j++) {
            if (crc & 0x80) crc = (crc << 1) ^ 0x07;
            else crc <<= 1;
        }
    }
    frame[31] = crc;

    ESP_LOGI(TAG, "");
    ESP_LOGI(TAG, ">>> SENDING COMMAND to Node A: SET_TEMP_THRESHOLDS");
    ESP_LOGI(TAG, ">>>   high=%.2f°C  low=%.2f°C", high_c100 / 100.0f, low_c100 / 100.0f);
    ESP_LOG_BUFFER_HEX_LEVEL(TAG, frame, 32, ESP_LOG_INFO);

    esp_err_t ret = esp_now_send(node_a_mac, frame, 32);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, ">>> Send failed: %s", esp_err_to_name(ret));
    }
}

void app_main(void)
{
    ESP_LOGI(TAG, "╔═══════════════════════════════════╗");
    ESP_LOGI(TAG, "║   ESP-NOW Test Listener           ║");
    ESP_LOGI(TAG, "║   Waiting for Node A frames...    ║");
    ESP_LOGI(TAG, "╚═══════════════════════════════════╝");

    /* NVS */
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    /* Wi-Fi STA mode */
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    wifi_init_config_t wifi_cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&wifi_cfg));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE));

    /* Print this device's MAC — YOU NEED THIS for Node A's GATEWAY_MAC */
    uint8_t mac[6];
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
    ESP_LOGI(TAG, "");
    ESP_LOGI(TAG, "╔═══════════════════════════════════════════════╗");
    ESP_LOGI(TAG, "║  THIS LISTENER'S MAC ADDRESS:                ║");
    ESP_LOGI(TAG, "║  %02X:%02X:%02X:%02X:%02X:%02X                        ║",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    ESP_LOGI(TAG, "║                                               ║");
    ESP_LOGI(TAG, "║  Put this MAC in Node A's GATEWAY_MAC in     ║");
    ESP_LOGI(TAG, "║  components/common/common.c                   ║");
    ESP_LOGI(TAG, "╚═══════════════════════════════════════════════╝");
    ESP_LOGI(TAG, "");

    /* ESP-NOW init */
    ESP_ERROR_CHECK(esp_now_init());
    ESP_ERROR_CHECK(esp_now_register_recv_cb(recv_cb));
    ESP_ERROR_CHECK(esp_now_register_send_cb(send_cb));

    /* Add Node A as peer so it can send to us */
    esp_now_peer_info_t peer = {
        .channel = ESPNOW_CHANNEL,
        .ifidx = WIFI_IF_STA,
        .encrypt = false,
    };
    /* Node A's MAC from its boot log (COM3) */
    uint8_t node_a_mac[] = {0x00, 0x4B, 0x12, 0xBE, 0xCE, 0xD4};
    memcpy(peer.peer_addr, node_a_mac, 6);
    esp_now_add_peer(&peer);

    /* Also add broadcast peer */
    uint8_t broadcast[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
    memcpy(peer.peer_addr, broadcast, 6);
    esp_now_add_peer(&peer);

    ESP_LOGI(TAG, "Listening on channel %d...", ESPNOW_CHANNEL);
    ESP_LOGI(TAG, "Will send threshold command in 30 seconds...");

    /* Wait 30 seconds, then send a command to Node A */
    vTaskDelay(pdMS_TO_TICKS(30000));

    /* Demo: change Node A's temp thresholds to 20-28°C (tighter range) */
    send_threshold_command(2800, 2000);  /* high=28.00°C, low=20.00°C */

    /* After another 60 seconds, restore defaults */
    vTaskDelay(pdMS_TO_TICKS(60000));
    send_threshold_command(3500, 500);   /* high=35.00°C, low=5.00°C */
    ESP_LOGI(TAG, "Thresholds restored to defaults");

    /* Idle forever */
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(10000));
    }
}
