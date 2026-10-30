import copy
import hashlib
import hmac
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("hooklet")

WEBHOOK_SECRET = os.environ["GITHUB_WEBHOOK_SECRET"].encode("utf-8")
EXPECTED_REPOSITORY = os.environ["GITHUB_REPOSITORY"]
EXPECTED_BRANCH = os.getenv("GITHUB_BRANCH", "main")
JOB_NAMESPACE = os.getenv("JOB_NAMESPACE", "builder")
JOB_TEMPLATES = tuple(
    name.strip() for name in os.environ["JOB_TEMPLATES"].split(",") if name.strip()
)
MAX_BODY_BYTES = 1024 * 1024
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

if not JOB_TEMPLATES:
    logger.error("JOB_TEMPLATES must contain at least one Job name")
    raise RuntimeError("JOB_TEMPLATES must contain at least one Job name")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        config.load_incluster_config()
        app.state.batch_api = client.BatchV1Api()
        app.state.api_client = client.ApiClient()
    except Exception:
        logger.exception("Failed to initialize Kubernetes API clients")
        raise
    yield


app = FastAPI(title="Hooklet", lifespan=lifespan)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


def verify_signature(body: bytes, supplied_signature: str | None) -> None:
    if not supplied_signature or not supplied_signature.startswith("sha256="):
        logger.error("Webhook request has a missing or malformed signature")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    expected = "sha256=" + hmac.new(WEBHOOK_SECRET, body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, supplied_signature):
        logger.error("Webhook request signature verification failed")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")


def parse_payload(raw_body: bytes, content_type: str) -> dict:
    try:
        decoded_body = raw_body.decode("utf-8")
        if content_type.split(";", 1)[0].strip().lower() == "application/x-www-form-urlencoded":
            form = parse_qs(decoded_body, keep_blank_values=True, strict_parsing=True)
            payload_values = form.get("payload", [])
            if len(payload_values) != 1:
                raise ValueError("Expected one payload form field")
            decoded_body = payload_values[0]
        payload = json.loads(decoded_body)
    except (UnicodeDecodeError, ValueError):
        logger.error("Webhook payload is not valid JSON or form-encoded JSON")
        raise HTTPException(status_code=400, detail="Invalid payload")

    if not isinstance(payload, dict):
        logger.error("Webhook payload is not a JSON object")
        raise HTTPException(status_code=400, detail="Expected JSON object")
    return payload


def job_name(template_name: str, commit: str) -> str:
    return f"{template_name[:50].rstrip('-')}-{commit[:12]}"


def make_job(api_client: client.ApiClient, source_job, name: str, commit: str) -> dict:
    source = api_client.sanitize_for_serialization(source_job)
    spec = copy.deepcopy(source["spec"])

    # These fields and labels are assigned by the API server and cannot be reused.
    spec.pop("manualSelector", None)
    spec.pop("selector", None)
    spec["ttlSecondsAfterFinished"] = 86400
    pod_metadata = spec.setdefault("template", {}).setdefault("metadata", {})
    pod_metadata.pop("creationTimestamp", None)
    labels = pod_metadata.setdefault("labels", {})
    for key in (
        "controller-uid",
        "job-name",
        "batch.kubernetes.io/controller-uid",
        "batch.kubernetes.io/job-name",
    ):
        labels.pop(key, None)

    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": name,
            "namespace": JOB_NAMESPACE,
            "labels": {
                "app.kubernetes.io/created-by": "hooklet",
                "app.kubernetes.io/instance": source["metadata"]["name"],
            },
            "annotations": {
                "github.com/repository": EXPECTED_REPOSITORY,
                "github.com/sha": commit,
                "hooklet.ksat.pupillo.org/template": source["metadata"]["name"],
            },
        },
        "spec": spec,
    }


def trigger_job(request: Request, template_name: str, commit: str) -> dict:
    name = job_name(template_name, commit)
    try:
        source_job = request.app.state.batch_api.read_namespaced_job(
            name=template_name,
            namespace=JOB_NAMESPACE,
        )
        body = make_job(request.app.state.api_client, source_job, name, commit)
        request.app.state.batch_api.create_namespaced_job(
            namespace=JOB_NAMESPACE,
            body=body,
        )
    except ApiException as exc:
        if exc.status == 404:
            logger.error("Build Job template %s/%s does not exist", JOB_NAMESPACE, template_name)
            raise HTTPException(status_code=503, detail="Build Job template not found")
        if exc.status == 409:
            try:
                existing = request.app.state.batch_api.read_namespaced_job(
                    name=name,
                    namespace=JOB_NAMESPACE,
                )
            except ApiException:
                logger.exception("Unable to verify conflicting Job %s", name)
                raise HTTPException(status_code=503, detail="Unable to verify existing Job")
            annotations = existing.metadata.annotations or {}
            if (
                annotations.get("github.com/sha") != commit
                or annotations.get("hooklet.ksat.pupillo.org/template") != template_name
            ):
                logger.error(
                    "Build Job name collision for %s using template %s",
                    name,
                    template_name,
                )
                raise HTTPException(status_code=409, detail="Build Job name collision")
            logger.info("Duplicate webhook for %s and template %s", commit, template_name)
            return {"status": "already_exists", "job": name}
        logger.exception("Kubernetes API error triggering template %s", template_name)
        raise HTTPException(status_code=503, detail="Unable to create build Job")

    logger.info("Created Job %s from template %s for %s", name, template_name, commit)
    return {"status": "created", "job": name}


@app.post("/webhook")
async def webhook(request: Request):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BODY_BYTES:
            logger.error("Webhook payload exceeds the %d-byte limit", MAX_BODY_BYTES)
            raise HTTPException(status_code=413, detail="Payload too large")
    raw_body = bytes(body)
    verify_signature(raw_body, request.headers.get("x-hub-signature-256"))

    event = request.headers.get("x-github-event", "")
    if event == "ping":
        return {"status": "pong"}
    if event != "push":
        return {"status": "ignored", "reason": "unsupported event"}

    payload = parse_payload(raw_body, request.headers.get("content-type", ""))

    repository_info = payload.get("repository") or {}
    if not isinstance(repository_info, dict):
        logger.error("Webhook payload contains invalid repository information")
        raise HTTPException(status_code=400, detail="Invalid repository")
    repository = repository_info.get("full_name")
    ref = payload.get("ref")
    commit = payload.get("after")

    if repository != EXPECTED_REPOSITORY or ref != f"refs/heads/{EXPECTED_BRANCH}":
        return {"status": "ignored", "reason": "repository or branch mismatch"}
    if payload.get("deleted") is True:
        return {"status": "ignored", "reason": "branch deletion"}
    if not isinstance(commit, str) or not SHA_RE.fullmatch(commit):
        logger.error("Webhook payload contains an invalid commit SHA")
        raise HTTPException(status_code=400, detail="Invalid commit SHA")

    jobs = [trigger_job(request, template_name, commit) for template_name in JOB_TEMPLATES]
    return {"status": "accepted", "namespace": JOB_NAMESPACE, "jobs": jobs}
