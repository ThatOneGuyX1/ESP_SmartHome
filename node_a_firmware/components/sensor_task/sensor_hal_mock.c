#include "sensor_hal.h"
#include "common.h"
#include "esp_log.h"
#include "esp_random.h"

static uint32_t s_sample_count = 0;
static uint16_t s_light = 500;        /* starting lux */
static uint8_t  s_occupancy = 0;

esp_err_t sensor_hal_init(void)
{
    ESP_LOGI(TAG_SENSOR, "Mock sensor HAL initialized");
    ESP_LOGW(TAG_SENSOR, "Using SIMULATED sensor data (CONFIG_USE_MOCK_SENSORS=y)");
    return ESP_OK;
}

esp_err_t sensor_hal_read_env(int16_t *temp, uint16_t *humidity, uint16_t *light)
{
    s_sample_count++;

    /*
     * Temperature: oscillates between 20.00°C and 26.00°C
     * Uses a simple triangle wave based on sample count.
     */
    int16_t offset = (int16_t)((s_sample_count % 60) * 10);
    if ((s_sample_count / 60) % 2 == 0) {
        *temp = 2000 + offset;  /* rising: 20.00 → 25.90 */
    } else {
        *temp = 2600 - offset;  /* falling: 26.00 → 20.10 */
    }

    /* Humidity: relatively stable around 45% with small jitter */
    int16_t jitter = (int16_t)((esp_random() % 200) - 100);  /* ±1.00% */
    *humidity = (uint16_t)(4500 + jitter);

    /* Light: random walk clamped to 0–10000 lux */
    int16_t light_step = (int16_t)((esp_random() % 200) - 100);  /* ±100 lux */
    int32_t new_light = (int32_t)s_light + light_step;
    if (new_light < 0) new_light = 0;
    if (new_light > 10000) new_light = 10000;
    s_light = (uint16_t)new_light;
    *light = s_light;

    return ESP_OK;
}

uint8_t sensor_hal_get_occupancy(void)
{
    /* Toggle occupancy every 5th sample to simulate room entry/exit */
    if (s_sample_count % 5 == 0 && s_sample_count > 0) {
        s_occupancy = !s_occupancy;
        ESP_LOGI(TAG_SENSOR, "Mock occupancy changed to: %s",
                 s_occupancy ? "OCCUPIED" : "VACANT");
    }
    return s_occupancy;
}
