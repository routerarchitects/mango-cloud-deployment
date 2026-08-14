# Mango Cloud

**Open-source OpenLAN/OpenWiFi cloud platform for managed Wi-Fi and connectivity operations.**

[Mango Cloud](https://www.mangowifi.cloud/) is developed by [Router Architects](https://www.routerarchitects.com/) to help ISPs, MSPs, OEMs, and system integrators build and operate open, extensible managed-connectivity platforms.

Mango Cloud provides a common cloud operations layer across OpenWiFi access points and OpenLAN connectivity infrastructure, with services for device provisioning, monitoring, firmware management, subscriber operations, topology, analytics, security, and operational workflows.

> **Own the platform. Avoid closed vendor lock-in. Extend it for your own services and workflows.**

## Why Mango Cloud?

Mango Cloud is designed for providers that want the flexibility of open networking without having to assemble and operate disconnected components themselves.

Key capabilities include:

* **Device lifecycle management** — provisioning, onboarding, configuration, monitoring, firmware management, and diagnostics
* **OpenWiFi management** — cloud management for compatible OpenWiFi access points and CPE
* **OpenLAN integration** — an open connectivity architecture spanning Wi-Fi, switching, and gateway infrastructure
* **Subscriber operations** — subscriber onboarding, device assignment, service lifecycle, and self-service workflows
* **Multi-tenant operations** — operators, tenants, locations, venues, hierarchies, and role-based workflows
* **Topology and analytics** — network topology, telemetry, operational analytics, and troubleshooting visibility
* **Open APIs** — API-driven integrations with OSS/BSS, billing, captive portals, CRM, support systems, and provider-specific workflows
* **Self-hosted deployment** — deploy and operate Mango Cloud using your own infrastructure and Docker Compose

## Managed Connectivity Use Cases

Mango Cloud can be used as the cloud operations layer for:

* Residential Wi-Fi
* MDU Wi-Fi
* Hospitality Wi-Fi
* Public Wi-Fi and hotspots
* MSP-managed enterprise Wi-Fi
* Edge IoT connectivity deployments
## Mango Cloud Architecture

![Mango Cloud component architecture](./mango-cloud-components.drawio.png)

The Mango Cloud deployment combines OpenWiFi cloud services with Router Architects-developed platform components and operational workflows.

The current Docker Compose stack includes:

| Component          | Role                                                              |
| ------------------ | ----------------------------------------------------------------- |
| `owgw`             | uCentral gateway and access-point communication                   |
| `owgw-ui`          | Wi-Fi controller user interface                                   |
| `owprov`           | Provisioning, inventory, subscriber, entity, and venue management |
| `owprov-ui`        | Provisioning and operations user interface                        |
| `owsec`            | Security and authentication services                              |
| `owfms`            | Firmware lifecycle management                                     |
| `owanalytics`      | Wi-Fi and network analytics                                       |
| `owsub`            | Subscriber self-service workflows                                 |
| `network-topology` | Network topology and connectivity visibility                      |
| `kafka`            | Inter-service messaging                                           |
| `postgresql`       | Persistent platform data                                          |

## Open-Source Components

Mango Cloud is built from public component repositories maintained under the Router Architects GitHub organization.

* [uCentral Gateway — OWGW](https://github.com/routerarchitects/ra-wlan-cloud-ucentralgw)
* [Wi-Fi Controller UI — OWGW UI](https://github.com/routerarchitects/ra-wlan-cloud-ucentralgw-ui)
* [Provisioning Service — OWPROV](https://github.com/routerarchitects/ra-wlan-cloud-owprov)
* [Provisioning UI — OWPROV UI](https://github.com/routerarchitects/ra-wlan-cloud-owprov-ui)
* [Analytics Service](https://github.com/routerarchitects/ra-wlan-cloud-analytics)
* [Security Service — OWSEC](https://github.com/routerarchitects/ra-wlan-cloud-ucentralsec)
* [Firmware Management Service — OWFMS](https://github.com/routerarchitects/ra-wlan-cloud-ucentralfms)
* [Subscriber Portal](https://github.com/routerarchitects/ra-wlan-cloud-userportal)
* [Network Topology Service](https://github.com/routerarchitects/ra-openlan-nw-topology)

Each component can be cloned and built independently, or the complete platform can be deployed using this repository.

## Deployment

This repository provides the Docker Compose configuration required to deploy the Mango Cloud stack.

It includes support for:

* Local development deployments
* Remote/cloud deployments
* Self-signed certificates for development
* Public certificates using Let's Encrypt
* Custom certificates
* Building and using your own Mango Cloud component images

For production deployments, review all certificate, credential, networking, and infrastructure settings before exposing the platform publicly.

## Learn More

* **Mango Cloud:** https://www.mangowifi.cloud/
* **Router Architects:** https://www.routerarchitects.com/
* **GitHub Organization:** https://github.com/routerarchitects

---
## Local Setup

### Clone repo
```
mkdir openwifi-sdk
cd openwifi-sdk
git clone https://github.com/routerarchitects/mango-cloud-deployment.git
cd mango-cloud-deployment/docker-compose/
git checkout release/v1.0.0
```

### Install Docker and Docker Compose
```
sudo apt install docker.io docker-compose -y
sudo usermod -aG docker $USER
newgrp docker
sudo chown -R $USER:$USER .
```

### Set up image configuration in owfms.env
These settings are used by owgw-ui and owprov-ui to display the device group and device type, and they are also required for firmware upgrades.

Update the firmware bucket settings in owfms.env. This bucket should contain all firmware images and the metadata file required for device upgrades. After completing the setup, verify that the device type and device group are displayed correctly in both owgw-ui and owprov-ui.
```
S3_BUCKETNAME=<firmware-bucket-name>
S3_REGION=<aws-region>
S3_SECRET=<s3-secret-key>
S3_KEY=<s3-access-key>
S3_BUCKET_URI=s3.<aws-region>.amazonaws.com/<firmware-bucket-name>
FIRMWAREDB_MAXAGE=365  # Firmware image expiry time in days. Default value is 90.
```

### Set up email verification in owsec.env


The Security service (owsec) uses an email account to send subscriber verification emails. To enable this feature, configure the email settings in owsec.env.

If you are using Gmail, create an App Password for the email account that will be used to send verification emails. You can generate it from:

[Google App Passwords](https://myaccount.google.com/apppasswords)

After generating the App Password, update the following values in owsec.env:

```
MAILER_ENABLED=true
MAILER_HOSTNAME=smtp.gmail.com
MAILER_USERNAME=<Email used to create the app-password>
MAILER_PASSWORD=<app-password>
MAILER_SENDER=Sender Name <sender email>
MAILER_PORT=587
MAILER_TEMPLATES=$OWSEC_ROOT/templates
```
### Update certificates
Certificates are required for secure communication between devices and the controller (owgw). A common CA/Issuer must be used to generate both the controller (server) certificates and the device certificates.

Use the guide available in [mango_cloud_cert_generation](https://github.com/routerarchitects/mango_cloud_cert_generation)
 to generate and transfer the required certificates.

After generating the certificates, update the following files in the certs/ directory with the newly generated certificates:
```
clientcas.pem
issuer.pem
root.pem
websocket-cert.pem
websocket-key.pem
```

### Start OpenWiFi Docker Stack (Local)
```
docker-compose down --remove-orphans
docker-compose up -d
```

### Add local hostname mapping
The local UI URLs use `openwifi.wlan.local`, so add it to `/etc/hosts` on your machine:
```
echo "127.0.0.1 openwifi.wlan.local" | sudo tee -a /etc/hosts
```

### Access Web UI 
```
Controller:
URL: https://openwifi.wlan.local

Provisioning:
URL: https://openwifi.wlan.local:8443

Credentials:
Username: tip@ucentral.com
Password: openwifi
```

---
## Remote Setup
- Create an EC2 Instance
- Choose an instance with at least 8 GB RAM
- Use Ubuntu 22.04.3 LTS or later
- Before starting the remote setup, first complete the local setup steps: clone the repository, install Docker, and configure owfms.env and owsec.env.

### Update security group
In the Security Group, allow these inbound ports:

```
TCP: 22, 80, 443, 5000, 5912, 5913, 8443, 15002, 16001, 16002, 16003, 16004, 16005, 16006, 16007, 16009
```


### Initial Setup
SSH into your instance:
```
ssh -i <your-key.pem> ubuntu@<EC2-PUBLIC-IP>
```


Update packages and install tools:
```
sudo apt update
sudo apt install net-tools certbot -y
```

Choose the public domain name that will be used to access Mango Cloud. Enter only the hostname, without `https://`.
Run:
```
PUBLIC_HOSTNAME=<your-public-domain eg. mangocloud.com>  
echo "$PUBLIC_HOSTNAME"
```

Run
```
bash ./update_openwifi_public_certs.sh
```

Update Hostname References:

Replace all instances of openwifi.wlan.local with your domain:
```
sudo find . -type f -name "*.env" -exec sed -i.bak "s|openwifi\.wlan\.local|$PUBLIC_HOSTNAME|g" {} +
```

Run certbot command:
```
sudo certbot certonly --standalone \
  --key-type rsa \
  --cert-name $PUBLIC_HOSTNAME \
  -d $PUBLIC_HOSTNAME \
  -m your-email@example.com \
  --agree-tos --non-interactive --force-renewal
```
Certs will be created in:
```
/etc/letsencrypt/live/<PUBLIC_HOSTNAME>/
```
If the Let’s Encrypt certificate is generated successfully, run the following commands:

```
cd /home/ubuntu/openwifi-sdk/mango-cloud-deployment/docker-compose

sudo cp /etc/letsencrypt/live/$PUBLIC_HOSTNAME/privkey.pem   certs/restapi-public-key.pem

sudo cp /etc/letsencrypt/live/$PUBLIC_HOSTNAME/fullchain.pem certs/restapi-public-cert.pem

sudo cp /etc/letsencrypt/live/$PUBLIC_HOSTNAME/chain.pem     certs/restapi-public-ca.pem

sudo chown ubuntu:ubuntu certs/restapi-public-*.pem
sudo chmod 664 certs/restapi-public-*.pem
ls -l certs/
```

### Update docker-compose.yml for Remote Setup
For remote setup, after generating the public certificates, update the certificate mount paths in docker-compose.yml for both owgw-ui and owprov-ui.

Replace:
```
- "./certs/restapi-cert.pem:/etc/nginx/restapi-cert.pem"
- "./certs/restapi-key.pem:/etc/nginx/restapi-key.pem"
```
with:
```
- "./certs/restapi-public-cert.pem:/etc/nginx/restapi-cert.pem"
- "./certs/restapi-public-key.pem:/etc/nginx/restapi-key.pem"
```
### Start OpenWiFi Docker Stack
```
docker-compose down --remove-orphans
docker-compose up -d
```

### Access Web UI 
```
Controller:
URL: https://<PUBLIC_HOSTNAME>

Provisioning:
URL: https://<PUBLIC_HOSTNAME>:8443

Credentials:
Username: tip@ucentral.com
Password: openwifi
```


### Automated Let’s Encrypt Certificate Renewal
#### Create the Deploy Hook Script

Note: <PUBLIC_HOSTNAME> in the script below is a placeholder and must be replaced with your actual hostname.

Create the file:
```
sudo tee /usr/local/bin/openwifi-sdk-renew-certs-hook.sh > /dev/null << 'EOF'
#!/bin/bash

LOG_FILE="/var/log/letsencrypt-renewal.log"
CERT_DIR="/home/ubuntu/openwifi-sdk/mango-cloud-deployment/docker-compose/certs"
LE_DIR="/etc/letsencrypt/live/<PUBLIC_HOSTNAME>"

echo "[openwifi-cert-renewal] Certificate renewed at $(date)" > "$LOG_FILE"

cp "$LE_DIR/fullchain.pem" "$CERT_DIR/restapi-public-cert.pem"
cp "$LE_DIR/privkey.pem"   "$CERT_DIR/restapi-public-key.pem"
cp "$LE_DIR/chain.pem"     "$CERT_DIR/restapi-public-ca.pem"

chown ubuntu:ubuntu -R "$CERT_DIR"/restapi-public*.pem
chmod 664 "$CERT_DIR"/restapi-public*.pem

cd /home/ubuntu/openwifi-sdk/mango-cloud-deployment/docker-compose || exit

/usr/bin/docker-compose down
/usr/bin/docker-compose up -d

echo "[openwifi-cert-renewal] Docker Compose restarted at $(date)" >> "$LOG_FILE"
EOF
```

Make it executable:
```
sudo chmod +x /usr/local/bin/openwifi-sdk-renew-certs-hook.sh
```

#### Create the Renewal Wrapper Script

This script checks whether the current certificate will expire within the next 48 hours. If yes, it forces renewal and then runs the deploy hook.
```
sudo tee /usr/local/bin/openwifi-sdk-renew-certs.sh > /dev/null << 'EOF'
#!/bin/bash
set -euo pipefail

CERT_FILE="/etc/letsencrypt/live/<PUBLIC_HOSTNAME>/cert.pem"
HOOK_SCRIPT="/usr/local/bin/openwifi-sdk-renew-certs-hook.sh"
LOG_FILE="/var/log/letsencrypt-renewal.log"

if ! openssl x509 -checkend 172800 -noout -in "$CERT_FILE"; then
  echo "[openwifi-cert-renewal] Certificate expires in less than 48 hours. Renewing at $(date)" >> "$LOG_FILE"
  certbot renew --cert-name <PUBLIC_HOSTNAME> --force-renewal --quiet
  "$HOOK_SCRIPT"
else
  echo "[openwifi-cert-renewal] Certificate is still valid for more than 48 hours. No renewal needed at $(date)" >> "$LOG_FILE"
fi
EOF
```
Make it executable:
```
sudo chmod +x /usr/local/bin/openwifi-sdk-renew-certs.sh
```
#### Set up Cron Job for Automatic Renewal Checks

Edit the root crontab:
```
sudo crontab -e
```

Add this entry:
```
17 */12 * * * /usr/local/bin/openwifi-sdk-renew-certs.sh
```
This checks the certificate every 12 hours and renews it only when less than 48 hours remain before expiry.

Check the crontab:
```
sudo crontab -l
```
#### Test the Renewal Logic

To test whether the script runs correctly:
```
sudo bash /usr/local/bin/openwifi-sdk-renew-certs.sh
```
To verify the current certificate expiry date:
```
sudo openssl x509 -enddate -noout -in /etc/letsencrypt/live/<PUBLIC_HOSTNAME>/cert.pem
```
