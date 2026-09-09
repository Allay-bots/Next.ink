# Ce programme est régi par la licence CeCILL soumise au droit français et
# respectant les principes de diffusion des logiciels libres. Vous pouvez
# utiliser, modifier et/ou redistribuer ce programme sous les conditions
# de la licence CeCILL diffusée sur le site "http://www.cecill.info".
#
# This image packages the Next.ink plugin together with the Allay Core
# (https://github.com/Allay-bots/Core), which it needs to run as a
# standalone Discord bot.

# ---- Fetch Allay Core -------------------------------------------------------

FROM docker.io/alpine/git:2.54.0 AS core

# Branch, tag or commit SHA of Allay-bots/Core to build against.
ARG CORE_REF=main

WORKDIR /core
RUN git clone --branch "${CORE_REF}" --depth 1 \
    https://github.com/Allay-bots/Core.git .

# ---- Runtime -----------------------------------------------------------------

FROM docker.io/library/python:3.12-slim-bookworm AS runtime

WORKDIR /app

# git is required at runtime by the LRFutils dependency (via GitPython)
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Allay Core
COPY --from=core /core /app

# This repository, installed as the "next_ink" Allay plugin
COPY . /app/allay/plugins/next_ink

RUN pip install --no-cache-dir -r requirements.txt \
    && if [ -f allay/plugins/next_ink/requirements.txt ]; then \
        pip install --no-cache-dir -r allay/plugins/next_ink/requirements.txt; \
    fi \
    && rm -rf /root/.cache

# Persisted SQLite database and generated config.yaml
VOLUME ["/app/data"]

# Configuration is done through ALLAY_* environment variables (mapped to the
# config.yaml tree, e.g. ALLAY_CORE_TOKEN -> core.token). At minimum you need:
#   ALLAY_CORE_TOKEN=<your Discord bot token>
# See https://github.com/Allay-bots/Core for the full list of options.
ENTRYPOINT ["python", "start.py"]
