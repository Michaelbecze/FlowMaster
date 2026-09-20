#!/bin/sh
# Provisions flow-records.v1 (see contracts/event-flow-record.md).
# Partition key is site_id; partition count gives room for per-site consumer parallelism
# without requiring a repartition for the dev/test topology.
set -eu

rpk topic create flow-records.v1 \
  --brokers broker:9092 \
  --partitions 6 \
  --replicas 1 \
  --topic-config retention.ms=604800000 \
  || rpk topic describe flow-records.v1 --brokers broker:9092
