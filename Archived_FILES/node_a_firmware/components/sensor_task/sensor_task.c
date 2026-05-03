#include "sensor_task.h"
#include "sensor_hal.h"
#include "mesh_comm.h"
#include "message.h"
#include "common.h"

#include "esp_log.h"
#include "esp_sleep.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

/* ── Default config fallbacks ──────────────────────────────────────── */
#ifndef CONFIG_SENSOR_SAMPLE_INTERVAL_MS
#define CONFIG_SENSOR_SAMPLE_INTERVAL_MS 30000
#endif

#ifndef CONFIG_PIR_GPIO_PIN
#define CONFIG_PIR_GPIO_PIN 25
#endif

#define SENSOR_TASK_STACK_SIZE  4096
#define SENSOR_TASK_PRIORITY    (tskIDLE_PRIORITY + 2)

/* ── Moving Average Filter ────────────────────────────────────────── */
#define FILTER_WINDOW_SIZE  5

typedef struct {
    int32_t  buf[FILTER_WINDOW_SIZE];
    uint8_t  idx;
    uint8_t  count;  /* how many samples collected so far */
} filter_t;

static filter_t s_temp_filter   = {0};
static filter_t s_hum_filter    = {0};
static filter_t s_light_filter  = {0};

static int32_t filter_update(filter_t *f, int32_t sample)
{
    f->buf[f->idx] = sample;
    f->idx = (f->idx + 1) % FILTER_WINDOW_SIZE;
    if (f->count < FILTER_WINDOW_SIZE) f->count++;

    int64_t sum = 0;
    for (uint8_t i = 0; i < f->count; i++) {
        sum += f->buf[i];
    }
    return (int32_t)(sum / f->count);
}

/* ── PIR Occupancy Logic ──────────────────────────────────────────── */
/*
 * The HC-SR505 has an ~8s retriggerable hold time. Its output cycles
 * HIGH-LOW-HIGH when someone is present, causing false VACANT blips.
 *
 * Strategy:
 *   - ANY motion (raw HIGH) → immediately confirm OCCUPIED
 *   - To go VACANT → must see VACANT_TIMEOUT consecutive LOW reads
 *     (e.g., 12 reads × 5s = 60 seconds of no motion)
 */
#define VACANT_TIMEOUT_COUNT  12   /* consecutive LOW reads before confirming VACANT */

static uint8_t  s_debounced_occ       = 0;  /* confirmed occupancy state */
static uint8_t  s_vacant_counter      = 0;  /* consecutive LOW reads */

static uint8_t debounce_occupancy(uint8_t raw_occ)
{
    if (raw_occ) {
        /* Motion detected — immediately OCCUPIED, reset vacant counter */
        s_vacant_counter = 0;
        if (!s_debounced_occ) {
            s_debounced_occ = 1;
            ESP_LOGI(TAG_SENSOR, "PIR: motion detected → OCCUPIED");
        }
    } else {
        /* No motion — count consecutive VACANT reads */
        s_vacant_counter++;
        if (s_debounced_occ && s_vacant_counter >= VACANT_TIMEOUT_COUNT) {
            s_debounced_occ = 0;
            ESP_LOGI(TAG_SENSOR, "PIR: no motion for %d reads → VACANT",
                     VACANT_TIMEOUT_COUNT);
        }
    }
    return s_debounced_occ;
}

/* ── Deadband / Adaptive Reporting ────────────────────────────────── */
#define TEMP_DEADBAND      50    /* 0.50°C — skip send if change < this */
#define HUMIDITY_DEADBAND   200  /* 2.00% RH */
#define LIGHT_DEADBAND      20   /* 20 lux */
#define MAX_SILENT_CYCLES   6    /* send at least every Nth cycle regardless */

static int16_t  s_last_sent_temp     = INT16_MIN;
static uint16_t s_last_sent_humidity = 0;
static uint16_t s_last_sent_light    = 0;
static uint8_t  s_silent_cycles      = 0;

