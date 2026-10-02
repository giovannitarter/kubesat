# kubesat

GitOps and provisioning repository for the `kubesat` Kubernetes cluster that will hosts sat services.
Currently Work-in-progress.

The repository contains:

- Terraform code to create a Debian/K3s virtual machine on Proxmox.
- Cloud-init snippets that bootstrap K3s and install Flux.
- Flux/Kustomize manifests for cluster infrastructure and applications.
- SOPS-encrypted Kubernetes and cloud-init secrets.

## Repository layout

```text
.
├── terraform/              # Proxmox VM, cloud-init, and bootstrap secrets
│   ├── cloud-init/          # Cloud-init fragments merged by Terraform
│   ├── main.tf              # VM, downloaded image, cloud-init snippet
│   ├── providers.tf         # Proxmox, SOPS, and cloudinit providers
│   └── vars.tf              # Required Proxmox credentials
├── kube/                   # Flux root for the cluster
│   ├── infrastructure/      # cert-manager, MetalLB, Traefik, Zot, sources
│   ├── apps/                # sentieri web app, database, updater, backups
│   ├── operations/builder/  # image/build automation workloads
│   └── namespaces/          # shared namespaces
├── requirements.txt        # Python tools, mainly pre-commit
└── .pre-commit-config.yaml # YAML and secret checks
```

## Bootstrap flow

1. Terraform connects to Proxmox and creates the `kubesat0` VM.
2. Cloud-init installs base packages, K3s, and bootstrap manifests.
3. K3s installs the Flux Operator and a `FluxInstance`.
4. Flux syncs this repository from `kube/`.
5. Flux applies infrastructure first, then applications and operations workloads.


## Prerequisites

Install the following tools on the workstation used to operate the repo:

- Terraform `>= 1.6`
- `kubectl`
- SOPS with age support
- Python 3 and `pip` for pre-commit hooks
- SSH access to Proxmox and to the Git repository used by Flux

## Secrets and SOPS

Secrets are encrypted with SOPS/age. Export the age key before decrypting or applying encrypted files locally:

```sh
export SOPS_AGE_KEY_FILE=/home/pupillo/kubesat/terraform/age_keypair/key.txt
```

Do not commit decrypted secrets, Terraform state, local plans, or `*.tfvars` files.

## Terraform usage

Create a local secrets tfvars file, for example `terraform/secrets/secrets.tfvars`, with the Proxmox credentials:

```hcl
pve_username = "..."
pve_password = "..."
```

Then run:

```sh
cd terraform
terraform init
terraform plan -var-file=secrets/secrets.tfvars
terraform apply -var-file=secrets/secrets.tfvars
```

Terraform renders the cloud-init configuration from `terraform/cloud-init/*.yaml` and provisions the Proxmox VM.

## Flux and Kubernetes manifests

The Flux root is `kube/kustomization.yaml`. It references these Flux `Kustomization` groups:

- `namespaces`
- `infrastructure`
- `apps`
- `builder`

Useful reconciliation commands:

```sh
flux get kustomizations -A
flux reconcile source git flux-system -n flux-system
flux reconcile kustomization infrastructure -n flux-system --with-source
flux reconcile kustomization apps -n flux-system --with-source
```

Validate manifests locally with:

```sh
kubectl kustomize kube
```

## Local development checks

Install and run pre-commit:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pre-commit install
pre-commit run --all-files
```

The configured hooks check YAML syntax, trailing whitespace, final newlines, large files, and accidental secrets.

## Zot registry notes

Test the in-cluster Zot registry with a temporary pod:

```sh
kubectl run curl-tmp \
  --image=alpine:latest \
  --rm \
  --attach=true \
  -q \
  --restart=Never \
  --command -- \
  sh -c 'apk add --no-cache curl bash >/dev/null && exec curl --fail --silent --show-error --location "http://zot.zot.svc.cluster.local:5000/v2/_catalog"'
```

Copy an image into Zot:

```sh
skopeo copy --dest-tls-verify=false \
  docker://docker.io/library/alpine:latest \
  docker://zot.zot:5000/alpine:latest
```

Or run Skopeo from inside the cluster:

```sh
kubectl run skopeo-tmp -it --rm --image rapidfort/skopeo-ib -- \
  copy --dest-tls-verify=false \
  docker://docker.io/library/alpine:latest \
  docker://zot.zot:5000/alpine:latest
```
