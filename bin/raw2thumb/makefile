SHELL=/bin/sh
CORES:=$(shell grep -c ^processor /proc/cpuinfo)
CC=gcc
CFLAGS= -I/usr/include/leptonica -I../pageDetector -I../common -L/usr/lib
ifneq ("1", "$(CORES)") 
	CFLAGS += -O3	
endif
LDFLAGS=-l lept -ltiff -ljpeg -lpng
OBJ=raw2thumb.o 

raw2thumb: $(OBJ) 
	$(CC) $(CFLAGS) $(OBJ) $(LDFLAGS) -o $@