static bool readings_changed(int16_t temp, uint16_t humidity, uint16_t light, uint8_t occ, uint8_t prev_occ)
{
    /* Always send if occupancy changed */
    if (occ != prev_occ) return true;

    /* Always send first reading or if max silent cycles reached */
    if (s_last_sent_temp == INT16_MIN) return true;
    if (s_silent_cycles >= MAX_SILENT_CYCLES) return true;

    /* Check deadbands */
    int16_t temp_diff = (temp > s_last_sent_temp) ? (temp - s_last_sent_temp) : (s_last_sent_temp - temp);
    int16_t hum_diff  = (humidity > s_last_sent_humidity) ? (humidity - s_last_sent_humidity) : (s_last_sent_humidity - humidity);
    int16_t lux_diff  = (light > s_last_sent_light) ? (light - s_last_sent_light) : (s_last_sent_light - light);

    return (temp_diff >= TEMP_DEADBAND ||
            hum_diff  >= HUMIDITY_DEADBAND ||
            lux_diff  >= LIGHT_DEADBAND);
}

/* ── Task 3: Dynamic thresholds (static globals, settable at runtime) ── */
static int16_t s_temp_high_threshold = 3500;  /* 35.00°C */
static int16_t s_temp_low_threshold  = 500;   /* 5.00°C  */

void sensor_task_set_temp_thresholds(int16_t high_c100, int16_t low_c100)
{
    s_temp_high_threshold = high_c100;
    s_temp_low_threshold  = low_c100;
    ESP_LOGI(TAG_SENSOR, "Thresholds updated: high=%.2f°C  low=%.2f°C",
             high_c100 / 100.0f, low_c100 / 100.0f);
}

void sensor_task_get_temp_thresholds(int16_t *high_c100, int16_t *low_c100)
{
    if (high_c100) *high_c100 = s_temp_high_threshold;
    if (low_c100)  *low_c100  = s_temp_low_threshold;
}

