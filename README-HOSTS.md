# Custom DNS / Hosts Configuration

## Problem
When you have custom DNS entries in your local `/etc/hosts` file (e.g., `192.168.1.100 myapp.local`), the proxy container can't resolve them because it has its own isolated `/etc/hosts`.

## Solution: Using `extra_hosts` in docker-compose.yml

### Method 1: Manual Configuration (Recommended)

Edit `docker-compose.yml` and uncomment/add your custom DNS entries:

```yaml
extra_hosts:
  - "myapp.local:192.168.1.100"
  - "api.dev:10.0.0.50"
  - "test.local:127.0.0.1"
```

Then restart the container:
```bash
docker-compose down
docker-compose up -d
```

### Method 2: Quick Add Without Editing Files

Use docker-compose command-line override:
```bash
docker-compose down
docker-compose up -d --extra_hosts "myapp.local:192.168.1.100"
```

### Method 3: Sync Your Entire /etc/hosts File

If you want to mirror your host machine's `/etc/hosts` in the container:

1. Create a script to extract your custom entries:
```bash
# Extract non-system entries from /etc/hosts
grep -v "^127.0.0.1\|^::1\|^255.255.255.255\|^#" /etc/hosts | grep -v "^$" > custom-hosts.txt
```

2. Mount it in docker-compose.yml:
```yaml
volumes:
  - ./custom-hosts.txt:/etc/hosts.custom:ro
```

3. Add a startup script to merge them (more complex, use Method 1 instead).

## Example Configuration

For your use case (local DNS names), here's a typical setup:

```yaml
services:
  web-burp:
    # ... other config ...
    extra_hosts:
      - "myapp.local:192.168.1.100"
      - "staging.myapp.local:192.168.1.101"
      - "db.local:192.168.1.50"
```

## Verification

After adding entries and restarting, verify they're working:

```bash
# Check /etc/hosts inside container
docker exec web-burp cat /etc/hosts

# Test DNS resolution
docker exec web-burp nslookup myapp.local

# Test through the proxy
curl -x http://localhost:8080 http://myapp.local/
```

## Notes

- **Format**: `"hostname:ip_address"` - quotes are important
- **Restart Required**: Changes to `extra_hosts` require `docker-compose down && up`
- **No Wildcards**: Each hostname must be explicitly listed
- **IPv4 & IPv6**: Both supported (e.g., `"myapp.local:fe80::1"`)

## Troubleshooting

**"Still getting 502"**: 
- Verify the IP is correct and accessible from inside container
- Check if the service is actually running on that IP
- Test direct connection: `docker exec web-burp curl http://192.168.1.100/`

**"Name doesn't resolve"**:
- Ensure you used `docker-compose down` (not just restart)
- Check syntax: colon separates hostname and IP, no spaces
- Verify entry in container: `docker exec web-burp cat /etc/hosts`
