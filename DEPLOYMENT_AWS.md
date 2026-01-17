# AWS EC2 Deployment Guide (CentOS/RHEL)

## Prerequisites
- AWS account with EC2 access
- SSH key pair
- Basic knowledge of Linux commands

## Step 1: Launch EC2 Instance

1. **Launch Instance:**
   - Go to AWS Console → EC2 → Launch Instance
   - Choose Amazon Linux 2 (CentOS/RHEL based) or CentOS
   - Instance type: t2.micro (free tier) or t3.small (recommended)
   - Configure security group (see Step 2 below)
   - Select your SSH key pair
   - Launch instance

2. **Security Group Configuration:**
   - Add inbound rule: **HTTP** port **5000** from **0.0.0.0/0** (or your IP only)
   - Add inbound rule: **SSH** port **22** from your IP
   - Note your instance's **Public IP** address

## Step 2: Connect to EC2 Instance

```bash
ssh -i your-key.pem ec2-user@YOUR_EC2_PUBLIC_IP
```

## Step 3: Install Dependencies (CentOS/RHEL)

```bash
# Update system
sudo yum update -y

# Install Python 3 and pip
sudo yum install python3 python3-pip -y

# Install git (if you need to clone repo)
sudo yum install git -y

# Install development tools (for building some Python packages)
sudo yum groupinstall "Development Tools" -y

# Install OpenSSL development libraries (for dnspython)
sudo yum install openssl-devel -y
```

**Note:** If `yum` is not available, try `dnf` (newer CentOS/RHEL versions):
```bash
sudo dnf update -y
sudo dnf install python3 python3-pip git -y
sudo dnf groupinstall "Development Tools" -y
sudo dnf install openssl-devel -y
```

## Step 4: Deploy Application

**Option A: Upload files via SCP (from your local machine)**

```bash
# From your local machine
scp -i your-key.pem -r /Users/ad/Desktop/email_verifier ec2-user@YOUR_EC2_PUBLIC_IP:~/
```

**Option B: Clone from Git repository (if you push to GitHub/GitLab)**

```bash
# On EC2 instance
cd ~
git clone YOUR_REPO_URL
cd email_verifier
```

## Step 5: Setup Python Environment

```bash
# Navigate to project directory
cd ~/email_verifier

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip (CentOS-specific: use --user or skip if system pip)
# Option 1: Install user-level pip (recommended)
pip install --user --upgrade pip
# Then use: ~/.local/bin/pip install -r requirements.txt

# Option 2: Just proceed with existing pip (simpler, works fine)
# The venv will use its own pip, so system pip version doesn't matter

# Install dependencies
pip install -r requirements.txt
```

**Note:** If you see "Cannot uninstall pip, RECORD file not found" error:
- This is normal on CentOS/RHEL (pip installed via RPM)
- Just skip pip upgrade - the venv will work fine with existing pip
- Or use `pip install --user --upgrade pip` to install pip in user directory

## Step 6: Test the Application

```bash
# Test run (will stop when you exit SSH)
python app.py

# Or use gunicorn
gunicorn app:app --bind 0.0.0.0:5000
```

Visit: `http://YOUR_EC2_PUBLIC_IP:5000` to test.

Press `Ctrl+C` to stop.

## Step 7: Run as System Service (Production)

### Option A: Using systemd (Recommended)

```bash
# Copy service file
sudo cp email-verifier.service /etc/systemd/system/

# Edit service file (adjust paths if needed)
sudo nano /etc/systemd/system/email-verifier.service
# Update WorkingDirectory and paths if your deployment path is different

# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable email-verifier

# Start service
sudo systemctl start email-verifier

# Check status
sudo systemctl status email-verifier

# View logs
sudo journalctl -u email-verifier -f
```

### Option B: Using screen/tmux (Quick setup)

```bash
# Install screen (CentOS/RHEL)
sudo yum install screen -y
# Or for newer versions: sudo dnf install screen -y

# Create new screen session
screen -S email-verifier

# Activate venv and start
cd ~/email_verifier
source venv/bin/activate
gunicorn app:app --bind 0.0.0.0:5000 --workers 4

# Detach: Press Ctrl+A then D
# Reattach: screen -r email-verifier
```

### Option C: Using nohup (Simple background)

```bash
cd ~/email_verifier
source venv/bin/activate
nohup gunicorn app:app --bind 0.0.0.0:5000 --workers 4 > app.log 2>&1 &
```

## Step 8: Access Your API

Once running, your API is available at:

- **Health Check:** `http://YOUR_EC2_PUBLIC_IP:5000/`
- **Verify Email:** `http://YOUR_EC2_PUBLIC_IP:5000/verify`

### Test with curl:

```bash
# Health check
curl http://YOUR_EC2_PUBLIC_IP:5000/

# Verify email
curl -X POST http://YOUR_EC2_PUBLIC_IP:5000/verify \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'
```

### Test with Python requests:

```python
import requests

response = requests.post(
    'http://YOUR_EC2_PUBLIC_IP:5000/verify',
    json={'email': 'test@example.com'}
)
print(response.json())
```

## Step 9: Firewall Configuration (CentOS/RHEL)

CentOS uses `firewalld` or `iptables`. Use firewalld:

```bash
# Check firewalld status
sudo systemctl status firewalld

# If firewall is active, allow port 5000
sudo firewall-cmd --permanent --add-port=5000/tcp
sudo firewall-cmd --reload

# Check status
sudo firewall-cmd --list-ports
```

**Note:** If you're using security groups in AWS, you may not need to configure the local firewall.

## Troubleshooting

**Service won't start:**
```bash
# Check logs
sudo journalctl -u email-verifier -n 50

# Check if port is in use
sudo netstat -tlnp | grep 5000
```

**Can't access from browser:**
- Check security group allows port 5000
- Check firewall (ufw) settings
- Verify service is running: `sudo systemctl status email-verifier`

**Permission errors:**
```bash
# Make start.sh executable
chmod +x start.sh

# Check file ownership
ls -la
```

**DNS/SMTP connection issues:**
- Ensure security group allows outbound connections (default)
- Check if your EC2 instance has internet access

## Security Recommendations

1. **Use Elastic IP** - Get a static IP so it doesn't change on restart
2. **Limit Security Group** - Restrict port 5000 to specific IPs, not 0.0.0.0/0
3. **Use HTTPS** - Add Nginx reverse proxy with SSL certificate
4. **Firewall Rules** - Use ufw to restrict access
5. **Regular Updates** - Keep system and packages updated

## Stopping/Starting Service

```bash
# Stop
sudo systemctl stop email-verifier

# Start
sudo systemctl start email-verifier

# Restart
sudo systemctl restart email-verifier
```
