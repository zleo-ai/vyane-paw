FROM ghcr.io/astral-sh/uv:0.13.4@sha256:9f130421e930bfbdc563c00740466603f8723158e90297d07957c2294640262b AS uv

FROM rust:1.97-bookworm@sha256:389c1ae98c20fbcadca68a685482749267cec3c90893ae4671c5a37cc894c416

COPY --from=uv /uv /uvx /usr/local/bin/

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates git jq \
    && rm -rf /var/lib/apt/lists/*
