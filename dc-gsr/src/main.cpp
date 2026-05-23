#include <Arduino.h>
#include <WiFi.h>

static const int ADC_PIN = 36;
static const float R_REF = 100000.0f;
static const float V_SUPPLY_MV = 3300.0f;
static const float ALPHA = 0.1f;
static const unsigned long SAMPLE_INTERVAL = 100;

static float filtered_mv = 0.0f;
static unsigned long last_sample_time = 0;
static bool first_sample = true;

void setup() {
    Serial.begin(115200);
    WiFi.mode(WIFI_OFF);
    btStop();
    analogSetPinAttenuation(ADC_PIN, ADC_11db);
    Serial.println("raw_adc\tvoltage_mv\tresistance_ohm\tconductance_us\tfiltered_mv");
}

void loop() {
    unsigned long now = millis();
    if (now - last_sample_time < SAMPLE_INTERVAL) return;
    last_sample_time = now;

    float voltage_mv = (float)analogReadMilliVolts(ADC_PIN);
    int raw_adc = (int)(voltage_mv * 4095.0f / V_SUPPLY_MV);

    if (first_sample) {
        filtered_mv = voltage_mv;
        first_sample = false;
    } else {
        filtered_mv = ALPHA * voltage_mv + (1.0f - ALPHA) * filtered_mv;
    }

    float resistance_ohm;
    float conductance_us;

    if (V_SUPPLY_MV - voltage_mv < 1.0f) {
        resistance_ohm = 0.0f;
        conductance_us = 0.0f;
    } else if (voltage_mv < 1.0f) {
        resistance_ohm = 0.0f;
        conductance_us = 0.0f;
    } else {
        resistance_ohm = R_REF * voltage_mv / (V_SUPPLY_MV - voltage_mv);
        conductance_us = 1.0e6f / resistance_ohm;
    }

    Serial.print(raw_adc);
    Serial.print('\t');
    Serial.print((int)voltage_mv);
    Serial.print('\t');
    Serial.print((int)resistance_ohm);
    Serial.print('\t');
    Serial.print(conductance_us, 2);
    Serial.print('\t');
    Serial.println(filtered_mv, 1);
}
