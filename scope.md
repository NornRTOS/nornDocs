# Scope: what nornRTOS has, what it leaves out, what is coming

A product team's first questions are not about the scheduler. This page answers them in
one place; the modules' READMEs have the details of what exists.

| Area | Here today | Not here, on purpose | Coming, and what it waits for |
|---|---|---|---|
| Kernel | nornCore: fixed priority, one task per priority, ceiling mutexes, queues, events, streams, timers, dynamic tasks, SMP on the ESP32, AVR (UNO, Mega 2560) and ESP32 ports | Time slicing, priority inheritance, memory protection and privilege separation (design.md "What is deliberately absent") | A Cortex-M port (BASEPRI, PendSV, MPU stack guard, tick on LPTIM/RTC): a board and the decision to start |
| TCP/IP | nornNET, its own stack: IPv4, ARP, ICMP, UDP, DHCP client, DNS, TCP (RFC 5681 congestion control, RFC 6298, TIME_WAIT); SLIP, TAP, QEMU Ethernet and the ESP32 radio as devices | lwIP and the BSD socket API: nornNET's API is its own, code written against lwIP is not a drop-in | IPv6 when a deployment needs it (none does today); W5500 Ethernet over SPI (a module to buy); the day long stability gate before any release claim |
| WiFi | nornWIFI: the ESP32 station on Espressif's radio binaries without ESP-IDF or FreeRTOS, WPA2-PSK with PMF, DHCP, reconnection; both cores or one | Soft AP, ESP-NOW, SNTP, modem power save (nornWIFI plan step 7) | Power save together with light sleep (a current meter); SNTP when a product keeps time |
| HTTP | nornHTTP: a buffer-free HTTP/1.1 client, chunked and streamed bodies, fuzzed, measured on the board | A server, HTTP/2, WebSocket | |
| TLS | Nothing: nornHTTP is plain text, so it is a LAN client today | | nornTLS, possibly as part of a nornCrypto module: mbedTLS over nornNET on the ESP32 (150 to 200 KB flash, 40 to 60 KB RAM), through nornHTTP's transport interface, which is made for it. A decision and a plan, not started |
| Bluetooth | Nothing | | BLE later, when a product needs it: Espressif's controller binary plus a host stack (NimBLE), the second core is free for it. WiFi and TCP come first |
| USB | Nothing to do: the ESP32 has no USB, the Mega's 16U2 is a serial bridge | | |
| Storage | nornStore: a key/value store in two erase blocks of flash (ESP32) or EEPROM (AVR), typed, with change notification and the `config` command | A file system | nornStore may grow toward a littlefs-like store (wear levelling, more than two blocks, larger values) when a product needs logs or files |
| Boot and update | The ROM loads the image from flash offset 0x1000; code in flash at 0x80000 through the cache. `make OTA=1`: a 2.6 KB selector at 0x1000, two slots, a slot table with SHA-256 and automatic rollback after three unconfirmed boots (nornCore README "Boot and update") | ESP-IDF's second stage bootloader and partition table | The application side exists too: hal/ota.h (begin, write, end, confirm) with examples/ota fetching the image over HTTP, a 403 KB update in 7 to 11 s over Wi-Fi, roll back tested. Images are signed (ed25519, the selector checks the signature of the digest in 120 ms; a forged image is rejected at its first boot). **Next in the plan: flash encryption and secure boot through the ROM's eFuses**, which turn "the selector checks the slot" into "the ROM checks the selector"; the selector already reads flash through the cache window as encryption requires. Not started: the eFuses are irreversible and wait for a board set aside for it |
| Low power | Idle sleep per tick on both ports, tickless (ticks only) and deep sleep with RTC wake-up on the ESP32 | | Light sleep on the ESP32, tickless with power-save on the AVR (a board with a 32 kHz crystal or an external RTC), measured with a current meter (nornCore README "Low power") |
| Peripherals | UART, GPIO, flash/EEPROM, the application timer, DHT11 and HD44780 drivers | | I2C, SPI, ADC, PWM as HAL drivers, in that order, when the hardware to test against is here |
| Console and diagnostics | nornSHELL (nosh): ps, sched, log, run/stop/wait, uptime, config; log classes; run time statistics; the persistent panic record; stack canary, monitor and hardware guard | | |
| Tooling | make per board, QEMU and simavr, the test suite on board and emulator, size and byte identity checks, Doxygen, the user guide | A PlatformIO platform (planned, not started) | |

## What comes next

In this order, as of 2026-11-20: flash encryption and secure boot for the OTA build (the
eFuse steps above, on a board set aside for them); nornTLS; the HAL drivers (I2C first)
when the hardware to test against is here; light sleep on the ESP32 and tickless with
power-save on the AVR, measured with a current meter; a Cortex-M port. Nothing of this is
dated; each item says what it waits for in the table.

## The radio binaries

nornWIFI drives the ESP32 radio with five binary libraries from Espressif, taken from
ESP-IDF v5.5.6: libnet80211, libpp, libcore, libphy and librtc, plus the ROM's symbols
(esp32_rom.ld) and the radio's OS adapter interface, version 8 of `wifi_osi_funcs_t`.
Everything else around them (the adapter, the supplicant port, the network device) is
source. The libraries are binary only, under Espressif's licence (THIRD_PARTY_LICENSES),
and pinned in the nornWIFI repository: a newer ESP-IDF may change the adapter version or
the libraries' behaviour, so an upgrade is a measured step (the nw01 to nw05 applications
and the throughput tables in the plan), not a file swap. The dependency is real; the open
alternative (esp32-open-mac in place of libnet80211 and libpp, libphy stays) was weighed
and is weeks of work for openness alone, so it is not planned. Flash and RAM of each
library are in nornWIFI's README.

## Licence

Business Source License 1.1 with Tenforward AB's Additional Use Grant (LICENSE.md in
every repository). Apache-2.0 was asked for in a review; it is a business decision and
stays open.
