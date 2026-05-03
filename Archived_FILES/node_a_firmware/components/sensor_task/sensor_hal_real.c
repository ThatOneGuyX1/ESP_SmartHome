#include "sensor_hal.h"
#include "common.h"

#include "esp_log.h"
#include "driver/i2c.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

/* ── I2C Configuration ─────────────────────────────────────────────── */
#define I2C_MASTER_NUM       I2C_NUM_0
#define I2C_MASTER_SDA_IO    GPIO_NUM_22
#define I2C_MASTER_SCL_IO    GPIO_NUM_20
#define I2C_MASTER_FREQ_HZ   100000      /* 100 kHz standard mode */
#define I2C_TIMEOUT_MS       1000

/* ── DHT20 (AHT20) ────────────────────────────────────────────────── */
#define DHT20_ADDR           0x38
#define DHT20_CMD_STATUS     0x71
#define DHT20_CMD_TRIGGER    {0xAC, 0x33, 0x00}
#define DHT20_MEAS_DELAY_MS  80          /* datasheet: ~75 ms typical */

/* ── BH1750 ────────────────────────────────────────────────────────── */
#define BH1750_ADDR          0x23        /* ADDR pin LOW */
#define BH1750_CMD_POWER_ON  0x01
#define BH1750_CMD_RESET     0x07
#define BH1750_CMD_HRES_1X   0x20        /* one-time high-res, 1 lx resolution */
#define BH1750_MEAS_DELAY_MS 180         /* datasheet: max 180 ms */

/* ── PIR Sensor ────────────────────────────────────────────────────── */
#ifndef CONFIG_PIR_GPIO_PIN
#define CONFIG_PIR_GPIO_PIN  GPIO_NUM_25
#endif
#define PIR_GPIO             ((gpio_num_t)CONFIG_PIR_GPIO_PIN)

/* ── State ─────────────────────────────────────────────────────────── */
static volatile uint8_t s_occupancy = 0;

/* ── Helper: I2C write ─────────────────────────────────────────────── */
static esp_err_t i2c_write_bytes(uint8_t addr, const uint8_t *data, size_t len)
{
    i2c_cmd_handle_t cmd = i2c_cmd_link_create();
    i2c_master_start(cmd);
    i2c_master_write_byte(cmd, (addr << 1) | I2C_MASTER_WRITE, true);
    i2c_master_write(cmd, data, len, true);
    i2c_master_stop(cmd);
    esp_err_t ret = i2c_master_cmd_begin(I2C_MASTER_NUM, cmd,
                                          pdMS_TO_TICKS(I2C_TIMEOUT_MS));
    i2c_cmd_link_delete(cmd);
    return ret;
}

/* ── Helper: I2C read ──────────────────────────────────────────────── */
static esp_err_t i2c_read_bytes(uint8_t addr, uint8_t *buf, size_t len)
{
    i2c_cmd_handle_t cmd = i2c_cmd_link_create();
    i2c_master_start(cmd);
    i2c_master_write_byte(cmd, (addr << 1) | I2C_MASTER_READ, true);
    if (len > 1) {
        i2c_master_read(cmd, buf, len - 1, I2C_MASTER_ACK);
    }
    i2c_master_read_byte(cmd, buf + len - 1, I2C_MASTER_NACK);
    i2c_master_stop(cmd);
    esp_err_t ret = i2c_master_cmd_begin(I2C_MASTER_NUM, cmd,
                                          pdMS_TO_TICKS(I2C_TIMEOUT_MS));
    i2c_cmd_link_delete(cmd);
    return ret;
}

/* ── PIR ISR ───────────────────────────────────────────────────────── */
static void IRAM_ATTR pir_isr_handler(void *arg)
{
    (void)arg;
    s_occupancy = gpio_get_level(PIR_GPIO);
}

/* ── I2C bus init ──────────────────────────────────────────────────── */
static esp_err_t i2c_master_init(void)
{
    i2c_config_t conf = {
        .mode             = I2C_MODE_MASTER,
        .sda_io_num       = I2C_MASTER_SDA_IO,
        .scl_io_num       = I2C_MASTER_SCL_IO,
        .sda_pullup_en    = GPIO_PULLUP_ENABLE,
        .scl_pullup_en    = GPIO_PULLUP_ENABLE,
        .master.clk_speed = I2C_MASTER_FREQ_HZ,
    };
    esp_err_t ret = i2c_param_config(I2C_MASTER_NUM, &conf);
    if (ret != ESP_OK) return ret;

    return i2c_driver_install(I2C_MASTER_NUM, conf.mode, 0, 0, 0);
}

