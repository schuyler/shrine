#include "adc_read.h"

#include <string.h>
#include <stdbool.h>
#include "driver/spi_master.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "config.h"

static const char *TAG = "adc_read";

static spi_device_handle_t s_spi = NULL;

/*
 * MCP3201 transfers 16 bits per transaction.
 * The device outputs a null bit (bit 15), then the 12-bit result MSB-first
 * (bits 14..3), then an LSB-first echo (bits 2..0, not used).
 *
 * Extraction: (raw >> 2) & 0x0FFF gives the 12-bit value directly from
 * the MSB-first segment in bits [13:2] of the received word.
 */
#define MCP3201_BITS  16
#define MCP3201_EXTRACT(raw)  (((raw) >> 2) & 0x0FFF)

esp_err_t adc_init(void)
{
    spi_bus_config_t bus = {
        .mosi_io_num   = -1,           /* MCP3201 is read-only, no MOSI */
        .miso_io_num   = PIN_SPI_MISO,
        .sclk_io_num   = PIN_SPI_CLK,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = 2,          /* 16-bit frame */
    };

    esp_err_t err = spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_DISABLED);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "spi_bus_initialize failed: %s", esp_err_to_name(err));
        return err;
    }

    spi_device_interface_config_t dev = {
        .mode           = 0,            /* CPOL=0, CPHA=0 */
        .clock_speed_hz = SPI_CLOCK_HZ,
        .spics_io_num   = PIN_SPI_CS,
        .queue_size     = 1,
        .flags          = 0,
        .command_bits   = 0,
        .address_bits   = 0,
        .dummy_bits     = 0,
    };

    err = spi_bus_add_device(SPI2_HOST, &dev, &s_spi);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "spi_bus_add_device failed: %s", esp_err_to_name(err));
        return err;
    }

    ESP_LOGI(TAG, "SPI2 initialised: clk=%d miso=%d cs=%d @ %d Hz",
             PIN_SPI_CLK, PIN_SPI_MISO, PIN_SPI_CS, SPI_CLOCK_HZ);
    return ESP_OK;
}

void adc_acquire(void)
{
    esp_err_t err = spi_device_acquire_bus(s_spi, portMAX_DELAY);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "spi_device_acquire_bus failed: %s", esp_err_to_name(err));
    }
}

uint16_t adc_read_sample(void)
{
    /*
     * SPI_TRANS_USE_RXDATA: the driver places received bytes into t.rx_data[]
     * (a 4-byte inline buffer inside spi_transaction_t) rather than a heap
     * pointer.  This avoids any allocation on the hot path and works correctly
     * for transactions up to 32 bits.
     */
    spi_transaction_t t = {
        .length    = MCP3201_BITS,
        .rxlength  = MCP3201_BITS,
        .rx_buffer = NULL,
        .tx_buffer = NULL,
        .flags     = SPI_TRANS_USE_RXDATA,
    };
    /* Polling transfer for lowest latency in the tight sensing loop. */
    esp_err_t err = spi_device_polling_transmit(s_spi, &t);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "spi_device_polling_transmit failed: %s", esp_err_to_name(err));
        return 0;
    }

    /*
     * The ESP32-S3 SPI master writes received bytes into rx_data[] MSB-first.
     * Reconstruct the 16-bit big-endian word.
     */
    uint16_t raw = ((uint16_t)t.rx_data[0] << 8) | (uint16_t)t.rx_data[1];
    return MCP3201_EXTRACT(raw);
}

bool adc_read_into_buffer(uint16_t *buf, int count)
{
    spi_transaction_t t = {
        .length    = MCP3201_BITS,
        .rxlength  = MCP3201_BITS,
        .rx_buffer = NULL,
        .tx_buffer = NULL,
        .flags     = SPI_TRANS_USE_RXDATA,
    };

    for (int i = 0; i < count; i++) {
        esp_err_t err = spi_device_polling_transmit(s_spi, &t);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "spi_device_polling_transmit failed at sample %d: %s",
                     i, esp_err_to_name(err));
            return false;
        }
        uint16_t raw = ((uint16_t)t.rx_data[0] << 8) | (uint16_t)t.rx_data[1];
        buf[i] = MCP3201_EXTRACT(raw);
    }
    return true;
}

void adc_release(void)
{
    spi_device_release_bus(s_spi);
}
