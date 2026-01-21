#!/usr/bin/env bash
set -e

# Create indices for NyaaV3.
# Allow configuring the base URL via ES_URL / ES_HOSTS.
ES_URL="${ES_URL:-${ES_HOSTS:-http://elasticsearch:9200}}"
# If ES_HOSTS is a python-ish list or comma separated, keep it simple and just take the first token
ES_URL="${ES_URL%%,*}"
ES_URL="${ES_URL#[}"
ES_URL="${ES_URL%]}"
ES_URL="${ES_URL#\'}"
ES_URL="${ES_URL%\'}"

echo "Creating Elasticsearch indices at ${ES_URL}"

curl -sS -XPUT "${ES_URL}/nyaa?pretty" -H"Content-Type: application/yaml" --data-binary @es_mapping.yml
curl -sS -XPUT "${ES_URL}/sukebei?pretty" -H"Content-Type: application/yaml" --data-binary @es_mapping.yml
