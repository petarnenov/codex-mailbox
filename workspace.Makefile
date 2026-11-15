# codex-mailbox entrypoint: the dashboard is a built-in workspace component.
.DEFAULT_GOAL := help
.NOTPARALLEL:
.PHONY: help setup doctor doctor-deps up start down stop restart build logs status health demo tools test lint check coverage
help setup doctor doctor-deps up start down stop restart build logs status health demo tools test lint check coverage:
	+@$(MAKE) --no-print-directory -C dashboard $@
