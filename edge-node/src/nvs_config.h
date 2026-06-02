#ifndef NVS_CONFIG_H
#define NVS_CONFIG_H

#include "esp_err.h"
#include "config.h"

/**
 * Load node configuration from NVS namespace "shrine".
 *
 * Required keys: node_id (u8), wifi_ssid, wifi_pass, osc_host (strings),
 *                osc_port (u16).
 * Optional keys (use defaults if absent): base_k (u16, default 180),
 *                step_k (u16, default 20), window_n (u16, default 1800).
 *
 * Returns ESP_OK on success.  The caller should treat any other return value
 * as fatal and restart the device.
 */
esp_err_t nvs_config_load(node_config_t *config);

#endif /* NVS_CONFIG_H */
