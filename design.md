# nornCore design

A small real time kernel for microcontrollers: ATmega328P/2560 and ESP32 today. This
document records how it works and why, so that the choices can be revisited knowingly.

## Scheduling

Fixed priority, preemptive, one task per priority. The task id is its priority, 1 to
`RTOS_CFG_NUM_TASKS`; 0 is the idle task, which is the context that called `rtos_start`.
The scheduler is a bitmask of ready tasks and a highest-bit lookup: O(1), four to twenty
cycles depending on the CPU. There is no time slicing, deliberately: two tasks at the same
priority would need a per priority list and a quantum, and make the scheduling order
depend on history. A task runs until it blocks or a higher priority task becomes ready.

A task becomes ready in three ways: a timeout (the tick interrupt walks the head of a
list sorted by wake-up tick, so a tick costs the same whether 2 or 30 tasks sleep), an
object hand-over (semaphore token, queue item, mailbox item, pool block, event group bits,
written straight into the waiting task's variables by the giver, so the woken task finds
its result without touching the object again), or a notification or event posted to it.

Context switches happen in two places only: in task context when the running task blocks
or makes a higher task ready, and at the end of an interrupt handler (`rtos_isrTail`) when
the handler did. An interrupt handler therefore never switches in the middle; the port
guarantees the interrupt frame survives other tasks running in between.

## Mutual exclusion

The mutex follows the immediate priority ceiling protocol: locking raises the owner to
the mutex's ceiling at once, so no task that could ever want the mutex runs while it is
held, and the owner can never be preempted by a contender. With correct ceilings nobody
blocks on a mutex, a chain of mutexes cannot deadlock, and the worst case blocking time of
a task is one critical section of a lower task. If a ceiling is too low, or the owner
blocks while holding the mutex (allowed but discouraged), contenders fall back to waiting
and get the mutex handed over in priority order; the hand-over raises the new owner
immediately. A lock that would wait follows the chain of owners and panics on a cycle.

The ready mask is indexed by base priority, so a boosted task that is ready but not
running (an owner that blocked while holding, or a waiter that was just handed the
mutex) is not found by the highest ready bit. The kernel keeps a second mask of the
tasks whose effective priority differs from their base priority (rtos_kernel_boostedMask,
maintained by rtos_kernel_setEffPrio); the task picker (pickBoosted in rtos_kernel.c,
shared by the scheduler and the interrupt tail) scans those few tasks only while one of
them other than the running task is ready, and otherwise costs one mask test on top of
the highest bit lookup. The running task's own boost is covered by the fast path's
comparison, so a task that merely holds a mutex schedules at full speed (before this
exclusion the Mega paid about 190 cycles on every semaphore give made under a mutex).
The scan is one iteration per ready boosted task; nested mutexes on one task are one
bit.

The scheduling order is a contract, not an artefact of that scan: tasks are ordered by
the key (effective priority, boosted, base priority), compared lexicographically, where
boosted means the effective priority differs from the base priority. The picker takes
the greatest key, and a ready task preempts the running one only if its key is strictly
greater. So the highest effective priority wins; at an equal effective priority c the
owner raised to the ceiling c runs before the task whose base priority is c (a user of
the mutex, which would block on it, and the protocol promises that never happens with a
correct ceiling), and that owner's wake-up preempts such a task; and two owners boosted
to the same ceiling, which only happens when one of them blocked while holding, run in
base priority order. The base priority is unique, so the order is total. On the fast
path, where no ready task but possibly the current one is boosted, the highest ready
bit above the current task's effective priority is the same order. test/test_tie.c
checks every case against the trace.

