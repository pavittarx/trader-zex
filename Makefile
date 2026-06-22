# Build / push the trader-zex container.
#
#   make docker-build                         # build <image>:<git-sha> + :latest
#   make docker-push  REGISTRY=ghcr.io/you    # push both tags
#   make docker-run   ARGS="-m runners.list"  # run locally (creds via .env)
#
# Secrets are passed at runtime, never baked into the image.

IMAGE    ?= trader-zex
REGISTRY ?=
TAG      ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)
NAME     := $(if $(REGISTRY),$(REGISTRY)/,)$(IMAGE)
# token lives at the container user's home (~trader = /home/trader)
TOKEN    ?= $(HOME)/.fyers_token.json

.PHONY: docker-build docker-push docker-run

docker-build:
	DOCKER_BUILDKIT=1 docker build -t $(NAME):$(TAG) -t $(NAME):latest .

docker-push: docker-build
	docker push $(NAME):$(TAG)
	docker push $(NAME):latest

docker-run:
	docker run --rm -it \
	  $(if $(wildcard .env),--env-file .env,) \
	  $(if $(wildcard $(TOKEN)),-v $(TOKEN):/home/trader/.fyers_token.json:ro,) \
	  $(NAME):$(TAG) $(ARGS)
