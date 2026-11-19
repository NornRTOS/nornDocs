# Porting nornOS to a new architecture

The kernel never touches hardware. Everything it needs comes from `port/<arch>/port.h`,
which every kernel file includes through `rtos.h`. A port is three or four files plus a
make fragment; the AVR port (`port/avr/`) is the smallest complete example, the host port
(`port/host/`) shows the minimum that makes the kernel run at all, and the Xtensa port
(`port/xtensa/`) shows a CPU with register windows, a lazy FPU and a ROM loader.

## 1. What `port.h` must define

| Name | Meaning |
|---|---|
| `RTOS_PORT_MIN_STACK` | Smallest task stack the port accepts: interrupt frame plus one switch frame plus some calls. Measure it with applications/tc11 (stack left by a task that only blocks, by one woken from an interrupt, by one interrupted while running) and leave room for a frame or two of the task's own. |
| `RTOS_PORT_STACK_ALIGN` | Alignment of stack frames in the ABI (1 on AVR, 16 on Xtensa). |
| `RTOS_PORT_DEFAULT_STACK`, `RTOS_PORT_LARGE_STACK` | Recommended starting sizes for an ordinary and for a complex task (README "Stacks"), neither an upper bound; exported as RTOS_STACK_DEFAULT / RTOS_STACK_LARGE. |
| `RTOS_PORT_STACK_WARN` | Margin in bytes below which the idle stack monitor warns: about what the next interrupt or nested call needs. |
| `RTOS_PORT_WEAK` | Attribute for overridable functions, normally `__attribute__((weak))`. |
| `RTOS_PORT_NOINIT` | Attribute placing data where a reset does not clear it (the panic record). |
| `RTOS_PORT_STR(s)` | String literal in program memory (`PSTR` on AVR, identity elsewhere). |
| `RTOS_PORT_RUNTIME_HZ` | Frequency of the run time counter. |
| `rtos_port_ctx_t` | Saved context of a task, the first field of the TCB; a stack pointer on both ports. |
| `rtos_port_cs_t` | What `rtos_port_enterCritical` returns and `rtos_port_exitCritical` takes back. |
| `rtos_port_runtime_t` | Width of run time counts, 32 or 64 bits. |
| `RTOS_ISR(name)` | Defines the body of an interrupt handler the kernel may switch tasks after. Keep the two level macro so that `name` can itself be a macro. |
| `RTOS_PORT_HIGHEST_BIT(m)` | Optional: index of the highest set bit when the CPU has an instruction for it. |

Functions, inline or not:

| Function | Contract |
|---|---|
| `rtos_port_enterCritical` / `rtos_port_exitCritical` | Mask every interrupt that may call the kernel; nestable; the saved state is restored exactly. |
| `rtos_port_enableInterrupts` | Unmask unconditionally; called when a task starts and when the idle task begins. |
| `rtos_port_idleSleep` | Wait for the next interrupt; may be a no-op. |
| `rtos_port_halt` | Stop forever with interrupts off; `noreturn`. |
| `rtos_port_reset` | Reset the system; `noreturn`. |
| `rtos_port_getResetCause` | One of `RTOS_RESET_*` for the last reset. |
| `rtos_port_switchContext` | Called with interrupts masked, in task or interrupt context: save what the ABI says a callee preserves plus the stack pointer into `rtos_pCurrent->ctx`, set `rtos_pCurrent = rtos_pNext`, load its stack pointer and return into it. |
| `RTOS_PORT_INLINE_SCHEDULE` | Optional, define as 1 to inline the scheduler into the blocking path (one call level and frame less per blocking call; worth it on Xtensa, not on the AVR). The interrupt epilogue may likewise call `rtos_kernel_isrTailInline` instead of `rtos_isrTail` to switch from its own frame. |
| `rtos_port_initStack(area, size, entry)` | Prepare a stack so that the first switch into it starts `entry` (always `rtos_taskTrampoline`) with interrupts masked; the trampoline enables them. Return the initial `ctx`. A port whose frames are expensive may instead run the three start steps itself (`rtos_kernel_taskStarting`, `rtos_kernel_taskStartArg`, `rtos_kernel_taskExit` in rtos_kernel.h) from a frameless stub. |
| `rtos_port_startTimer` | Start the tick at `RTOS_CFG_TICK_HZ`; the interrupt calls `rtos_tickFromIsr` and then the ISR tail. |
| `rtos_port_getRunTimeCounter` | Free running time at `RTOS_PORT_RUNTIME_HZ`; interrupts are masked by the caller. |
| `rtos_getTimeUs` | Microseconds since start (public API, but port implemented). |
| `rtos_port_wdtStart(ms)` / `rtos_port_wdtKick` | Hardware watchdog in reset mode, when `RTOS_CFG_WATCHDOG` is used. |

## 2. The interrupt model

Every interrupt that may wake a task runs with the kernel's interrupts masked, calls its
`RTOS_ISR` body, then `rtos_isrTail()`. The tail switches context if the body made a
higher priority task ready. The switch happens on the interrupted task's stack, so the
interrupt frame must be fully restorable after other tasks have run; nothing may live on
an interrupt stack across the tail. On the AVR the wrapper in `port.h` does this in inline
assembler around the body; on Xtensa one assembler entry (`port_context.S`) serves every
level 1 interrupt and a C dispatcher finds the handler.

