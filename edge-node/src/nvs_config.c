#include "nvs_config.h"

#include <string.h>
#include "nvs.h"
#include "esp_log.h"

static const char *TAG = "nvs_config";

#define NVS_NAMESPACE "shrine"

esp_err_t nvs_config_load(node_config_t *config)
{
    esp_err_t err;

    /* NVS flash is assumed to be already initialised by main.c. */

    nvs_handle_t handle;
    size_t ssid_len = sizeof(config->wifi_ssid);
    size_t pass_len = sizeof(config->wifi_pass);
    size_t host_len = sizeof(config->osc_host);

    err = nvs_open(NVS_NAMESPACE, NVS_READONLY, &handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "nvs_open(\"%s\") failed: %s", NVS_NAMESPACE, esp_err_to_name(err));
        return err;
    }

    /* node_id */
    err = nvs_get_u8(handle, "node_id", &config->node_id);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "read node_id: %s", esp_err_to_name(err));
        goto done;
    }

    /* wifi_ssid */
    err = nvs_get_str(handle, "wifi_ssid", config->wifi_ssid, &ssid_len);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "read wifi_ssid: %s", esp_err_to_name(err));
        goto done;
    }

    /* wifi_pass */
    err = nvs_get_str(handle, "wifi_pass", config->wifi_pass, &pass_len);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "read wifi_pass: %s", esp_err_to_name(err));
        goto done;
    }

    /* osc_host */
    err = nvs_get_str(handle, "osc_host", config->osc_host, &host_len);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "read osc_host: %s", esp_err_to_name(err));
        goto done;
    }

    /* osc_port */
    err = nvs_get_u16(handle, "osc_port", &config->osc_port);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "read osc_port: %s", esp_err_to_name(err));
        goto done;
    }

    /* base_k (optional — defaults to BASE_K_DEFAULT) */
    config->base_k = BASE_K_DEFAULT;
    err = nvs_get_u16(handle, "base_k", &config->base_k);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        err = ESP_OK;  /* not an error — key is optional */
    } else if (err != ESP_OK) {
        ESP_LOGE(TAG, "read base_k: %s", esp_err_to_name(err));
        goto done;
    }

    /* step_k (optional — defaults to STEP_K_DEFAULT) */
    config->step_k = STEP_K_DEFAULT;
    err = nvs_get_u16(handle, "step_k", &config->step_k);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        err = ESP_OK;  /* not an error — key is optional */
    } else if (err != ESP_OK) {
        ESP_LOGE(TAG, "read step_k: %s", esp_err_to_name(err));
        goto done;
    }

    /* window_n (optional — defaults to WINDOW_N_DEFAULT) */
    config->window_n = WINDOW_N_DEFAULT;
    err = nvs_get_u16(handle, "window_n", &config->window_n);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        err = ESP_OK;  /* not an error — key is optional */
    } else if (err != ESP_OK) {
        ESP_LOGE(TAG, "read window_n: %s", esp_err_to_name(err));
        goto done;
    }

    /* floor_stdev (optional — defaults to 0 = no subtraction) */
    config->floor_stdev = CAL_FLOOR_DEFAULT;
    err = nvs_get_u16(handle, "floor_stdev", &config->floor_stdev);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        err = ESP_OK;
    } else if (err != ESP_OK) {
        ESP_LOGE(TAG, "read floor_stdev: %s", esp_err_to_name(err));
        goto done;
    }

    /* floor_gsr0 (optional) */
    config->floor_gsr0 = CAL_FLOOR_DEFAULT;
    err = nvs_get_u16(handle, "floor_gsr0", &config->floor_gsr0);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        err = ESP_OK;
    } else if (err != ESP_OK) {
        ESP_LOGE(TAG, "read floor_gsr0: %s", esp_err_to_name(err));
        goto done;
    }

    /* floor_gsr1 (optional) */
    config->floor_gsr1 = CAL_FLOOR_DEFAULT;
    err = nvs_get_u16(handle, "floor_gsr1", &config->floor_gsr1);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        err = ESP_OK;
    } else if (err != ESP_OK) {
        ESP_LOGE(TAG, "read floor_gsr1: %s", esp_err_to_name(err));
        goto done;
    }

    /* floor_gsr2 (optional) */
    config->floor_gsr2 = CAL_FLOOR_DEFAULT;
    err = nvs_get_u16(handle, "floor_gsr2", &config->floor_gsr2);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        err = ESP_OK;
    } else if (err != ESP_OK) {
        ESP_LOGE(TAG, "read floor_gsr2: %s", esp_err_to_name(err));
        goto done;
    }

    /* ceil_stdev (optional — defaults to CAL_CEIL_DEFAULT = 65535 = unconfigured) */
    config->ceil_stdev = CAL_CEIL_DEFAULT;
    err = nvs_get_u16(handle, "ceil_stdev", &config->ceil_stdev);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        err = ESP_OK;
    } else if (err != ESP_OK) {
        ESP_LOGE(TAG, "read ceil_stdev: %s", esp_err_to_name(err));
        goto done;
    }

    /* ceil_gsr0 (optional) */
    config->ceil_gsr0 = CAL_CEIL_DEFAULT;
    err = nvs_get_u16(handle, "ceil_gsr0", &config->ceil_gsr0);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        err = ESP_OK;
    } else if (err != ESP_OK) {
        ESP_LOGE(TAG, "read ceil_gsr0: %s", esp_err_to_name(err));
        goto done;
    }

    /* ceil_gsr1 (optional) */
    config->ceil_gsr1 = CAL_CEIL_DEFAULT;
    err = nvs_get_u16(handle, "ceil_gsr1", &config->ceil_gsr1);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        err = ESP_OK;
    } else if (err != ESP_OK) {
        ESP_LOGE(TAG, "read ceil_gsr1: %s", esp_err_to_name(err));
        goto done;
    }

    /* ceil_gsr2 (optional) */
    config->ceil_gsr2 = CAL_CEIL_DEFAULT;
    err = nvs_get_u16(handle, "ceil_gsr2", &config->ceil_gsr2);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        err = ESP_OK;
    } else if (err != ESP_OK) {
        ESP_LOGE(TAG, "read ceil_gsr2: %s", esp_err_to_name(err));
        goto done;
    }

    ESP_LOGI(TAG, "config loaded: node_id=%u base_k=%u step_k=%u window_n=%u ssid=%s osc=%s:%u",
             config->node_id, config->base_k, config->step_k, config->window_n,
             config->wifi_ssid, config->osc_host, config->osc_port);
    ESP_LOGI(TAG, "cal floors: stdev=%u gsr=[%u, %u, %u]",
             config->floor_stdev, config->floor_gsr0,
             config->floor_gsr1, config->floor_gsr2);
    ESP_LOGI(TAG, "cal ceils: stdev=%u gsr=[%u, %u, %u]",
             config->ceil_stdev, config->ceil_gsr0,
             config->ceil_gsr1, config->ceil_gsr2);

done:
    nvs_close(handle);
    return err;
}
