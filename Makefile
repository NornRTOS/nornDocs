# nornDocs: the public documentation of nornRTOS.
#   make api      generate the API reference from the nornRTOS sources into api/html
#   make data     regenerate the user guide's graph data from nornCore's doc/measurements
#   make guide    build guide/nornRTOS-UserGuide.pdf (latexmk, pdflatex, pgfplots)
#   make clean
NORNRTOS ?= ../nornRTOS
export NORNRTOS

.PHONY: api data guide clean
api:
	@test -f $(NORNRTOS)/modules/nornCore/kernel/rtos.h || \
	  { echo "nornRTOS not found at $(NORNRTOS); set NORNRTOS=<path>"; exit 1; }
	doxygen Doxyfile
	@echo "api/html/index.html"

data:
	python3 tools/measurements_to_csv.py $(NORNRTOS) guide/data

guide:
	cd guide && latexmk -pdf -interaction=nonstopmode -halt-on-error nornRTOS-UserGuide.tex
	@echo "guide/nornRTOS-UserGuide.pdf"

clean:
	rm -rf api
	cd guide && latexmk -C nornRTOS-UserGuide.tex 2>/dev/null; rm -f guide/*.idx guide/*.ind guide/*.ilg
