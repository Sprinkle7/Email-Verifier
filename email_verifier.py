"""
Email verification module for local verification similar to verifyemailaddress.org
Performs syntax validation, DNS/MX checks, and SMTP handshake (no emails sent)

IMPORTANT LIMITATIONS:
- This tool only verifies if a mail server accepts an email address
- It does NOT verify if the email is actively used by a human
- Gmail, Outlook, Yahoo, and other major providers may return false positives
  (they may accept addresses that don't exist to prevent enumeration)
- Results indicate mail server acceptance, NOT actual account existence

AWS EC2 PORT 25 RESTRICTION:
- AWS EC2 blocks outbound port 25 connections by default to prevent spam
- This will cause SMTP verification to fail for most emails
- To fix: Request AWS to remove port 25 restriction via support case
- Alternative: Use port 587/465, but most servers require authentication
"""

import re
import smtplib
import socket
import random
import string
from typing import Dict, Tuple
import dns.resolver
import dns.exception

# Timeout settings (in seconds)
DNS_TIMEOUT = 5
SMTP_TIMEOUT = 10
SMTP_CONNECT_TIMEOUT = 5

# SMTP connection settings
SMTP_PORT = 25
SMTP_ESMTP_PORT = 587


def validate_email_syntax(email: str) -> bool:
    """
    Validate email syntax using regex.
    Returns True if syntax is valid, False otherwise.
    """
    if not email or not isinstance(email, str):
        return False
    
    # RFC 5322 compliant regex (simplified but practical)
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def check_dns_and_mx(domain: str) -> Tuple[bool, list]:
    """
    Check if domain exists and has MX records.
    Returns (has_mx_records, mx_records_list)
    """
    try:
        # Resolve MX records
        mx_records = dns.resolver.resolve(domain, 'MX', lifetime=DNS_TIMEOUT)
        mx_hosts = [(str(record.exchange), record.preference) for record in mx_records]
        mx_hosts.sort(key=lambda x: x[1])  # Sort by preference
        return True, [host[0] for host in mx_hosts]
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
        # No MX records found, check if domain exists at all
        try:
            dns.resolver.resolve(domain, 'A', lifetime=DNS_TIMEOUT)
            # Domain exists but no MX - might accept mail via A record
            return False, [domain]
        except (dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
            return False, []
    except (dns.exception.Timeout, socket.timeout):
        return False, []
    except Exception:
        return False, []


def generate_random_email(domain: str) -> str:
    """
    Generate a random email address for catch-all testing.
    """
    random_string = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
    return f"{random_string}@{domain}"


def smtp_handshake(mx_host: str, email: str, timeout: int = SMTP_TIMEOUT) -> Tuple[bool, str]:
    """
    Perform SMTP handshake using RCPT TO command.
    Does NOT send any email (no DATA command).
    Tries multiple MX hosts and ports.
    Returns (accepted, error_message)
    """
    # Try multiple ports (25, 587, 465)
    ports_to_try = [SMTP_PORT, SMTP_ESMTP_PORT, 465]
    
    last_error = None
    
    for port in ports_to_try:
        server = None
        try:
            # Connect to SMTP server
            server = smtplib.SMTP(timeout=SMTP_CONNECT_TIMEOUT)
            server.set_debuglevel(0)
            server.connect(mx_host, port, timeout=SMTP_CONNECT_TIMEOUT)
            
            # Send EHLO/HELO
            try:
                server.ehlo()
            except Exception:
                try:
                    server.helo()
                except Exception:
                    server.quit()
                    continue
            
            # Some servers require MAIL FROM first
            try:
                server.mail('')
            except Exception as e:
                server.quit()
                last_error = f"MAIL FROM failed: {str(e)}"
                continue
            
            # Try RCPT TO - this checks if the mailbox is accepted
            try:
                code, message = server.rcpt(email)
                
                # 250 = success, 251/252 = success (forwarding or catch-all)
                if code in (250, 251, 252):
                    server.quit()
                    return True, "Accepted"
                else:
                    server.quit()
                    msg = message.decode('utf-8', errors='ignore') if isinstance(message, bytes) else str(message)
                    last_error = f"Rejected: {code} {msg}"
                    # Continue to next port if this one rejected
                    continue
            except smtplib.SMTPRecipientsRefused as e:
                server.quit()
                last_error = f"Recipient refused: {str(e)}"
                continue
            except Exception as e:
                server.quit()
                last_error = f"RCPT TO error: {str(e)}"
                continue
                
        except (socket.timeout, smtplib.socket.timeout, TimeoutError):
            if server:
                try:
                    server.quit()
                except:
                    pass
            last_error = f"Connection timeout on port {port}"
            continue
        except socket.gaierror:
            if server:
                try:
                    server.quit()
                except:
                    pass
            last_error = "Could not resolve host"
            break  # No point trying other ports if DNS fails
        except (ConnectionRefusedError, OSError, ConnectionResetError) as e:
            if server:
                try:
                    server.quit()
                except:
                    pass
            error_str = str(e)
            # Check if it's port 25 blocked (common on AWS EC2)
            if port == 25 and ("Connection refused" in error_str or "errno 111" in error_str):
                last_error = f"Port 25 blocked (AWS EC2 blocks outbound port 25 by default)"
                continue  # Try next port
            last_error = f"Connection error on port {port}: {str(e)}"
            continue
        except smtplib.SMTPServerDisconnected:
            last_error = f"Server disconnected on port {port}"
            continue
        except Exception as e:
            if server:
                try:
                    server.quit()
                except:
                    pass
            last_error = f"SMTP error on port {port}: {str(e)}"
            continue
    
    # If we get here, all ports failed
    return False, last_error or "All connection attempts failed"


def check_catch_all(domain: str, mx_hosts: list) -> bool:
    """
    Check if domain is catch-all by testing a random mailbox.
    Returns True if catch-all detected.
    """
    if not mx_hosts:
        return False
    
    test_email = generate_random_email(domain)
    accepted, _ = smtp_handshake(mx_hosts[0], test_email, timeout=SMTP_TIMEOUT)
    return accepted


def verify_email(email: str) -> Dict:
    """
    Main verification function.
    Returns a dictionary with verification results.
    """
    result = {
        'email': email,
        'syntax': False,
        'mx': False,
        'smtp_accepts': False,
        'catch_all': False,
        'status': 'invalid'
    }
    
    # Step 1: Syntax validation
    if not validate_email_syntax(email):
        return result
    
    result['syntax'] = True
    
    # Extract domain
    try:
        domain = email.split('@')[1]
    except IndexError:
        result['status'] = 'invalid'
        return result
    
    # Step 2: DNS and MX record check
    has_mx, mx_hosts = check_dns_and_mx(domain)
    
    if not mx_hosts:
        # No MX records and domain doesn't exist
        result['status'] = 'invalid'
        return result
    
    result['mx'] = True
    
    # If no explicit MX records but domain exists, mx_hosts will contain the domain
    # This is already handled by check_dns_and_mx
    
    # Step 3: SMTP handshake - try multiple MX hosts
    accepted = False
    error_msg = "No MX hosts available"
    
    for mx_host in mx_hosts[:3]:  # Try first 3 MX hosts
        accepted, error_msg = smtp_handshake(mx_host, email)
        if accepted:
            break
    
    result['smtp_accepts'] = accepted
    
    if not accepted:
        result['status'] = 'invalid'
        return result
    
    # Step 4: Check for catch-all
    result['catch_all'] = check_catch_all(domain, mx_hosts)
    
    # Determine final status
    if result['catch_all']:
        result['status'] = 'risky'
    else:
        result['status'] = 'valid'
    
    return result
