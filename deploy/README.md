# Deploying to a server

How to run the KickPick backend on a Linux server with a public HTTPS address and the database already filled with
data. For whoever sets up the server; it takes about 15 minutes.

## What you need

- A Linux server with Docker Engine and Compose v2, about 2 GB of free RAM and 5 GB of disk. ARM64 (Oracle Ampere)
  and x86_64 both work.
- Ports 80 and 443 reachable from the internet (Caddy gets the HTTPS certificate through them).
- From the project owner: read access to the GitHub repository, and `kickpick-deploy.tar` with the database dump
  (`kickpick.dump`, ~100 MB) and the prediction model (`models/`).

## 1. Check that FotMob answers this server

```bash
curl -s -o /dev/null -w "%{http_code}\n" "https://www.fotmob.com/api/data/matches?date=$(date +%Y%m%d)&timezone=UTC"
```

`200` is good. Anything else (`403`, a timeout) means FotMob blocks this server's address: stop here and tell the
owner, since the collector could not update scores.

## 2. Open ports 80 and 443

On Oracle Cloud this takes two steps.

1. In the console: Networking → Virtual cloud networks → the instance's VCN → Security Lists → Default Security List →
   Add Ingress Rules: source `0.0.0.0/0`, TCP, destination port `80`; then the same for `443`.
2. On the server, the image's own firewall. Ubuntu images:

   ```bash
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
   sudo netfilter-persistent save
   ```

   Oracle Linux images:

   ```bash
   sudo firewall-cmd --permanent --add-service=http --add-service=https && sudo firewall-cmd --reload
   ```

Never open 5432, 8000 or 8001: the database, the gateway and the admin pages stay on localhost.

If 80 and 443 are already used by your own reverse proxy, see [Behind your own reverse proxy](#behind-your-own-reverse-proxy).

## 3. Get the code and the data

```bash
git clone https://github.com/MaksymShupeikin/kickpick.git && cd kickpick
tar -xf ~/kickpick-deploy.tar -C ~                       # → ~/kickpick-deploy/
mkdir -p backend/artifacts/models && cp -R ~/kickpick-deploy/models/* backend/artifacts/models/
python3 backend/tools/init_secrets.py                    # creates .secrets/ with new random passwords
```

## 4. Choose the public address

Create `.env` in the repository root:

```bash
PUBLIC_HOST=1-2-3-4.sslip.io
COMPOSE_PROFILES=public,ml
```

- `PUBLIC_HOST` is the address the app will use. Without a domain, take the server's public IP with dashes plus
  `.sslip.io` (IP `140.238.1.2` → `140-238-1-2.sslip.io`): it resolves to that IP and needs no setup. With a domain,
  use a subdomain whose A record points at the server, for example `kickpick.example.com`.
- `COMPOSE_PROFILES`: `public` starts Caddy (HTTPS), `ml` starts the prediction service. Drop `ml` to run without
  predictions.
- If 8000, 8001 or 5432 are taken on this server, add `API_PORT=`, `ADMIN_PORT=` or `DB_PORT=` with free ports; they
  are only bound to localhost.

## 5. Load the database and start

```bash
deploy/restore.sh ~/kickpick-deploy/kickpick.dump        # once, before the first start
docker compose up -d --build
docker compose ps
curl -s -o /dev/null -w "%{http_code}\n" "https://$(grep PUBLIC_HOST .env | cut -d= -f2)/competitions"
```

`restore.sh` prints how many matches and players it loaded, and refuses to run over a database that already has
tables. If the stack was already started once without the dump, `docker compose down -v` deletes that empty database
first (only do this on a fresh install).

The last command should print `200`. The first HTTPS request can take a few seconds while Caddy gets the certificate.

## 6. Send the address to the owner

Send `https://<PUBLIC_HOST>` to the owner: it goes into `API_BASE_URL[sdk=iphoneos*]` in `ios/project.yml`, and the
app is rebuilt with it.

## Running it

| Task | Command |
|---|---|
| What is collected | `docker compose exec collector python -m kickpick.collector status` |
| Logs | `docker compose logs -f collector` (or `api`, `gateway`, `caddy`) |
| Update to the latest code | `git pull && docker compose up -d --build` |
| Back up the database | `docker compose exec -T db pg_dump -U kickpick -d kickpick -Fc > kickpick-$(date +%F).dump` |
| Admin dashboard | `ssh -L 8001:127.0.0.1:8001 <server>`, then open `http://localhost:8001/dashboard` |

The collector picks up from the dump's date by itself: within an hour it syncs the current seasons and fetches the
matches played since.

## Behind your own reverse proxy

If ports 80 and 443 already belong to your own Nginx, Caddy or Traefik, leave `public` out of `COMPOSE_PROFILES` and
proxy the host to `http://127.0.0.1:8000` (or your `API_PORT`). Your proxy must set `X-Forwarded-For` to the client's
address. Then let the gateway trust it: send one request through your proxy, read the address it arrived from
(the first field of the line):

```bash
docker compose logs --tail 5 gateway
```

and in `deploy/nginx/trusted-proxies.conf` replace `172.31.255.2` with that address, then
`docker compose restart gateway`. Without this, every user shares one per-IP rate limit.
