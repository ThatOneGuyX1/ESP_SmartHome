#include "mesh_comm.h"
#include "common.h"
#include "message.h"

#include <string.h>
#include "esp_log.h"
#include "esp_wifi.h"
#include "esp_now.h"
#include "esp_mac.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"

static mesh_get_next_hop_fn s_get_next_hop = NULL;
static mesh_recv_cb_t       s_recv_cb = NULL;
static uint16_t             s_sequence_num = 0;
static uint8_t              s_own_mac[6] = {0};
static SemaphoreHandle_t    s_send_sem = NULL;
static SemaphoreHandle_t    s_send_mutex = NULL;
static bool                 s_send_success = false;
static int8_t               s_last_rssi = 0;

/* Default next-hop stub: always route to gateway */
static const uint8_t *default_get_next_hop(const uint8_t *dst_mac)
{
    (void)dst_mac;
    return GATEWAY_MAC;
}

/* ESP-NOW send callback */
static void espnow_send_cb(const esp_now_send_info_t *tx_info, esp_now_send_status_t status)
{
    s_send_success = (status == ESP_NOW_SEND_SUCCESS);
    if (s_send_sem) {
        xSemaphoreGive(s_send_sem);
    }
}

/* ESP-NOW receive callback */
static void espnow_recv_cb(const esp_now_recv_info_t *recv_info,
                            const uint8_t *data, int data_len)
{
    /* Store RSSI from this reception */
    if (recv_info->rx_ctrl) {
        s_last_rssi = (int8_t)recv_info->rx_ctrl->rssi;
    }

    if (data_len < MESH_HEADER_SIZE + 1) {
        ESP_LOGW(TAG_MESH, "Received undersized frame (%d bytes)", data_len);
        return;
    }

    if (!message_validate(data, (size_t)data_len)) {
        ESP_LOGW(TAG_MESH, "Received invalid frame (bad CRC or TTL)");
        return;
    }

    mesh_frame_t frame;
    if (!message_deserialize(data, (size_t)data_len, &frame)) {
        ESP_LOGW(TAG_MESH, "Failed to deserialize received frame");
        return;
    }

    char src_str[18];
    common_mac_to_str(frame.header.src_mac, src_str, sizeof(src_str));
    ESP_LOGI(TAG_MESH, "RX from %s type=0x%02X seq=%u ttl=%u len=%u",
             src_str, frame.header.msg_type, frame.header.sequence_num,
             frame.header.ttl, frame.header.payload_len);

    /* Handle specific message types */
    switch (frame.header.msg_type) {
    case MSG_TYPE_ACK:
        ESP_LOGI(TAG_MESH, "ACK received from %s", src_str);
        break;
    case MSG_TYPE_COMMAND:
        ESP_LOGI(TAG_MESH, "COMMAND received from %s, payload_len=%u",
                 src_str, frame.header.payload_len);
        ESP_LOG_BUFFER_HEX_LEVEL(TAG_MESH, frame.payload,
                                  frame.header.payload_len, ESP_LOG_INFO);
        break;
    case MSG_TYPE_HEARTBEAT:
        ESP_LOGD(TAG_MESH, "HEARTBEAT from %s", src_str);
        break;
    default:
        ESP_LOGD(TAG_MESH, "Unhandled msg_type=0x%02X from %s",
                 frame.header.msg_type, src_str);
        break;
    }

    /* Forward to application callback if registered */
    if (s_recv_cb) {
        s_recv_cb(&frame);
    }
}

esp_err_t mesh_comm_init(const mesh_comm_config_t *config)
{
    esp_err_t ret;

    /* Store routing function */
    s_get_next_hop = (config && config->get_next_hop)
                     ? config->get_next_hop
                     : default_get_next_hop;

    /* Get own MAC address */
    ret = esp_read_mac(s_own_mac, ESP_MAC_WIFI_STA);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG_MESH, "Failed to read MAC: %s", esp_err_to_name(ret));
        return ret;
    }
    char mac_str[18];
    common_mac_to_str(s_own_mac, mac_str, sizeof(mac_str));
    ESP_LOGI(TAG_MESH, "Node MAC: %s", mac_str);

    /* Create send semaphore for blocking on send callback */
    s_send_sem = xSemaphoreCreateBinary();
    if (!s_send_sem) {
        ESP_LOGE(TAG_MESH, "Failed to create send semaphore");
        return ESP_ERR_NO_MEM;
    }

    /* Create mutex to serialize concurrent send calls */
    s_send_mutex = xSemaphoreCreateMutex();
    if (!s_send_mutex) {
        ESP_LOGE(TAG_MESH, "Failed to create send mutex");
        return ESP_ERR_NO_MEM;
    }

    /* Initialize ESP-NOW */
    ret = esp_now_init();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG_MESH, "ESP-NOW init failed: %s", esp_err_to_name(ret));
        return ret;
    }

    /* Register callbacks */
    ret = esp_now_register_send_cb(espnow_send_cb);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG_MESH, "Failed to register send cb: %s", esp_err_to_name(ret));
        return ret;
    }

    ret = esp_now_register_recv_cb(espnow_recv_cb);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG_MESH, "Failed to register recv cb: %s", esp_err_to_name(ret));
        return ret;
    }

    /* Add broadcast peer */
    ret = mesh_comm_add_peer(BROADCAST_MAC);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG_MESH, "Failed to add broadcast peer: %s", esp_err_to_name(ret));
        return ret;
    }

    /* Add gateway peer */
    ret = mesh_comm_add_peer(GATEWAY_MAC);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG_MESH, "Failed to add gateway peer: %s", esp_err_to_name(ret));
        /* Non-fatal: gateway MAC may not be set yet */
    }

    ESP_LOGI(TAG_MESH, "ESP-NOW mesh initialized on channel %d",
             config ? config->channel : ESPNOW_CHANNEL);

    return ESP_OK;
}

