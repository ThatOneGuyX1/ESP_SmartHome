#include "common.h"
#include <stdio.h>
#include "esp_timer.h"

const uint8_t BROADCAST_MAC[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
const uint8_t GATEWAY_MAC[6]   = {0xC0, 0xCD, 0xD6, 0x35, 0xC9, 0x98};

uint32_t common_get_uptime_ms(void)
{
    return (uint32_t)(esp_timer_get_time() / 1000);
}

void common_mac_to_str(const uint8_t *mac, char *buf, size_t buf_len)
{
    snprintf(buf, buf_len, MAC_FMT, MAC_ARG(mac));
}
