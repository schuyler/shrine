CC      = cc
CFLAGS  = -Wall -Wextra -std=c99 \
          -I../src \
          -I../components/tinyosc \
          -I stubs

.PHONY: all test_tinyosc test_fdm_math test_adc_parse clean

all: test_tinyosc test_fdm_math test_adc_parse

test_tinyosc: test_tinyosc.c ../components/tinyosc/tinyosc.c
	$(CC) $(CFLAGS) -o $@ $^
	./$@

test_fdm_math: test_fdm_math.c ../src/fdm_math.c
	$(CC) $(CFLAGS) -o $@ $^ -lm
	./$@

test_adc_parse: test_adc_parse.c ../src/adc_parse.c
	$(CC) $(CFLAGS) -o $@ $^ -lm
	./$@

clean:
	rm -f test_tinyosc test_fdm_math test_adc_parse
