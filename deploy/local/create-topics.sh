#!/usr/bin/env bash
# Create Aegis Kafka topics with partition counts sized for local dev.
# Partition keys are documented in libs/aegis_common/aegis_common/events.py.
# ADR-002 (event backbone), ADR-009 (incidents.lifecycle keyed by incident_id), ADR-018 (correlation).
set -euo pipefail

BROKER="kafka:9092"
KCMD="/opt/kafka/bin/kafka-topics.sh --bootstrap-server ${BROKER}"

create() {
  local name="$1" partitions="$2"
  ${KCMD} --create --if-not-exists --topic "${name}" \
    --partitions "${partitions}" --replication-factor 1 \
    --config retention.ms="$3" || true
  echo "ensured topic ${name} (${partitions} partitions, retention ${3}ms)"
}

# topic                         partitions  retention(ms)
create "signals.raw"            6           3600000      # 1h hot window; cold tiering handled elsewhere (ADR-020)
create "signals.normalized"     6           3600000
create "incidents.lifecycle"    6           604800000    # 7d; keyed by incident_id (ADR-009)
create "actions.requested"      6           604800000
create "actions.result"         6           604800000
create "knowledge.ingest"       3           604800000
create "notifications.outbound" 3           86400000     # 1d
create "signals.raw.dlq"        3           1209600000   # 14d DLQ
create "incidents.lifecycle.dlq" 3          1209600000

echo "topic bootstrap complete"
