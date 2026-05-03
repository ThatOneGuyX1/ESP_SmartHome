#ifndef MESH_COMM_H
#define MESH_COMM_H

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
#include "message.h"

/**
 * Function pointer type for next-hop routing lookup.
 * Given a destination MAC, returns the next-hop MAC to send to.
 * Default stub returns GATEWAY_MAC for all destinations.
 * John's routing module will provide the real implementation.
 */
typedef const uint8_t *(*mesh_get_next_hop_fn)(const uint8_t *dst_mac);

/**
 * Configuration for mesh communication init.
 */
typedef struct {
    uint8_t             channel;        /* Wi-Fi channel (default 1) */
    mesh_get_next_hop_fn get_next_hop;  /* Routing function (NULL = use gateway MAC) */
} mesh_comm_config_t;

/**
 * Callback type for received frames.
 * Called from the ESP-NOW receive task context.
 */
typedef void (*mesh_recv_cb_t)(const mesh_frame_t *frame);

/**
 * Initialize ESP-NOW mesh communication.
 * Sets up Wi-Fi in STA mode, initializes ESP-NOW, registers callbacks,
 * and creates the TX queue.
 */
esp_err_t mesh_comm_init(const mesh_comm_config_t *config);

/**
 * Send a mesh frame.
 * Looks up next-hop via the routing function, serializes the frame,
 * and transmits via ESP-NOW with retry logic.
 * The frame's src_mac is automatically filled with this node's MAC.
 * Sequence number is auto-incremented.
 * Returns ESP_OK on successful transmission.
 */
esp_err_t mesh_comm_send(mesh_frame_t *frame);

/**
 * Add a peer to the ESP-NOW peer list.
 * Must be called before sending unicast frames to a specific MAC.
 */
esp_err_t mesh_comm_add_peer(const uint8_t *mac);

/**
 * Register a callback for received frames.
 * Only one callback can be registered at a time.
 */
void mesh_comm_register_recv_cb(mesh_recv_cb_t cb);

/**
 * Get this node's MAC address.
 */
void mesh_comm_get_own_mac(uint8_t *mac);

/**
 * Get the RSSI of the last received frame (dBm).
 * Returns 0 if no frame has been received yet.
 */
int8_t mesh_comm_get_last_rssi(void);

#endif /* MESH_COMM_H */
