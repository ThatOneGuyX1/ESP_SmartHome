#ifndef MAX17048_H
#define MAX17048_H

#include <stdint.h>
#include "esp_err.h"

/**
 * MAX17048 LiPoly/LiIon fuel gauge driver (I2C @ 0x36).
 *
 * Shares I2C_NUM_0 bus with DHT20 and BH1750 — does NOT install the
 * I2C driver itself. The bus must already be initialized (by sensor_hal_real.c)
 * before calling these functions.
 */

/**
 * Initialize the MAX17048. Reads the VERSION register to verify the chip
 * is present on the bus. Returns ESP_OK on success.
 *
 * If the I2C bus is not initialized (e.g. mock sensor mode), returns
 * ESP_ERR_INVALID_STATE and logs a warning — this is non-fatal.
 */
esp_err_t max17048_init(void);

/**
 * Read battery voltage in millivolts.
 * Returns 0 if the chip is not initialized or the read fails.
 */
uint16_t max17048_read_voltage_mv(void);

/**
 * Read battery state-of-charge as an integer percentage (0–100).
 * Returns 0 if the chip is not initialized or the read fails.
 */
uint8_t max17048_read_soc(void);

#endif /* MAX17048_H */
