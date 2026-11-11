# nornDocs

The public documentation of nornRTOS: what a user of the system needs, independent of
which module the text happens to describe. The sources live in the nornRTOS tree
(https://github.com/NornRTOS/nornRTOS, with nornCore, nornNET, nornWIFI and nornHTTP
as submodules); each repository keeps its own README for layout, build and status, and
its `doc/` for the material that belongs to its development (plans, audits,
measurements). What is for using the system is here.

## Where to start

1. **Build and run an example.** The nornRTOS README: `make APP=hello BOARD=esp32`,
   the application directory (app.mk, rtos_config.h), the boards (boards/esp32,
   boards/avr).
2. **Configure the kernel.** The nornCore README has the three measured configurations
   to start from (UNO, Mega 2560, ESP32), the primitives and the timing tables;
   config/rtos_config.template.h in nornCore lists every option.
3. **Understand the model.** [design.md](design.md): scheduling, the priority ceiling
   protocol, time, memory, failure, the task life cycle, and what is absent on purpose.
4. **Read the user guide.** `make guide` builds guide/nornRTOS-UserGuide.pdf (needs
   TeX Live with pgfplots, listings and latexmk). It is the one document that covers the
   whole system: concepts, configuration, how to use each primitive, the API, nornNET
   and nornWIFI, the measurements as graphs, and the test suite.
5. **The API.** `make api` generates the reference from kernel/rtos.h, the HAL
   headers and nornHTTP's norn_http.h into api/html (doxygen 1.9 or later; the nornRTOS checkout is expected next
   to this one, or NORNRTOS=path).
6. **Networking, WiFi and HTTP.** Chapter 8 of the user guide; the nornNET README
   ("Using it in a nornOS application"), the nornWIFI README ("Using it") and the
   nornHTTP README for the details that are still only there.
7. **A new CPU or board.** [porting.md](porting.md): the port interface, the interrupt
   model, the context switch, the make fragment, bringing it up.

## Documents

| File | What |
|---|---|
| guide/ | The user guide (LaTeX): concepts, configuration, the primitives, the API reference, networking, measurements with graphs, the tests; `make guide` builds the PDF, `make data` refreshes the graph data from nornCore's measurements |
| design.md | How the kernel works and why: the contract an application can rely on |
| porting.md | Porting nornCore to a new architecture |
| Doxyfile, Makefile | The API reference, generated from the sources |
| LICENSE.md | Business Source License 1.1 with Tenforward AB's Additional Use Grant |

## Licence

Business Source License 1.1 with the Additional Use Grant in LICENSE.md, the same as
the sources.
