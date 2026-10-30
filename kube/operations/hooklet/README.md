# Hooklet

Hooklet receives signed GitHub push webhooks and creates fresh Kubernetes Jobs from the build Job templates in the `builder` namespace.

## Deployment

Flux reconciles this directory through `operations/hooklet/kflux.yaml`. The workload uses the standard `python:3.12-slim-bookworm` image, installs `requirements.txt` at container startup, and mounts `app.py` and `requirements.txt` from a generated ConfigMap.

Runtime configuration is supplied by the `hooklet-config` ConfigMap. The GitHub HMAC secret is generated in `hooklet.secret.yaml` and encrypted with SOPS.

The public webhook endpoint is:

```text
https://hooklet.ksat.pupillo.org/webhook
```

Configure the GitHub webhook for push events and the decrypted value of `GITHUB_WEBHOOK_SECRET`. Both GitHub content types are supported: `application/json` and `application/x-www-form-urlencoded`. JSON is preferred. To inspect the secret locally with the repository age key configured:

```sh
sops --config /dev/null --decrypt operations/hooklet/hooklet.secret.yaml
```

## Behavior

- Accepts pushes to `giovannitarter/sat_sentieri` on `main`.
- Verifies `X-Hub-Signature-256` against the unmodified request body before processing it.
- Accepts JSON payloads and form-encoded GitHub payloads in the `payload` field.
- Creates one Job per configured template and commit.
- Uses deterministic names, so repeated delivery of the same commit is idempotent while the generated Job exists.
- Reads the templates `build-sentieri-webapp` and `build-aggiorna-sentieri` from the `builder` namespace.
