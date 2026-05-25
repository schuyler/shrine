CC      = cc
CFLAGS  = -Wall -Wextra -std=c99 \
          -I../src \
          -I../components/tinyosc \
          -I stubs

.PHONY: all test_tdm test_tinyosc clean

all: test_tdm test_tinyosc

test_tdm: test_tdm.c ../src/tdm.c
	$(CC) $(CFLAGS) -o $@ $^ -lm
	./$@

test_tinyosc: test_tinyosc.c ../components/tinyosc/tinyosc.c
	$(CC) $(CFLAGS) -o $@ $^
	./$@

clean:
	rm -f test_tdm test_tinyosc
