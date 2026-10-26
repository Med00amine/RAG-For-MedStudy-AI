# Deploying to AWS EC2

Single-instance setup: Docker Compose runs the API behind Nginx, with the vector
database on a persistent Docker volume.

```
Internet ──► Nginx :80 (rate limit, proxy) ──► FastAPI :8000 ──► ChromaDB (volume)
                                                    └──────────► Claude API
```

## 1. Launch the instance

- AMI: Ubuntu 24.04 LTS
- Type: `t3.medium` (4 GB RAM is enough for the MiniLM embedding model on CPU)
- Storage: 20 GB gp3
- Security group inbound: SSH (22) from your IP only, HTTP (80) and HTTPS (443) from anywhere

## 2. Install Docker

```bash
ssh -i key.pem ubuntu@<EC2_PUBLIC_IP>
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu && newgrp docker
```

## 3. Deploy

```bash
git clone https://github.com/Med00amine/Rag-project.git && cd Rag-project
cp .env.example .env   # then set ANTHROPIC_API_KEY
docker compose -f docker-compose.prod.yml up -d --build
curl http://localhost/health/ready
```

To update after merging to `master`:

```bash
git pull && docker compose -f docker-compose.prod.yml up -d --build
```

## 4. HTTPS (optional)

Point a domain at the instance (an Elastic IP keeps the address stable), then:

```bash
sudo apt install -y certbot
docker compose -f docker-compose.prod.yml stop nginx
sudo certbot certonly --standalone -d your-domain.com
```

Mount `/etc/letsencrypt` into the Nginx container and add a `listen 443 ssl` server
block that uses the issued certificate.

## 5. Persistent storage

Embeddings live in the `chroma-data` Docker volume, which survives container
rebuilds. To back it up:

```bash
docker run --rm -v rag-project_chroma-data:/data -v $PWD:/backup alpine \
  tar czf /backup/chroma-$(date +%F).tgz -C /data .
```

For durability across instance loss, copy the archive to S3 or snapshot the EBS volume.

## 6. Monitoring basics

- Container health: `docker compose -f docker-compose.prod.yml ps` (uses the image `HEALTHCHECK`)
- Logs (JSON, one line per request with latency): `docker compose -f docker-compose.prod.yml logs -f api`
- Install the CloudWatch agent to ship logs and get CPU/memory/disk alarms
- Point an uptime check (e.g. CloudWatch Synthetics or UptimeRobot) at `/health`
