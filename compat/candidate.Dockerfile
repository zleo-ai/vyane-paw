FROM ghcr.io/astral-sh/uv:0.11.28@sha256:5c3ab83183a73c5d319a77009eb425b60d5bb937f339fb7876788ebf567baf48 AS uv

FROM rust:1.97-bookworm@sha256:389c1ae98c20fbcadca68a685482749267cec3c90893ae4671c5a37cc894c416

COPY --from=uv /uv /uvx /usr/local/bin/

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates git jq \
    && rm -rf /var/lib/apt/lists/*
