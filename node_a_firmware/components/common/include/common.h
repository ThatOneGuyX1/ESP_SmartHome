#ifndef COMMON_H
#define COMMON_H

#include <stdint.h>
#include <string.h>

/* Node identification */
#define NODE_TYPE_SENSOR_A   0x01  /* Occupancy + Temp/Light */
#define NODE_TYPE_SENSOR_B   0x02  /* Water/Leak */
#define NODE_TYPE_SENSOR_C   0x03  /* Air Quality */
#define NODE_TYPE_GATEWAY    0x00

/* ESP-NOW configuration */
#define ESPNOW_CHANNEL       1
#define ESPNOW_MAX_PAYLOAD   227   /* 250 - 22 byte header - 1 byte CRC */
#define MESH_DEFAULT_TTL     5
#define MESH_TX_QUEUE_DEPTH  16
#define MESH_MAX_RETRIES     3
#define MESH_RETRY_DELAY_MS  100

/* Broadcast MAC address */
extern const uint8_t BROADCAST_MAC[6];

/* Gateway MAC placeholder — update with actual gateway MAC during deployment */
extern const uint8_t GATEWAY_MAC[6];

/* Log tags */
#define TAG_MAIN       "NODE_A"
#define TAG_MESH       "MESH"
#define TAG_SENSOR     "SENSOR"
#define TAG_HEALTH     "HEALTH"
#define TAG_MESSAGE    "MSG"

/* MAC address formatting */
#define MAC_FMT        "%02X:%02X:%02X:%02X:%02X:%02X"
#define MAC_ARG(mac)   (mac)[0], (mac)[1], (mac)[2], (mac)[3], (mac)[4], (mac)[5]

/**
 * Get current uptime in milliseconds.
 * Wraps esp_timer_get_time() to uint32_t ms.
 */
uint32_t common_get_uptime_ms(void);

/**
 * Format a MAC address into a string buffer.
 * Buffer must be at least 18 bytes.
 */
void common_mac_to_str(const uint8_t *mac, char *buf, size_t buf_len);

#endif /* COMMON_H */
