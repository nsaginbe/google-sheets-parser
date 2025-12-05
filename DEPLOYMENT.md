# Deployment Guide for Digital Ocean Droplet

This guide walks you through deploying the Google Sheets Parser API on a Digital Ocean Droplet.

## Prerequisites

1. A Digital Ocean account
2. A domain name (optional, but recommended)
3. Your Google Service Account credentials file (`key.json`)

## Step 1: Create a Digital Ocean Droplet

1. Log in to [Digital Ocean](https://cloud.digitalocean.com/)
2. Click "Create" → "Droplet"
3. Choose:
   - **Image**: Ubuntu 22.04 (LTS)
   - **Plan**: Basic (minimum 1GB RAM, 1 vCPU)
   - **Region**: Choose closest to your users
   - **Authentication**: SSH keys (recommended) or root password
4. Click "Create Droplet"
5. Note your droplet's IP address

## Step 2: Initial Server Setup

### Connect to your droplet

```bash
ssh root@YOUR_DROPLET_IP
```

### Update system packages

```bash
apt update && apt upgrade -y
```

### Install Docker and Docker Compose

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Install Docker Compose
apt install docker-compose-plugin -y

# Verify installation
docker --version
docker compose version
```

### Create a non-root user (optional but recommended)

```bash
# Create user
adduser deploy
usermod -aG docker deploy
usermod -aG sudo deploy

# Switch to new user
su - deploy
```

## Step 3: Prepare Your Application

### On your local machine, prepare files

1. Ensure you have:
   - `key.json` (Google Service Account credentials)
   - `.env` file with your configuration
   - All application files

2. Create a deployment package or clone from Git:

**Option A: Using Git (Recommended)**

```bash
# On your local machine, ensure code is in a Git repository
git init
git add .
git commit -m "Initial commit"
# Push to GitHub/GitLab, then clone on server
```

**Option B: Using SCP**

```bash
# From your local machine, copy files to server
scp -r . deploy@YOUR_DROPLET_IP:/home/deploy/google-sheets-parser/
```

### On the server, clone or prepare the application

```bash
# Navigate to home directory
cd ~

# If using Git:
git clone YOUR_REPO_URL google-sheets-parser
cd google-sheets-parser

# If using SCP, files should already be there
cd google-sheets-parser
```

### Copy and configure environment file

```bash
# Copy example env file
cp .env.example .env

# Edit the .env file with your configuration
nano .env
```

**Important**: Update the following in `.env`:
- `GOOGLE_CREDENTIALS_PATH=./key.json` (or use `GOOGLE_CREDENTIALS_JSON`)
- `SPREADSHEET_ID=your_actual_spreadsheet_id`
- Other configuration as needed

### Ensure key.json is present

```bash
# If you copied via SCP, it should be there
# If using Git, you may need to copy it separately (don't commit credentials!)

# Copy key.json if needed
# scp key.json deploy@YOUR_DROPLET_IP:/home/deploy/google-sheets-parser/key.json
```

## Step 4: Deploy with Docker Compose

### Build and start the container

```bash
# Build and start
docker compose up -d --build

# View logs
docker compose logs -f

# Check status
docker compose ps
```

### Verify the service is running

```bash
# Check health endpoint
curl http://localhost:8000/health

# Or from your local machine
curl http://YOUR_DROPLET_IP:8000/health
```

## Step 5: Set Up Nginx Reverse Proxy (Recommended)

### Install Nginx

```bash
sudo apt install nginx -y
```

### Create Nginx configuration

```bash
sudo nano /etc/nginx/sites-available/google-sheets-parser
```

Add the following configuration:

```nginx
server {
    listen 80;
    server_name YOUR_DOMAIN_OR_IP;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        
        # Increase timeouts for long-running requests
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

### Enable the site

```bash
# Create symbolic link
sudo ln -s /etc/nginx/sites-available/google-sheets-parser /etc/nginx/sites-enabled/

# Remove default site (optional)
sudo rm /etc/nginx/sites-enabled/default

# Test configuration
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx
sudo systemctl enable nginx
```

### Configure Firewall

```bash
# Allow HTTP and HTTPS
sudo ufw allow 'Nginx Full'

# If you need direct access to port 8000 (optional)
sudo ufw allow 8000/tcp

# Enable firewall
sudo ufw enable
```

## Step 6: Set Up SSL with Let's Encrypt (Optional but Recommended)

### Install Certbot

```bash
sudo apt install certbot python3-certbot-nginx -y
```

### Obtain SSL certificate

```bash
# Replace YOUR_EMAIL and YOUR_DOMAIN with actual values
sudo certbot --nginx -d YOUR_DOMAIN -m YOUR_EMAIL --agree-tos --non-interactive

# Or for interactive setup:
sudo certbot --nginx
```

### Auto-renewal is set up automatically

Certbot creates a cron job that automatically renews certificates.

## Step 7: Managing the Application

### View logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f app

# Last 100 lines
docker compose logs --tail=100 app
```

### Restart the application

```bash
docker compose restart
```

### Update the application

```bash
# Pull latest code (if using Git)
git pull

# Rebuild and restart
docker compose up -d --build
```

### Stop the application

```bash
docker compose down
```

### Start the application

```bash
docker compose up -d
```

### Check resource usage

```bash
docker stats
```

## Step 8: Set Up Automated Backups (Optional)

### Backup key.json and .env

Create a backup script:

```bash
nano ~/backup.sh
```

```bash
#!/bin/bash
BACKUP_DIR="/home/deploy/backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Backup key.json and .env
tar -czf $BACKUP_DIR/backup_$DATE.tar.gz \
    /home/deploy/google-sheets-parser/key.json \
    /home/deploy/google-sheets-parser/.env

# Keep only last 7 days of backups
find $BACKUP_DIR -name "backup_*.tar.gz" -mtime +7 -delete
```

```bash
chmod +x ~/backup.sh

# Add to crontab (daily at 2 AM)
crontab -e
# Add: 0 2 * * * /home/deploy/backup.sh
```

## Troubleshooting

### Container won't start

```bash
# Check logs
docker compose logs app

# Check if port is in use
sudo netstat -tlnp | grep 8000

# Restart Docker
sudo systemctl restart docker
```

### Permission issues

```bash
# Fix file permissions
sudo chown -R deploy:deploy /home/deploy/google-sheets-parser
```

### Google API authentication errors

1. Verify `key.json` is present and has correct permissions
2. Check that the service account email has access to your Google Sheet
3. Verify `GOOGLE_CREDENTIALS_PATH` in `.env` is correct

### Can't access from outside

1. Check firewall: `sudo ufw status`
2. Verify Docker port mapping: `docker compose ps`
3. Check Nginx status: `sudo systemctl status nginx`

## Security Best Practices

1. **Never commit credentials**: Keep `key.json` and `.env` out of Git
2. **Use environment variables**: Consider using Digital Ocean's App Platform or Spaces for secrets
3. **Regular updates**: Keep system and Docker images updated
4. **Firewall**: Only open necessary ports
5. **SSL**: Always use HTTPS in production
6. **Monitor logs**: Regularly check application logs for errors

## Monitoring (Optional)

### Set up basic monitoring

```bash
# Install htop for resource monitoring
sudo apt install htop -y

# Monitor system resources
htop
```

### Set up log rotation

Create logrotate config:

```bash
sudo nano /etc/logrotate.d/docker-compose
```

```
/home/deploy/google-sheets-parser/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    missingok
}
```

## Support

For issues:
1. Check application logs: `docker compose logs -f`
2. Check Nginx logs: `sudo tail -f /var/log/nginx/error.log`
3. Verify environment variables: `docker compose exec app env`

## Next Steps

- Set up CI/CD pipeline for automatic deployments
- Configure monitoring and alerting (e.g., UptimeRobot, Pingdom)
- Set up automated backups
- Consider using Digital Ocean's managed databases if needed
- Implement rate limiting if required

