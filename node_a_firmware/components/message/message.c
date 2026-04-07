#include "message.h"
#include <stddef.h>
#include <string.h>

/* CRC-8 with polynomial 0x07 (CRC-8-CCITT) */
uint8_t crc8_compute(const uint8_t *data, size_t len)
{
    uint8_t crc = 0x00;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int j = 0; j < 8; j++) {
            if (crc & 0x80) {
                crc = (crc << 1) ^ 0x07;
            } else {
                crc <<= 1;
            }
        }
    }
    return crc;
}

size_t message_serialize(const mesh_frame_t *frame, uint8_t *buf, size_t buf_size)
{
    size_t total = MESH_HEADER_SIZE + frame->header.payload_len + 1; /* +1 for CRC */
    if (buf_size < total || frame->header.payload_len > MESH_MAX_PAYLOAD) {
        return 0;
    }

    /* Copy header (packed struct matches wire format) */
    memcpy(buf, &frame->header, MESH_HEADER_SIZE);

    /* Copy payload */
    if (frame->header.payload_len > 0) {
        memcpy(buf + MESH_HEADER_SIZE, frame->payload, frame->header.payload_len);
    }

    /* Compute and append CRC over header + payload */
    size_t crc_offset = MESH_HEADER_SIZE + frame->header.payload_len;
    buf[crc_offset] = crc8_compute(buf, crc_offset);

    return total;
}

bool message_deserialize(const uint8_t *buf, size_t len, mesh_frame_t *frame)
{
    if (len < MESH_HEADER_SIZE + 1) {
        return false;
    }

    /* Extract header */
    memcpy(&frame->header, buf, MESH_HEADER_SIZE);

    /* Validate payload length */
    if (frame->header.payload_len > MESH_MAX_PAYLOAD) {
        return false;
    }

    size_t expected_len = MESH_HEADER_SIZE + frame->header.payload_len + 1;
    if (len < expected_len) {
        return false;
    }

    /* Copy payload */
    if (frame->header.payload_len > 0) {
        memcpy(frame->payload, buf + MESH_HEADER_SIZE, frame->header.payload_len);
    }

    /* Validate CRC */
    size_t crc_offset = MESH_HEADER_SIZE + frame->header.payload_len;
    uint8_t expected_crc = crc8_compute(buf, crc_offset);
    frame->crc8 = buf[crc_offset];

    return frame->crc8 == expected_crc;
}

bool message_validate(const uint8_t *buf, size_t len)
{
    if (len < MESH_HEADER_SIZE + 1) {
        return false;
    }

    /* Read payload_len from header */
    uint8_t payload_len = buf[offsetof(mesh_header_t, payload_len)];
    if (payload_len > MESH_MAX_PAYLOAD) {
        return false;
    }

    size_t expected_len = MESH_HEADER_SIZE + payload_len + 1;
    if (len < expected_len) {
        return false;
    }

    /* Check TTL > 0 */
    uint8_t ttl = buf[offsetof(mesh_header_t, ttl)];
    if (ttl == 0) {
        return false;
    }

    /* Validate CRC */
    size_t crc_offset = MESH_HEADER_SIZE + payload_len;
    uint8_t computed = crc8_compute(buf, crc_offset);
    return buf[crc_offset] == computed;
}

void sensor_payload_pack(mesh_frame_t *frame, const sensor_data_payload_t *data)
{
    frame->header.msg_type = MSG_TYPE_SENSOR_DATA;
    frame->header.payload_len = sizeof(sensor_data_payload_t);
    memcpy(frame->payload, data, sizeof(sensor_data_payload_t));
}

void health_payload_pack(mesh_frame_t *frame, const health_payload_t *data)
{
    frame->header.msg_type = MSG_TYPE_HEALTH;
    frame->header.payload_len = sizeof(health_payload_t);
    memcpy(frame->payload, data, sizeof(health_payload_t));
}

void alert_payload_pack(mesh_frame_t *frame, const alert_payload_t *data)
{
    frame->header.msg_type = MSG_TYPE_ALERT;
    frame->header.payload_len = sizeof(alert_payload_t);
    memcpy(frame->payload, data, sizeof(alert_payload_t));
}

void discovery_payload_pack(mesh_frame_t *frame, const discovery_payload_t *data)
{
    frame->header.msg_type = MSG_TYPE_DISCOVERY;
    frame->header.payload_len = sizeof(discovery_payload_t);
    memcpy(frame->payload, data, sizeof(discovery_payload_t));
}

void command_payload_pack(mesh_frame_t *frame, const command_payload_t *data)
{
    frame->header.msg_type = MSG_TYPE_COMMAND;
    frame->header.payload_len = sizeof(command_payload_t);
    memcpy(frame->payload, data, sizeof(command_payload_t));
}
