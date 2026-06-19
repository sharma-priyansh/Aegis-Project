# Aegis Kubernetes manifests

Cloud-agnostic, Kubernetes-first (ADR-011). One container image runs every service; the
`command:` selects which (ADR-013).

```bash
docker build -t aegis:latest .
# load image into your cluster (kind load / push to registry), then:
kubectl apply -k deploy/k8s
```

Backing infrastructure (Postgres, Redis, Kafka, Qdrant, OTel Collector) is **not** in these
manifests — deploy it via the official operators/Helm charts or Terraform and point
`aegis-config` at the resulting service DNS names. This keeps the platform portable and the
stateful backends managed by their purpose-built operators (architecture §15).

Safety:
- `networkpolicy.yaml` default-denies ingress except intra-namespace (§13).
- `killswitch.yaml` `AUTONOMY_MODE` drops Aegis to observe/suggest instantly (ADR-019);
  scale `executor` to 0 to hard-stop all remediation.
- All pods run non-root, read-only rootfs, drop ALL caps (hardening, §13).