esp_err_t mesh_comm_send(mesh_frame_t *frame)
{
    /* Serialize access so concurrent tasks don't interleave send/callback pairs */
    if (xSemaphoreTake(s_send_mutex, pdMS_TO_TICKS(5000)) != pdTRUE) {
        ESP_LOGE(TAG_MESH, "Failed to acquire send mutex");
        return ESP_ERR_TIMEOUT;
    }

    /* Fill in src_mac and sequence number */
    memcpy(frame->header.src_mac, s_own_mac, 6);
    frame->header.sequence_num = s_sequence_num++;
    frame->header.timestamp = common_get_uptime_ms();

    if (frame->header.ttl == 0) {
        frame->header.ttl = MESH_DEFAULT_TTL;
    }

    /* Determine next hop */
    const uint8_t *next_hop = s_get_next_hop(frame->header.dst_mac);

    /* Serialize frame to buffer */
    uint8_t buf[MESH_MAX_FRAME_SIZE];
    size_t len = message_serialize(frame, buf, sizeof(buf));
    if (len == 0) {
        ESP_LOGE(TAG_MESH, "Failed to serialize frame");
        xSemaphoreGive(s_send_mutex);
        return ESP_ERR_INVALID_ARG;
    }

    char dst_str[18];
    common_mac_to_str(next_hop, dst_str, sizeof(dst_str));

    esp_err_t result = ESP_FAIL;

    /* Send with retry */
    for (int attempt = 0; attempt < MESH_MAX_RETRIES; attempt++) {
        esp_err_t ret = esp_now_send(next_hop, buf, len);
        if (ret != ESP_OK) {
            ESP_LOGW(TAG_MESH, "TX attempt %d failed (send): %s",
                     attempt + 1, esp_err_to_name(ret));
            vTaskDelay(pdMS_TO_TICKS(MESH_RETRY_DELAY_MS));
            continue;
        }

        /* Wait for send callback */
        if (xSemaphoreTake(s_send_sem, pdMS_TO_TICKS(1000)) == pdTRUE) {
            if (s_send_success) {
                ESP_LOGD(TAG_MESH, "TX OK to %s type=0x%02X seq=%u (%zu bytes)",
                         dst_str, frame->header.msg_type,
                         frame->header.sequence_num, len);
                result = ESP_OK;
                break;
            }
            ESP_LOGW(TAG_MESH, "TX attempt %d: send callback reported failure",
                     attempt + 1);
        } else {
            ESP_LOGW(TAG_MESH, "TX attempt %d: send callback timeout", attempt + 1);
        }

        if (attempt < MESH_MAX_RETRIES - 1) {
            vTaskDelay(pdMS_TO_TICKS(MESH_RETRY_DELAY_MS));
        }
    }

    if (result != ESP_OK) {
        ESP_LOGE(TAG_MESH, "TX FAILED to %s type=0x%02X after %d attempts",
                 dst_str, frame->header.msg_type, MESH_MAX_RETRIES);
    }

    xSemaphoreGive(s_send_mutex);
    return result;
}

esp_err_t mesh_comm_add_peer(const uint8_t *mac)
{
    if (esp_now_is_peer_exist(mac)) {
        return ESP_OK;
    }

    esp_now_peer_info_t peer = {
        .channel = ESPNOW_CHANNEL,
        .ifidx = WIFI_IF_STA,
        .encrypt = false,
    };
    memcpy(peer.peer_addr, mac, 6);

    esp_err_t ret = esp_now_add_peer(&peer);
    if (ret != ESP_OK) {
        char mac_str[18];
        common_mac_to_str(mac, mac_str, sizeof(mac_str));
        ESP_LOGE(TAG_MESH, "Failed to add peer %s: %s", mac_str, esp_err_to_name(ret));
    }
    return ret;
}

void mesh_comm_register_recv_cb(mesh_recv_cb_t cb)
{
    s_recv_cb = cb;
}

void mesh_comm_get_own_mac(uint8_t *mac)
{
    memcpy(mac, s_own_mac, 6);
}

int8_t mesh_comm_get_last_rssi(void)
{
    return s_last_rssi;
}
