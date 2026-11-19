/**
 * @file hello.c
 * The smallest nornRTOS application: one task that prints a line once a second and
 * toggles the board's LED, the idle hook counting idle loops. rtos_config.h names the
 * number of tasks and asks for the HAL's hooks (a panic is printed, not swallowed);
 * everything else is the kernel's default. Build it from the nornRTOS directory:
 * make APP=hello BOARD=esp32 sim.
 */

#include "rtos.h"
#include "uart.h"
#include "board.h"

static const gpio_pin_t _led = BOARD_PIN_LED;
static volatile uint32_t _idleLoops;

void rtos_idleHook(void)
{
    ++ _idleLoops;
}

static void task(void *arg)
{
    uint32_t n = 0;
    (void)arg;
    gpio_output(&_led);
    for(;;)
    {
        (void)rtos_waitPeriodic(RTOS_S(1));
        gpio_toggle(&_led);
        uart_puts("hello from nornRTOS, second ");
        uart_putU32(++n);
        uart_puts(", idle loops ");
        uart_putU32(_idleLoops);
        uart_puts("\r\n");
    }
}

int main(void)
{
    uart_init(UART_BAUD_DEFAULT);
    uart_puts("\r\nnornRTOS hello\r\n");
    rtos_init();
    RTOS_TASK(1, task, NULL, RTOS_STACK_DEFAULT);
    rtos_start();
    return 0;
}
