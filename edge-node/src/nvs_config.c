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
    uint8_t leader_u8 = 0;
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

    /* leader → is_leader */
    err = nvs_get_u8(handle, "leader", &leader_u8);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "read leader: %s", esp_err_to_name(err));
        goto done;
    }
    config->is_leader = (leader_u8 != 0);

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

    ESP_LOGI(TAG, "config loaded: node_id=%u leader=%d ssid=%s osc=%s:%u",
             config->node_id, config->is_leader,
             config->wifi_ssid, config->osc_host, config->osc_port);

done:
    nvs_close(handle);
    return err;
}