/* ── Sensor read-and-send (shared by both always-on and deep-sleep paths) ── */
static void sensor_read_and_send(uint8_t *prev_occupancy, bool *first_reading)
{
    int16_t  temp = 0;
    uint16_t humidity = 0;
    uint16_t light = 0;

    esp_err_t ret = sensor_hal_read_env(&temp, &humidity, &light);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG_SENSOR, "Failed to read sensors: %s", esp_err_to_name(ret));
        return;
    }

    /* ── Apply moving average filter ── */
    temp     = (int16_t)filter_update(&s_temp_filter, temp);
    humidity = (uint16_t)filter_update(&s_hum_filter, humidity);
    light    = (uint16_t)filter_update(&s_light_filter, light);

    uint8_t raw_occ = sensor_hal_get_occupancy();
    uint8_t occupancy = debounce_occupancy(raw_occ);

    ESP_LOGI(TAG_SENSOR, "Reading: temp=%.2f°C humidity=%.2f%% light=%u lux occ=%s (raw=%s, filtered, n=%u)",
             temp / 100.0f, humidity / 100.0f, light,
             occupancy ? "OCCUPIED" : "VACANT",
             raw_occ ? "OCC" : "VAC",
             s_temp_filter.count);

    /* ── Check temperature thresholds for ALERT (dynamic globals) ── */
    if (temp > s_temp_high_threshold || temp < s_temp_low_threshold) {
        ESP_LOGW(TAG_SENSOR, "Temperature ALERT: %.2f°C (thresholds: low=%.2f high=%.2f)",
                 temp / 100.0f,
                 s_temp_low_threshold / 100.0f,
                 s_temp_high_threshold / 100.0f);

        mesh_frame_t alert_frame = {0};
        memcpy(alert_frame.header.dst_mac, GATEWAY_MAC, 6);
        alert_frame.header.ttl = MESH_DEFAULT_TTL;

        alert_payload_t alert = {
            .alert_code = 1,  /* triggered */
            .sensor_reading = (uint16_t)((temp > 0) ? temp : -temp),
        };
        alert_payload_pack(&alert_frame, &alert);

        esp_err_t send_ret = mesh_comm_send(&alert_frame);
        if (send_ret != ESP_OK) {
            ESP_LOGW(TAG_SENSOR, "Failed to send ALERT frame");
        }
    }

    /* ── Detect occupancy transition → send immediate ALERT ── */
    if (!(*first_reading) && occupancy != *prev_occupancy) {
        ESP_LOGI(TAG_SENSOR, "Occupancy transition: %s -> %s",
                 *prev_occupancy ? "OCCUPIED" : "VACANT",
                 occupancy ? "OCCUPIED" : "VACANT");

        /* Send immediate occupancy alert (alert_code 0x10 = occupancy change) */
        mesh_frame_t occ_alert = {0};
        memcpy(occ_alert.header.dst_mac, GATEWAY_MAC, 6);
        occ_alert.header.ttl = MESH_DEFAULT_TTL;

        alert_payload_t occ_data = {
            .alert_code = 0x10,  /* occupancy transition */
            .sensor_reading = (uint16_t)occupancy,  /* new state: 0=vacant, 1=occupied */
        };
        alert_payload_pack(&occ_alert, &occ_data);

        esp_err_t occ_ret = mesh_comm_send(&occ_alert);
        if (occ_ret != ESP_OK) {
            ESP_LOGW(TAG_SENSOR, "Failed to send occupancy ALERT frame");
        } else {
            ESP_LOGI(TAG_SENSOR, "Occupancy ALERT sent: %s",
                     occupancy ? "OCCUPIED" : "VACANT");
        }
    }
    *prev_occupancy = occupancy;
    *first_reading = false;

    /* ── Adaptive reporting: only send if readings changed significantly ── */
    if (readings_changed(temp, humidity, light, occupancy, *prev_occupancy)) {
        mesh_frame_t frame = {0};
        memcpy(frame.header.dst_mac, GATEWAY_MAC, 6);
        frame.header.ttl = MESH_DEFAULT_TTL;

        sensor_data_payload_t payload = {
            .temperature = temp,
            .humidity = humidity,
            .light_level = light,
            .occupancy_state = occupancy,
        };
        sensor_payload_pack(&frame, &payload);

        esp_err_t send_ret = mesh_comm_send(&frame);
        if (send_ret != ESP_OK) {
            ESP_LOGW(TAG_SENSOR, "Failed to send SENSOR_DATA frame");
        } else {
            ESP_LOGI(TAG_SENSOR, "SENSOR_DATA sent (changed or keepalive)");
            s_last_sent_temp     = temp;
            s_last_sent_humidity = humidity;
            s_last_sent_light    = light;
            s_silent_cycles      = 0;
        }
    } else {
        s_silent_cycles++;
        ESP_LOGI(TAG_SENSOR, "Readings stable — skipped TX (%u/%u cycles)",
                 s_silent_cycles, MAX_SILENT_CYCLES);
    }
}

/* ── Deep-sleep one-shot path ──────────────────────────────────────── */
#if !defined(CONFIG_NODE_ALWAYS_ON_RELAY) || !CONFIG_NODE_ALWAYS_ON_RELAY

/*
 * In deep-sleep mode we don't use a FreeRTOS task loop. Instead,
 * sensor_task_start() does a single read-and-send, then puts the
 * ESP32 to sleep. On wake the chip reboots, app_main() runs again,
 * and we repeat.
 *
 * Wake sources:
 *   1. Timer — CONFIG_SENSOR_SAMPLE_INTERVAL_MS
 *   2. ext1  — PIR GPIO (any-high level trigger)
 */

