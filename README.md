# kubesat


Kubernetes flux config respository for sentieri.sat.tn.it
```
export SOPS_AGE_KEY_FILE=/home/pupillo/kubesat/terraform/age_keypair/key.txt
```


Testing zot
```
kubectl run curl-tmp   --image=alpine:latest   --rm   --attach=true   -q   --restart=Never   --command --   sh -c '
    apk add --no-cache curl bash >/dev/null &&
    exec curl --fail --silent --show-error --location "http://zot.zot.svc.cluster.local:5000/v2/_catalog"'
```

Copying to zot an image from docker registry:
```
skopeo copy --dest-tls-verify=false  docker://docker.io/library/alpine:latest   docker://zot.zot:5000/alpine:latest
kubectl run skopeo-tmp -it --rm --image rapidfort/skopeo-ib -- copy --dest-tls-verify=false  docker://docker.io/library/alpine:latest   docker://zot.zot:5000/alpine:latest
```