/* ── DHT20 helpers ─────────────────────────────────────────────────── */
static esp_err_t dht20_check_status(void)
{
    uint8_t status = 0;
    esp_err_t ret = i2c_read_bytes(DHT20_ADDR, &status, 1);
    if (ret != ESP_OK) return ret;

    /* Bit 3 must be 1 (calibrated). If not, re-init the sensor. */
    if ((status & 0x08) == 0) {
        ESP_LOGW(TAG_SENSOR, "DHT20: not calibrated (status=0x%02X), sending init", status);
        /* Send initialization sequence per datasheet */
        uint8_t init1[] = {0x1B, 0x00, 0x00};
        i2c_write_bytes(DHT20_ADDR, init1, sizeof(init1));
        vTaskDelay(pdMS_TO_TICKS(10));
        uint8_t init2[] = {0x1C, 0x00, 0x00};
        i2c_write_bytes(DHT20_ADDR, init2, sizeof(init2));
        vTaskDelay(pdMS_TO_TICKS(10));
        uint8_t init3[] = {0x1E, 0x00, 0x00};
        i2c_write_bytes(DHT20_ADDR, init3, sizeof(init3));
        vTaskDelay(pdMS_TO_TICKS(10));
    }
    return ESP_OK;
}

static esp_err_t dht20_read(int16_t *temp_c100, uint16_t *hum_c100)
{
    /* Trigger measurement */
    uint8_t trigger[] = {0xAC, 0x33, 0x00};
    esp_err_t ret = i2c_write_bytes(DHT20_ADDR, trigger, sizeof(trigger));
    if (ret != ESP_OK) {
        ESP_LOGE(TAG_SENSOR, "DHT20: trigger failed: %s", esp_err_to_name(ret));
        return ret;
    }

    vTaskDelay(pdMS_TO_TICKS(DHT20_MEAS_DELAY_MS));

    /* Read 7 bytes: status + 5 data + CRC */
    uint8_t data[7] = {0};
    ret = i2c_read_bytes(DHT20_ADDR, data, sizeof(data));
    if (ret != ESP_OK) {
        ESP_LOGE(TAG_SENSOR, "DHT20: read failed: %s", esp_err_to_name(ret));
        return ret;
    }

    /* Check busy bit (bit 7 of status byte) */
    if (data[0] & 0x80) {
        ESP_LOGW(TAG_SENSOR, "DHT20: still busy, retrying...");
        vTaskDelay(pdMS_TO_TICKS(40));
        ret = i2c_read_bytes(DHT20_ADDR, data, sizeof(data));
        if (ret != ESP_OK) return ret;
        if (data[0] & 0x80) {
            ESP_LOGE(TAG_SENSOR, "DHT20: still busy after retry");
            return ESP_ERR_TIMEOUT;
        }
    }

    /*
     * Data layout (per AHT20 datasheet):
     *   data[1]       = humidity[19:12]
     *   data[2]       = humidity[11:4]
     *   data[3] upper = humidity[3:0]
     *   data[3] lower = temperature[19:16]
     *   data[4]       = temperature[15:8]
     *   data[5]       = temperature[7:0]
     */
    uint32_t raw_hum  = ((uint32_t)data[1] << 12)
                       | ((uint32_t)data[2] << 4)
                       | ((uint32_t)(data[3] >> 4));

    uint32_t raw_temp = (((uint32_t)(data[3] & 0x0F)) << 16)
                       | ((uint32_t)data[4] << 8)
                       | (uint32_t)data[5];

    /* Convert: humidity = raw / 2^20 * 100 (in %RH × 100) */
    *hum_c100 = (uint16_t)((raw_hum * 10000UL) / (1UL << 20));

    /* Convert: temp = raw / 2^20 * 200 - 50 (in °C × 100) */
    int32_t temp_calc = (int32_t)((raw_temp * 20000LL) / (1LL << 20)) - 5000;
    *temp_c100 = (int16_t)temp_calc;

    ESP_LOGD(TAG_SENSOR, "DHT20 raw: hum=0x%05lX temp=0x%05lX → hum=%u temp=%d",
             (unsigned long)raw_hum, (unsigned long)raw_temp,
             *hum_c100, *temp_c100);

    return ESP_OK;
}

