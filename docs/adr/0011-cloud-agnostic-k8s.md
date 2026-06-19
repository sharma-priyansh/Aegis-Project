# ADR-011 — Cloud-agnostic, Kubernetes-first

**Status:** Accepted · **Date:** 2026-06-19

## Context
Portability and interview generality are goals; the platform also remediates Kubernetes workloads.

## Decision
Target vanilla Kubernetes; provision infra via operators + Terraform/Helm; keep all backends swappable behind
interfaces so the stack runs on EKS/GKE/AKS/on-prem.

## Alternatives considered
Single managed cloud (faster initially, but lock-in and reduced portability/learning value).

## Consequences
(+) Portable, reproducible, vendor-neutral. (−) More upfront infra abstraction; cannot lean on a single
cloud's managed conveniences by default (mitigated by allowing managed backends per ADR-020).
