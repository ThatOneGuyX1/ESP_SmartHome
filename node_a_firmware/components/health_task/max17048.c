#include "max17048.h"
#include "common.h"

#include "esp_log.h"
#include "driver/i2c.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

/* ── MAX17048 I2C constants ────────────────────────────────────────── */
#define MAX17048_ADDR        0x36
#define MAX17048_REG_VCELL   0x02    /* Battery voltage (78.125 µV/cell) */
#define MAX17048_REG_SOC     0x04    /* State of charge (%) */
#define MAX17048_REG_VERSION 0x08    /* Chip version */

#define I2C_MASTER_NUM       I2C_NUM_0
#define I2C_TIMEOUT_MS       1000

/* ── State ─────────────────────────────────────────────────────────── */
static bool s_initialized = false;

/* ── Helper: read a 16-bit big-endian register ─────────────────────── */
static esp_err_t max17048_read_reg(uint8_t reg, uint16_t *value)
{
    uint8_t data[2] = {0};

    i2c_cmd_handle_t cmd = i2c_cmd_link_create();
    i2c_master_start(cmd);
    i2c_master_write_byte(cmd, (MAX17048_ADDR << 1) | I2C_MASTER_WRITE, true);
    i2c_master_write_byte(cmd, reg, true);
    i2c_master_start(cmd);  /* repeated start */
    i2c_master_write_byte(cmd, (MAX17048_ADDR << 1) | I2C_MASTER_READ, true);
    i2c_master_read_byte(cmd, &data[0], I2C_MASTER_ACK);
    i2c_master_read_byte(cmd, &data[1], I2C_MASTER_NACK);
    i2c_master_stop(cmd);

    esp_err_t ret = i2c_master_cmd_begin(I2C_MASTER_NUM, cmd,
                                          pdMS_TO_TICKS(I2C_TIMEOUT_MS));
    i2c_cmd_link_delete(cmd);

    if (ret == ESP_OK) {
        *value = ((uint16_t)data[0] << 8) | data[1];
    }
    return ret;
}

/* ═══════════════════════════════════════════════════════════════════ */
/* Public API                                                          */
/* ═══════════════════════════════════════════════════════════════════ */

esp_err_t max17048_init(void)
{
    s_initialized = false;

    /* Try to read VERSION register to verify the chip is on the bus */
    uint16_t version = 0;
    esp_err_t ret = max17048_read_reg(MAX17048_REG_VERSION, &version);

    if (ret == ESP_ERR_INVALID_STATE) {
        /* I2C driver not installed — likely mock sensor mode */
        ESP_LOGW(TAG_HEALTH, "MAX17048: I2C bus not initialized (mock mode?). "
                 "Battery readings will be 0.");
        return ret;
    }

    if (ret != ESP_OK) {
        ESP_LOGW(TAG_HEALTH, "MAX17048: not detected at 0x%02X (err=%s). "
                 "Battery readings will be 0.",
                 MAX17048_ADDR, esp_err_to_name(ret));
        return ret;
    }

    if (version == 0) {
        ESP_LOGW(TAG_HEALTH, "MAX17048: VERSION register returned 0 — chip may not be present");
        return ESP_ERR_NOT_FOUND;
    }

    s_initialized = true;
    ESP_LOGI(TAG_HEALTH, "MAX17048 fuel gauge detected (version=0x%04X)", version);
    return ESP_OK;
}

uint16_t max17048_read_voltage_mv(void)
{
    if (!s_initialized) return 0;

    uint16_t raw = 0;
    esp_err_t ret = max17048_read_reg(MAX17048_REG_VCELL, &raw);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG_HEALTH, "MAX17048: VCELL read failed: %s", esp_err_to_name(ret));
        return 0;
    }

    /*
     * VCELL register: 16-bit unsigned, units of 78.125 µV.
     * To convert to millivolts: raw * 78.125 / 1000 = raw * 5 / 64
     * Using integer math to avoid float.
     */
    uint32_t mv = ((uint32_t)raw * 5UL) / 64UL;
    return (uint16_t)mv;
}

uint8_t max17048_read_soc(void)
{
    if (!s_initialized) return 0;

    uint16_t raw = 0;
    esp_err_t ret = max17048_read_reg(MAX17048_REG_SOC, &raw);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG_HEALTH, "MAX17048: SOC read failed: %s", esp_err_to_name(ret));
        return 0;
    }

    /*
     * SOC register: high byte = integer %, low byte = 1/256 %.
     * We just return the integer part.
     */
    uint8_t soc = (uint8_t)(raw >> 8);
    if (soc > 100) soc = 100;  /* clamp */
    return soc;
}