/* ── BH1750 helpers ────────────────────────────────────────────────── */
static esp_err_t bh1750_read_lux(uint16_t *lux)
{
    /* Power on */
    uint8_t cmd = BH1750_CMD_POWER_ON;
    esp_err_t ret = i2c_write_bytes(BH1750_ADDR, &cmd, 1);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG_SENSOR, "BH1750: power-on failed: %s", esp_err_to_name(ret));
        return ret;
    }

    /* Start one-time high-resolution measurement */
    cmd = BH1750_CMD_HRES_1X;
    ret = i2c_write_bytes(BH1750_ADDR, &cmd, 1);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG_SENSOR, "BH1750: start measurement failed: %s", esp_err_to_name(ret));
        return ret;
    }

    vTaskDelay(pdMS_TO_TICKS(BH1750_MEAS_DELAY_MS));

    /* Read 2 bytes of light data */
    uint8_t data[2] = {0};
    ret = i2c_read_bytes(BH1750_ADDR, data, sizeof(data));
    if (ret != ESP_OK) {
        ESP_LOGE(TAG_SENSOR, "BH1750: read failed: %s", esp_err_to_name(ret));
        return ret;
    }

    /* Convert: raw / 1.2 = lux */
    uint16_t raw = ((uint16_t)data[0] << 8) | data[1];
    *lux = (uint16_t)(raw * 10 / 12);  /* integer approximation of raw/1.2 */

    ESP_LOGD(TAG_SENSOR, "BH1750 raw=0x%04X → %u lux", raw, *lux);
    return ESP_OK;
}

/* ── PIR init ──────────────────────────────────────────────────────── */
static esp_err_t pir_init(void)
{
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << PIR_GPIO),
        .mode         = GPIO_MODE_INPUT,
        .pull_up_en   = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_ENABLE,
        .intr_type    = GPIO_INTR_ANYEDGE,
    };
    esp_err_t ret = gpio_config(&io_conf);
    if (ret != ESP_OK) return ret;

    ret = gpio_install_isr_service(0);
    if (ret != ESP_OK && ret != ESP_ERR_INVALID_STATE) {
        /* ESP_ERR_INVALID_STATE means ISR service already installed — OK */
        return ret;
    }

    ret = gpio_isr_handler_add(PIR_GPIO, pir_isr_handler, NULL);
    if (ret != ESP_OK) return ret;

    /* Read initial state */
    s_occupancy = gpio_get_level(PIR_GPIO);

    ESP_LOGI(TAG_SENSOR, "PIR sensor initialized on GPIO %d (initial: %s)",
             PIR_GPIO, s_occupancy ? "OCCUPIED" : "VACANT");
    return ESP_OK;
}

/* ═══════════════════════════════════════════════════════════════════ */
/* HAL Public API                                                      */
/* ═══════════════════════════════════════════════════════════════════ */

esp_err_t sensor_hal_init(void)
{
    ESP_LOGI(TAG_SENSOR, "Initializing REAL sensor HAL");
    ESP_LOGI(TAG_SENSOR, "I2C: SDA=GPIO%d  SCL=GPIO%d  %d Hz",
             I2C_MASTER_SDA_IO, I2C_MASTER_SCL_IO, I2C_MASTER_FREQ_HZ);

    /* 1. I2C bus */
    esp_err_t ret = i2c_master_init();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG_SENSOR, "I2C master init failed: %s", esp_err_to_name(ret));
        return ret;
    }
    ESP_LOGI(TAG_SENSOR, "I2C master initialized");

    /* 2. DHT20 — check calibration status */
    ret = dht20_check_status();
    if (ret != ESP_OK) {
        ESP_LOGW(TAG_SENSOR, "DHT20 status check failed (sensor may not be connected)");
        /* Non-fatal: sensor might just not be on the bus yet */
    } else {
        ESP_LOGI(TAG_SENSOR, "DHT20 (AHT20) ready at 0x%02X", DHT20_ADDR);
    }

    /* 3. BH1750 — send power-on to verify it responds */
    uint8_t cmd = BH1750_CMD_POWER_ON;
    ret = i2c_write_bytes(BH1750_ADDR, &cmd, 1);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG_SENSOR, "BH1750 power-on failed (sensor may not be connected)");
    } else {
        ESP_LOGI(TAG_SENSOR, "BH1750 ready at 0x%02X", BH1750_ADDR);
    }

    /* 4. PIR sensor GPIO */
    ret = pir_init();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG_SENSOR, "PIR GPIO init failed: %s", esp_err_to_name(ret));
        return ret;
    }

    ESP_LOGI(TAG_SENSOR, "All sensors initialized");
    return ESP_OK;
}

esp_err_t sensor_hal_read_env(int16_t *temp, uint16_t *humidity, uint16_t *light)
{
    esp_err_t ret;

    /* Read temperature & humidity from DHT20 */
    ret = dht20_read(temp, humidity);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG_SENSOR, "DHT20 read failed, zeroing temp/humidity");
        *temp = 0;
        *humidity = 0;
    }

    /* Read light level from BH1750 */
    ret = bh1750_read_lux(light);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG_SENSOR, "BH1750 read failed, zeroing light");
        *light = 0;
    }

    return ESP_OK;  /* partial reads are OK — individual warnings logged */
}

uint8_t sensor_hal_get_occupancy(void)
{
    /* Poll GPIO directly each call — don't rely only on ISR edges */
    s_occupancy = gpio_get_level(PIR_GPIO);
    return s_occupancy;
}