static void configure_deep_sleep(void)
{
    /* Timer wakeup */
    uint64_t sleep_us = (uint64_t)CONFIG_SENSOR_SAMPLE_INTERVAL_MS * 1000ULL;
    esp_sleep_enable_timer_wakeup(sleep_us);
    ESP_LOGI(TAG_SENSOR, "Deep-sleep timer: %d ms", CONFIG_SENSOR_SAMPLE_INTERVAL_MS);

    /*
     * ext1 wakeup on PIR GPIO (any-high).
     * Note: ext1 only works on RTC GPIOs. GPIO 25 is RTC GPIO 6 — valid.
     */
    uint64_t pir_mask = (1ULL << CONFIG_PIR_GPIO_PIN);
    esp_sleep_enable_ext1_wakeup(pir_mask, ESP_EXT1_WAKEUP_ANY_HIGH);
    ESP_LOGI(TAG_SENSOR, "Deep-sleep ext1 wakeup: GPIO %d (PIR motion)", CONFIG_PIR_GPIO_PIN);
}

esp_err_t sensor_task_start(void)
{
    ESP_LOGI(TAG_SENSOR, "Sensor task (DEEP-SLEEP mode)");

    /* Check wakeup reason */
    esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();
    switch (cause) {
        case ESP_SLEEP_WAKEUP_TIMER:
            ESP_LOGI(TAG_SENSOR, "Woke from deep sleep: TIMER");
            break;
        case ESP_SLEEP_WAKEUP_EXT1:
            ESP_LOGI(TAG_SENSOR, "Woke from deep sleep: PIR MOTION (ext1)");
            break;
        case ESP_SLEEP_WAKEUP_UNDEFINED:
        default:
            ESP_LOGI(TAG_SENSOR, "First boot (not waking from deep sleep)");
            break;
    }

    /* Init sensors */
    esp_err_t ret = sensor_hal_init();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG_SENSOR, "Sensor HAL init failed: %s", esp_err_to_name(ret));
        ESP_LOGE(TAG_SENSOR, "Going to sleep and retrying on next wake");
        configure_deep_sleep();
        esp_deep_sleep_start();
        return ret;  /* never reached */
    }

    /* Single read-and-send cycle */
    uint8_t prev_occ = 0;
    bool first = true;
    sensor_read_and_send(&prev_occ, &first);

    /*
     * Give the radio a moment to finish transmitting before we
     * kill it with deep sleep. 200 ms is generous for ESP-NOW.
     */
    vTaskDelay(pdMS_TO_TICKS(200));

    /* Configure wakeup sources and enter deep sleep */
    configure_deep_sleep();
    ESP_LOGI(TAG_SENSOR, "Entering deep sleep...");
    esp_deep_sleep_start();

    /* Never reached */
    return ESP_OK;
}

#else /* CONFIG_NODE_ALWAYS_ON_RELAY is enabled */

/* ── Always-on relay path (original vTaskDelay loop) ───────────────── */

static void sensor_task(void *arg)
{
    (void)arg;

    esp_err_t ret = sensor_hal_init();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG_SENSOR, "Sensor HAL init failed: %s", esp_err_to_name(ret));
        ESP_LOGE(TAG_SENSOR, "Sensor task aborting");
        vTaskDelete(NULL);
        return;
    }

    uint8_t prev_occupancy = 0;
    bool first_reading = true;

    while (1) {
        sensor_read_and_send(&prev_occupancy, &first_reading);
        vTaskDelay(pdMS_TO_TICKS(CONFIG_SENSOR_SAMPLE_INTERVAL_MS));
    }
}

esp_err_t sensor_task_start(void)
{
    ESP_LOGI(TAG_SENSOR, "Sensor task (ALWAYS-ON relay mode)");

    BaseType_t ret = xTaskCreate(
        sensor_task,
        "sensor_task",
        SENSOR_TASK_STACK_SIZE,
        NULL,
        SENSOR_TASK_PRIORITY,
        NULL
    );

    if (ret != pdPASS) {
        ESP_LOGE(TAG_SENSOR, "Failed to create sensor task");
        return ESP_ERR_NO_MEM;
    }

    ESP_LOGI(TAG_SENSOR, "Sensor task started (interval=%d ms)",
             CONFIG_SENSOR_SAMPLE_INTERVAL_MS);
    return ESP_OK;
}

#endif /* CONFIG_NODE_ALWAYS_ON_RELAY */