A port that routes interrupts through a table exposes `rtos_port_attachInterrupt` or
similar; the kernel does not care how a body gets called.

## 3. The context switch

A solicited switch (the task blocks) only needs the registers the ABI says a callee must
preserve, because the kernel called `rtos_port_switchContext` like any other function.
Preemption needs the rest too, and those were already saved by the interrupt entry. On a
CPU with register windows every live window must be spilled to the stack before the stack
pointer changes; see the comment block in `port/xtensa/port_context.S`.

Interrupts are masked throughout. The new task continues after its own call to
`rtos_port_switchContext`, with the interrupt mask it had there, which its critical section
then restores.

## 4. Time

The tick is a periodic interrupt; `rtos_tickFromIsr` does the kernel's bookkeeping. The
run time counter must be monotonic and consistent with the tick (take both from the same
hardware timer, or extend the tick with a cycle counter, as the Xtensa port does) because
`rtos_getCpuLoad` and `rtos_getTaskRunTime` take differences of it.

A port that offers tickless idle (`RTOS_CFG_TICKLESS`, `rtos_port_idleSleepTicks(n)`)
moves the tick compare out by `n` ticks and sleeps. The missed ticks must be counted
(`rtos_tickFromIsr` once each) at the entry of the interrupt that ends the sleep, before
that interrupt's handler runs: the handler may wake a task and the kernel switches to it
at the interrupt's tail, so a catch-up placed after the sleep instruction in the idle task
runs too late and the woken task computes its timeouts from a stale tick (they end at the
catch-up, up to the whole sleep too early; nornCore's tc16 shows it). The Xtensa port
keeps a flag set across `waiti` and counts in `rtos_port_exception`; the compare must be
written in the catch-up so that a pending tick is not counted twice. Bound the sleep so
that the catch-up's signed difference of counter values cannot overflow (the Xtensa port:
2^30 cycles), and never past half the watchdog timeout.

## 4b. Several cores (RTOS_CFG_SMP)

A port that offers SMP sets `RTOS_PORT_CORES` and `RTOS_PORT_SMP 1`, and provides:
`rtos_port_coreId()` (a register read: it is in every access to the current task),
`rtos_port_lockAcquire()` / `rtos_port_lockRelease()` (the one kernel lock, a spinlock;
keep its uncontended path short, it is paid by every critical section of the kernel: the
ESP32 inlines a test-and-set and leaves the line only to spin),
`rtos_port_startCore(core, entry)` (the core runs `entry`, the kernel's idle loop for it,
with its own stack, vectors and the IPI interrupt attached), `rtos_port_ipi(core)` (the
kernel's `rtos_port_ipiHandler` runs on that core in interrupt context), a run time
counter that is one clock for every core, `rtos_port_irqMask()` /
`rtos_port_irqRestore()` (the mask alone, for a read of this core's own state), and
`rtos_port_stallOtherCore()` / `rtos_port_resumeOtherCore()` (halt the other core for an
operation it must not run beside, such as a flash write with the cache off; called inside
a critical section, so that the halted core cannot hold the kernel lock). The ESP32 port
shows two things a second core may need that the first did not: its cache state after
reset (an invalid access flag to clear, an MMU table to zero) and the memory its ROM
start-up uses when the core is released (`RTOS_PORT_ROM_APP_CPU_END`), which nothing
may own across `rtos_start`.

The rule the kernel is built on: on every core, "interrupts masked" and "the lock held"
are the same state. A critical section entered with interrupts enabled takes the lock,
one entered masked is nested and takes nothing; the interrupt entry takes the lock after
the hardware has masked, and releases it when the interrupted context returns, however
late (the tail may have switched tasks in between: the lock is then released by the task
switched to, at its own critical section's end, and taken again by whoever switches back).
`rtos_port_enableInterrupts()` releases, and the boot code of every core takes the lock
before the kernel runs so that the first enable is balanced. The context switch does not
release: the task switched to continues inside its own critical section.

The current task is a per core entry read in two steps, the core and then the entry;
`rtos_kernel_current()` masks interrupts around them, since a migration between the steps
would read another task's entry. Nothing else in the kernel changes for a port: the
scheduler, the IPI handler and the per core idle tasks are the kernel's. The ESP32 port
(port/xtensa, RTOS_CFG_SMP) is the reference; its measurements and open points are in
nornCore's nornInternal/nornCore/measurements/step15-smp.md.

## 5. The make fragment

`port/<arch>/arch.mk` maps each board of the architecture to MCU, clock and flashing
tool, sets `CC`, `CFLAGS`, `ASFLAGS`, `LDFLAGS`, `LDLIBS`, and provides the targets
`image`, `sim`, `upload` and `monitor`. One line in the top Makefile maps the board name
to the architecture. `hal/<arch>/` holds `hal_arch.h` (flash strings, delays),
`gpio_arch.h`, `uart.c` and `board.h` with the pin map and the application timer the
test applications use.

## 6. Bringing it up

1. `applications/hello` without the scheduler: startup, UART and GPIO.
2. tc01: tick, one interrupt source, semaphore from the interrupt, mutex, events.
3. tc02 and tc03: queues, mailbox, notifications, software timers.
4. tc04: the timing figures, into the README.
5. tc05: panic, reset, persistent record, watchdog.
6. tc06: floating point across preemption, if the CPU has an FPU.

The host unit tests (`make host-test`) do not involve the port and should already pass;
they are the reference for what the kernel expects.