Critical sections are short interrupt masks with the previous state restored, nestable;
rtos_enterCritical and rtos_exitCritical are the public pair (inline aliases of the port's,
3 cycles on the Mega), for a counter or a flag that a task and an interrupt share. There
is no kernel lock besides them; every kernel operation runs with interrupts masked
for a bounded number of instructions, which is what gives the interrupt latency figures
in the README. (With RTOS_CFG_SMP the same section also takes the one kernel spinlock,
see "Several cores"; the kernel's source does not change where it enters them.)

## Time

A fixed 1 kHz tick (configurable) drives delays, timeouts, periodic tasks and software
timers. `rtos_waitPeriodic` keeps a period base per task so periods do not drift; a
missed period is counted as an overrun and re-based rather than replayed. Software timers
are a sorted list served by the tick; their callbacks run in the tick interrupt unless the
timer task is configured, in which case they run in a kernel task of chosen priority.

Tickless idle (`RTOS_CFG_TICKLESS`) lets the idle task move the tick timer out to the next
deadline and sleep; the missed ticks are counted in one go on wake-up, at the interrupt's
entry and before its handler runs, so that whatever the interrupt wakes computes its
timeouts from the current tick (a delay started from a stale count would end at the
catch-up, up to the whole sleep too early; tc16 shows it). Only the ESP32 port implements
it; the AVR ports sleep one tick at a time.

Run time statistics are taken at every context switch from a free running counter, so the
per task run times always add up to the elapsed time and `rtos_getCpuLoad` is exact.

## Several cores (RTOS_CFG_SMP)

The default is a kernel per core (AMP, below under Ports): nothing shared, no lock, and
on the ESP32 a message link through a window of memory. One kernel over all the cores is
a build option, RTOS_CFG_SMP, whose default comes from the port: off up to two cores, on
above (RTOS_PORT_SMP_DEFAULT), and off, nothing of it is compiled (the single core images
are byte for byte unchanged, which the build checks). The model keeps everything above:

* **Global fixed priority, one task per priority.** The N highest ranked ready tasks run
  on the N cores. The ready mask is still one; the next task to run is the highest bit of
  ready and not running, and the core that must give way is the one running the lowest
  ranked task. The scheduling key is the same, so the order is total and no two tasks tie.
  No per core queues, no load balancing, no time slicing.
* **One kernel lock.** A critical section is the core's interrupt mask plus one spinlock,
  taken when the mask goes on and released when it goes off, so "interrupts masked" and
  "lock held" are the same state on every core, also through the interrupt entry (the
  hardware masks, the entry takes the lock) and across a context switch. One lock and not
  one per object: the sections are a handful of instructions, the objects are small, and
  one lock has no lock ordering. An ISR body that calls a FromIsr function holds the lock
  too, since a task on another core may be inside the kernel at the same time. Its cost is
  the whole SMP tax: about 30 cycles on the ESP32 per section with a test-and-set whose
  fast path is inline (nornInternal/nornCore/measurements/step16-lock.md), and the interrupt entry latency
  gains the wait for the other core's section, 3 us worst case measured.
* **Switches across cores by IPI.** When a task becomes ready and outranks the lowest
  running task on another core, that core gets an inter processor interrupt; its handler
  sets the switch request and the interrupt tail switches, exactly the one core
  rtos_isrTail. The two switch points of the one core kernel are unchanged; the IPI is one
  more interrupt. Interrupt on core 0 to task running on core 1: 14 us average on the ESP32
  (tc17), most of it not in the lock; where it goes is a follow-up.
* **Per core state.** The current task, the next task and the switch request are arrays
  indexed by the core id (a register read); an idle task per core, outside 1 to
  NUM_TASKS; the interrupt depth and the FPU owner. Core 0 owns the tick and the timed
  list; wake-ups for a task on another core go by IPI; the other cores have no tick.
  Run time statistics need one clock for all cores (the ESP32 uses a timer group at 1
  MHz; its cycle counters are per core and start at different times).
* **Affinity** as a sub option, RTOS_CFG_SMP_AFFINITY: a mask of allowed cores per task,
  one AND in the pick and in the choice of the core that gives way. A task that runs on a
  core its new mask excludes is moved by IPI. It is for a driver whose interrupt lives on
  one core: nornWIFI pins its tasks to core 0, where the radio's interrupts are, and moves
  a caller there for a call into the library.

What breaks, and is the one semantic difference an application sees: **"a lower priority
never runs while I run" is no longer true.** Two tasks of which one is lower may run at
the same instant on two cores. A shared variable that was safe because one side could not
preempt the other needs a mutex or a critical section. In the ceiling protocol the
argument "nothing below the ceiling runs while I hold" holds for the owner's core only; a
task on another core may lock the same mutex, finds it held and waits, and gets the
hand-over in priority order, as a contender does on one core when the ceiling is wrong.
So on several cores a mutex can block even with a correct ceiling, bounded by one critical
section of the owner, and the deadlock check is unchanged. The ceiling itself still
prevents the preemption of the owner by a contender on its own core, which is what keeps
the hand-over simple. Ownership and the waiter lists are under the kernel lock and correct
as before (tc17 runs a ceiling mutex across the cores and counts the violations: none).

Memory ordering: the lock's acquire and release are barriers and everything the kernel
touches is under the lock. The stream buffer's copies outside the section rest on one
writer and one reader whose counters are updated under the lock, so visibility follows.

The host port runs the SMP kernel on N threads with the same discipline, which is where
the invariant "the running tasks are the N highest ranked ready tasks allowed on their
cores" is checked about two million times per test run with N = 2, 3 and 4
(test/test_smp.c); the ESP32 is the two core proof on hardware (tc17). A port that offers
SMP provides the core id, the lock, the start of a core, the IPI and the shared clock
(porting.md 4b). The plan with the measured outcome of every step is nornCore's
nornInternal/nornCore/smp_plan.md.

## The hot path

Every blocking call and every interrupt that wakes a task goes through the same few
functions: make a task ready, pick the highest ready task, account the run time, switch.
Interrupts are masked from the call that decides to switch until the task switched to
leaves its own kernel call, so this path is both the context switch cost and the worst
interrupt latency; tc10 measures it in cycles. Rules that came out of measuring it on the
Mega (496 to 423 cycles per switch, 2026-11-04): the port's run time counter must be an
addition, not a multiplication (the AVR keeps a per tick base); the highest waiter comes
from the bit mask lookup, not a scan; `rtos_assertFailed` is `noreturn` so that the
compiler does not save registers for the failure branch; the run time accounting is
inlined into the two switch sites; the timed list removal is kept out of line because only
timed out or cancelled waits need it. Inlining the scheduler into the blocking path was
tried and rejected on the AVR: the register pressure cost more than the call. Each of
these is a few cycles; what remains is the register save itself (about 105 cycles on the
AVR, more on the ESP32 where the windows are spilled) and the configurable bookkeeping
(run time statistics about 45, assertions about 20).

## Memory

Everything is static: tasks, stacks and objects are declared by the application and
registered with the kernel; nothing is allocated behind the scenes. The memory pool gives
fixed blocks with O(1) alloc and free; the heap (`RTOS_CFG_HEAP`, off by default) is a
first fit allocator with coalescing for the cases that need one, deterministic in that it
does only what the caller asked and reports its statistics.

## Stream buffers

The stream buffer (RTOS_CFG_STREAMS, rtos_stream.c) is the one object for data of
variable length: a ring of bytes, writes and reads of any size, a trigger level that wakes
the reader once enough is in. It is built on a rule rather than a lock: one writer and one
reader at a time. The writer alone moves the tail and alone touches the free part of the
ring; the reader alone moves the head and alone touches the filled part. So the bytes are
copied with interrupts enabled, and the critical section covers only reading the count
that says how much may be copied and updating count and index afterwards, a bounded
handful of instructions whatever the length. The writer may be an interrupt (it is the
single writer then; a task writing to the same stream is the application's mistake, which
cannot be detected); a second task blocking as reader or writer is checked. A reset moves
the head up to the tail and leaves the writer's side alone, so it does not disturb a
write in progress. The copies are plain loops, not memcpy, so that the code can run from
IRAM on the ESP32 without reaching a library function in flash.

## Failure

One path: `rtos_panic`. Assertions, stack overflow (canary at the bottom of every stack,
checked at every switch and tick), the task watchdog, deadlock detection and CPU
exceptions all end there. The record survives a reset, the application's hook can print
or log before the halt or reset, and the next boot reads the record and the hardware's
reset cause. Queues, mailboxes, pools and semaphores count what they drop or overwrite.

## Ports

The kernel talks to hardware through `port.h` only (porting.md). The AVR port is the
simplest: the ISR wrapper and the switch save what the ABI requires and nothing else. The
Xtensa port adds the register window spill, a lazy FPU context, the ROM loader image
format, the PLL and a second kernel instance on the other core (AMP) with a shared
memory link, or, with RTOS_CFG_SMP, one kernel on both cores. The host port runs the
kernel on Linux ucontext for deterministic unit tests with simulated interrupts, which is
where every primitive is specified by its trace; with RTOS_HOST_CORES above one it runs
the SMP kernel on threads.

## Task life cycle

The states are derived from the TCB, not stored: no byte and no store on the hot path.
This is the table the kernel implements, and the contract the dynamic task API
(RTOS_CFG_DYNAMIC_TASKS: rtos_exit, rtos_reapTask, rtos_startTask in rtos_dyntask.c)
builds on.

| State | Predicate | Entered by | Left by |
|---|---|---|---|
| UNUSED | `taskFunc == NULL`; the TCB is in its initial state (rtos_kernel_tcbReset) | rtos_init, a reap | rtos_createTask |
| READY | bit in the ready mask, not the running task | create, wake-up, preemption | pick, block, suspend |
| RUNNING | `rtos_pCurrent` (its bit stays in the ready mask) | pick | block, preemption, return |
| BLOCKED | bit not in the ready mask, `waitKind` says on what, RTOS_TF_IN_TIMED_LIST says if a timeout runs | a blocking call | wake-up, timeout |
| TERMINATED | `waitKind == RTOS_WAIT_TERMINATED`, bit not in the ready mask | the task function returning (rtos_kernel_taskExit), rtos_exit | rtos_reapTask, from another context |

Suspended is a modifier on READY and BLOCKED, not a state: RTOS_TF_SUSPENDED keeps the
task off the ready mask and RTOS_TF_READY_PENDING remembers that a wake-up arrived
meanwhile. rtos_getTaskInfo reports it as RTOS_TASK_SUSPENDED, except for a terminated
task, which is final either way.

Rules, each checked by test/test_lifecycle.c and test/test_dyntask.c:

* A terminated task is deaf: nothing makes it ready again. Every wake-up path tests the
  wait kind (events, event groups), a flag the task no longer has (notifications), a list
  it is no longer in (timeouts, waiter masks) or RTOS_TF_READY_PENDING (resume), and
  rtos_kernel_taskExit never calls rtos_kernel_blockCurrent, so the wait kind is never
  reset. Events and notifications posted at it accumulate harmlessly;
  rtos_broadcastEvents and the stack monitor still visit it; a watchdog monitor on it
  fires, as it should, when the task returned. rtos_exit drops the monitor first: an exit
  on purpose is not a missed check-in. The reap drops it too, so a reused slot never
  inherits one.
* A task must not return while holding a mutex: the owner would stay recorded for ever
  and every later lock would wait with no deadlock panic, since the detector only
  follows tasks blocked on mutexes. rtos_kernel_taskExit checks `effPrio == prio`
  (RTOS_PANIC_ARGUMENT), which catches every mutex with a ceiling above the task's
  priority; a ceiling equal to it is invisible to that check. With RTOS_CFG_DYNAMIC_TASKS
  the TCB counts the mutexes held (one byte, an increment in lock, in the hand-over and in
  unlock) and the exit checks the count as well; the count is under the option because it
  is the one part of the API on the hot path.
* UNUSED means reset, not just `taskFunc == NULL`. rtos_createTask fills only what it
  owns (function, argument, stack, context) and relies on the rest being in the initial
  state, so a reused slot that kept pending events, a suspended flag or a raised
  effective priority would hand them to the new task. rtos_kernel_tcbReset is the one
  place that produces the initial state; rtos_init runs it over every slot and a reap
  runs it over a terminated task.
* The stack of a terminated task is in use until another context runs. The task
  returns into rtos_kernel_taskExit on its own stack, and the switch away from it saves
  the context there (pushes on the AVR, the window spill on the Xtensa). So a task only
  ever terminates itself, and the reap, the reset and the freeing of the stack happen in
  a different context, after the switch: the idle task or the creator, never the dying
  task, and never a task that is READY, BLOCKED or RUNNING. The host port also has to
  release the ucontext and the stack it allocated in rtos_port_initStack.
* Creating a task while the scheduler runs needs a critical section around
  rtos_createTask, a schedule after it from task context (the new task may be the
  highest) and the switch request from an ISR; the stack fill loop under
  RTOS_CFG_STACK_CHECK makes creation from an ISR a bad idea. rtos_createTask itself
  stays as it is; rtos_startTask wraps it: it refuses an interrupt caller, a slot in use
  and a bad argument with an error code, then creates under the critical section and
  schedules.

## What is deliberately absent

Time slicing (see above), killing a task from outside (the source of most use-after-free
bugs in kernels: the victim may hold a mutex, sit in a waiter list or be mid hand-over;
a task that should stop is told with a notification or an event and calls rtos_exit
itself, and only the terminated slot is reaped), priority change at run time (the id is
the priority, which is what keeps the ready mask and the ceiling protocol simple), a
kernel-owned stack allocator (the application owns every stack, also one it lends to a
dynamic task), priority inheritance (the ceiling protocol is simpler and has better
bounds), recursive mutexes (an owner count and a check in every lock, and it hides the
design errors the ceiling protocol otherwise exposes), SMP by default (the two ESP32
cores run two independent kernels: no locks in the scheduler, no cache coherence
questions, and a message link that is as fast as a shared memory copy; one kernel over
the cores is the option above, meant for the ports with more cores), per core run queues
and load balancing (the global pick is bit operations and keeps the scheduling order a
contract).
