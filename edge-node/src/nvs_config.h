#ifndef NVS_CONFIG_H
#define NVS_CONFIG_H

#include "esp_err.h"
#include "config.h"

/**
 * Load node configuration from NVS namespace "shrine".
 *
 * Reads: node_id (u8), leader (u8 → bool), wifi_ssid, wifi_pass,
 *        osc_host (strings), osc_port (u16).
 *
 * Returns ESP_OK on success.  The caller should treat any other return value
 * as fatal and restart the device.
 */
esp_err_t nvs_config_load(node_config_t *config);

#endif /* NVS_CONFIG_H */
