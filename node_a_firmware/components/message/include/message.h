#ifndef MESSAGE_H
#define MESSAGE_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

/*
 * ESP-NOW Mesh Frame Format (per ECE568 System Architecture §8.1)
 *
 * Byte Offset   Field           Size     Description
 * 0x00          src_mac         6 bytes  Originating node MAC
 * 0x06          dst_mac         6 bytes  Destination MAC (or FF:FF:FF:FF:FF:FF)
 * 0x0C          msg_type        1 byte   Message type ID
 * 0x0D          sequence_num    2 bytes  Per-node monotonic counter
 * 0x0F          ttl             1 byte   Hop limit (default 5)
 * 0x10          timestamp       4 bytes  Node uptime in milliseconds
 * 0x14          payload_len     1 byte   Length of payload section
 * 0x15          payload         N bytes  Type-specific data
 * 0x15+N        crc8            1 byte   CRC-8 over header + payload
 *
 * Header: 22 bytes. Max payload: 227 bytes. Total max: 250 bytes.
 */

#define MESH_HEADER_SIZE    22
#define MESH_MAX_FRAME_SIZE 250
#define MESH_MAX_PAYLOAD    (MESH_MAX_FRAME_SIZE - MESH_HEADER_SIZE - 1) /* 227 */

/* Message type IDs (§5.3) */
typedef enum {
    MSG_TYPE_SENSOR_DATA = 0x01,
    MSG_TYPE_ALERT       = 0x02,
    MSG_TYPE_HEALTH      = 0x03,
    MSG_TYPE_DISCOVERY   = 0x04,
    MSG_TYPE_HEARTBEAT   = 0x05,
    MSG_TYPE_COMMAND     = 0x06,
    MSG_TYPE_ACK         = 0x07,
} msg_type_t;

/* Frame header — matches wire format (little-endian) */
typedef struct __attribute__((packed)) {
    uint8_t  src_mac[6];
    uint8_t  dst_mac[6];
    uint8_t  msg_type;
    uint16_t sequence_num;
    uint8_t  ttl;
    uint32_t timestamp;
    uint8_t  payload_len;
} mesh_header_t;

/* Complete frame with payload */
typedef struct {
    mesh_header_t header;
    uint8_t       payload[MESH_MAX_PAYLOAD];
    uint8_t       crc8;
} mesh_frame_t;

/* Node A sensor data payload (§8.2 — 7 bytes) */
typedef struct __attribute__((packed)) {
    int16_t  temperature;      /* °C × 100 (e.g., 2350 = 23.50°C) */
    uint16_t humidity;         /* %RH × 100 */
    uint16_t light_level;      /* lux */
    uint8_t  occupancy_state;  /* 0 = vacant, 1 = occupied */
} sensor_data_payload_t;

/* Health data payload */
typedef struct __attribute__((packed)) {
    uint16_t battery_mv;    /* millivolts (0 if USB powered) */
    uint8_t  battery_soc;   /* state-of-charge 0–100% (from MAX17048) */
    int16_t  chip_temp_c;   /* °C × 100 */
    int8_t   rssi_dbm;      /* dBm */
    uint32_t heap_free;     /* bytes */
    uint32_t uptime_ms;     /* milliseconds */
} health_payload_t;

/* Alert payload */
typedef struct __attribute__((packed)) {
    uint8_t  alert_code;      /* 1 = triggered, 2 = cleared, 0x10 = occupancy */
    uint16_t sensor_reading;  /* raw value that triggered alert */
} alert_payload_t;

/* Command payload (gateway → node) */
#define CMD_SET_TEMP_THRESHOLDS   0x01  /* data: int16 high, int16 low */
#define CMD_SET_SAMPLE_INTERVAL   0x02  /* data: uint32 interval_ms */
#define CMD_REQUEST_READING       0x03  /* data: none — trigger immediate send */

typedef struct __attribute__((packed)) {
    uint8_t  command_id;      /* CMD_SET_TEMP_THRESHOLDS, etc. */
    uint8_t  data[8];         /* command-specific data */
} command_payload_t;

/* Discovery payload (broadcast on boot) */
typedef struct __attribute__((packed)) {
    uint8_t  node_type;       /* NODE_TYPE_SENSOR_A, etc. */
    uint8_t  distance_level;  /* 0xFF = unknown */
    uint8_t  capabilities;    /* bitmask: bit0=temp, bit1=humidity, bit2=light, bit3=PIR */
} discovery_payload_t;

/**
 * Serialize a mesh frame to a byte buffer for transmission.
 * Returns total bytes written, or 0 on error.
 */
size_t message_serialize(const mesh_frame_t *frame, uint8_t *buf, size_t buf_size);

/**
 * Deserialize a byte buffer into a mesh frame.
 * Returns true on success (including CRC validation), false on error.
 */
bool message_deserialize(const uint8_t *buf, size_t len, mesh_frame_t *frame);

/**
 * Compute CRC-8 over a byte buffer.
 * Uses polynomial 0x07 (CRC-8-CCITT).
 */
uint8_t crc8_compute(const uint8_t *data, size_t len);

/**
 * Validate a raw frame buffer (CRC, TTL, payload_len bounds).
 * Returns true if valid.
 */
bool message_validate(const uint8_t *buf, size_t len);

/**
 * Pack a sensor_data_payload_t into the frame's payload field.
 * Sets payload_len appropriately.
 */
void sensor_payload_pack(mesh_frame_t *frame, const sensor_data_payload_t *data);

/**
 * Pack a health_payload_t into the frame's payload field.
 */
void health_payload_pack(mesh_frame_t *frame, const health_payload_t *data);

/**
 * Pack an alert_payload_t into the frame's payload field.
 */
void alert_payload_pack(mesh_frame_t *frame, const alert_payload_t *data);

/**
 * Pack a discovery_payload_t into the frame's payload field.
 */
void discovery_payload_pack(mesh_frame_t *frame, const discovery_payload_t *data);

/**
 * Pack a command_payload_t into the frame's payload field.
 */
void command_payload_pack(mesh_frame_t *frame, const command_payload_t *data);

#endif /* MESSAGE_H */
