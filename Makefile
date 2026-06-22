# Build / push / run trader-zex strategy containers.
#
# Build (once, on local or EC2):
#   make docker-build
#   make docker-push  REGISTRY=ghcr.io/you
#
# Run a strategy (interactive, e.g. for testing):
#   make docker-run   STRATEGY=momentum RUNNER=sandbox
#   make docker-run   STRATEGY=pead     RUNNER=backtest
#
# Deploy a strategy (detached, auto-restart, named container):
#   make docker-deploy  STRATEGY=momentum RUNNER=sandbox
#   make docker-stop    STRATEGY=momentum
#   make docker-logs    STRATEGY=momentum
#
# One image, one running container per strategy. Env vars live on the host at:
#   ~/zex/.<strategy>.env    (Fyers creds + strategy-specific settings)
# Secrets are NEVER baked into the image.

IMAGE    ?= trader-zex
REGISTRY ?=
TAG      ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)
NAME     := $(if $(REGISTRY),$(REGISTRY)/,)$(IMAGE)

STRATEGY ?=
RUNNER   ?= sandbox
ARGS     ?=

ENV_FILE  = $(HOME)/zex/.$(STRATEGY).env
CTR_NAME  = zex-$(STRATEGY)

.PHONY: docker-build docker-push docker-run docker-deploy docker-stop docker-logs

docker-build:
	DOCKER_BUILDKIT=1 docker build -t $(NAME):$(TAG) -t $(NAME):latest .

docker-push:
	docker push $(NAME):$(TAG)
	docker push $(NAME):latest

docker-run:
	@test -n "$(STRATEGY)" || (echo "Usage: make docker-run STRATEGY=<name> [RUNNER=sandbox|backtest|live] [ARGS='']" && exit 1)
	docker run --rm -it \
	  $(if $(wildcard $(ENV_FILE)),--env-file $(ENV_FILE),) \
	  $(NAME):$(TAG) -m runners.$(RUNNER) $(STRATEGY) $(ARGS)

docker-deploy:
	@test -n "$(STRATEGY)" || (echo "Usage: make docker-deploy STRATEGY=<name> [RUNNER=sandbox|live]" && exit 1)
	docker run -d --restart unless-stopped \
	  --name $(CTR_NAME) \
	  $(if $(wildcard $(ENV_FILE)),--env-file $(ENV_FILE),) \
	  $(NAME):$(TAG) -m runners.$(RUNNER) $(STRATEGY) $(ARGS)
	@echo "Deployed $(CTR_NAME). Logs: make docker-logs STRATEGY=$(STRATEGY)"

docker-stop:
	@test -n "$(STRATEGY)" || (echo "Usage: make docker-stop STRATEGY=<name>" && exit 1)
	docker stop $(CTR_NAME) && docker rm $(CTR_NAME)

docker-logs:
	@test -n "$(STRATEGY)" || (echo "Usage: make docker-logs STRATEGY=<name>" && exit 1)
	docker logs -f $(CTR_NAME)
