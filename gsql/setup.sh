#!/usr/bin/env bash
# Installs the PDS Trust Layer graph schema + queries into a running
# TigerGraph instance (Community edition works fine for this scale).
#
# Usage: ./setup.sh [gsql-host]
# Default host: localhost

HOST="${1:-localhost}"

echo "Creating schema on $HOST ..."
gsql --ip "$HOST" gsql/schema.gsql

echo "Installing queries on $HOST ..."
gsql --ip "$HOST" gsql/queries.gsql
gsql --ip "$HOST" "USE GRAPH PDS_TrustGraph; INSTALL QUERY ALL"

echo "Done. Verify with: gsql --ip $HOST 'USE GRAPH PDS_TrustGraph; LS'"
