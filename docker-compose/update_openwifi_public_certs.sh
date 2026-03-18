#!/usr/bin/env bash
# update_openwifi_public_certs.sh
# Purpose: Adjust PUBLIC REST cert variables in all *.env files.
# - Uncomments (if commented): RESTAPI_HOST_PORT, RESTAPI_HOST_KEY_PASSWORD, RESTAPI_HOST_{ROOTCA,CERT,KEY}
# - Sets filenames to restapi-public-{ca,cert,key}.pem (keeps $<SERVICE>_ROOT/certs/ prefix)
# - Does NOT modify INTERNAL_* variables.

set -euo pipefail

echo "==> Updating public REST cert settings in all *.env files"
changed_any=0

for f in $(find . -name "*.env"); do
  echo "   -> $f"

  # 1) Uncomment the five public REST lines if they are commented.
  sed -i -E '
    s/^[[:space:]]*#([[:space:]]*RESTAPI_HOST_PORT=)/\1/;
    s/^[[:space:]]*#([[:space:]]*RESTAPI_HOST_KEY_PASSWORD=)/\1/;
    s/^[[:space:]]*#([[:space:]]*RESTAPI_HOST_ROOTCA=)/\1/;
    s/^[[:space:]]*#([[:space:]]*RESTAPI_HOST_CERT=)/\1/;
    s/^[[:space:]]*#([[:space:]]*RESTAPI_HOST_KEY=)/\1/;
  ' "$f"

  # 2) Update only the public cert filenames (keep path prefix intact)
  sed -i -E '
    s|^([[:space:]]*RESTAPI_HOST_ROOTCA=\$[A-Z_]+/certs/)[^[:space:]]+|\1restapi-public-ca.pem|;
    s|^([[:space:]]*RESTAPI_HOST_CERT=\$[A-Z_]+/certs/)[^[:space:]]+|\1restapi-public-cert.pem|;
    s|^([[:space:]]*RESTAPI_HOST_KEY=\$[A-Z_]+/certs/)[^[:space:]]+|\1restapi-public-key.pem|;
  ' "$f"


  changed_any=1

  # 3) Log note if any keys are missing
  for key in RESTAPI_HOST_PORT RESTAPI_HOST_KEY_PASSWORD RESTAPI_HOST_ROOTCA RESTAPI_HOST_CERT RESTAPI_HOST_KEY; do
    if ! grep -qE "^[[:space:]]*$key=" "$f"; then
      echo "      (note) $key not found in $f -- skipped"
    fi
  done
done

if [ "$changed_any" -eq 1 ]; then
  echo "==> Done. Public REST cert paths now use: restapi-public-{cert,key,ca}.pem"
  echo "==> Verify a couple of files, then run: docker-compose down && docker-compose up -d"
else
  echo "==> No *.env files found to update."
fi
