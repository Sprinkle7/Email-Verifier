"""
Email verification module for local verification similar to verifyemailaddress.org
Performs syntax validation, DNS/MX checks, and SMTP handshake (no emails sent)

IMPORTANT LIMITATIONS:
- This tool only verifies if a mail server accepts an email address
- It does NOT verify if the email is actively used by a human
- Gmail, Outlook, Yahoo, and other major providers may return false positives
  (they may accept addresses that don't exist to prevent enumeration)
- Results indicate mail server acceptance, NOT actual account existence
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
    Returns (accepted, error_message)
    """
    server = None
    try:
        # Connect to SMTP server
        server = smtplib.SMTP(timeout=timeout)
        server.set_debuglevel(0)
        server.connect(mx_host, SMTP_PORT)
        
        # Send EHLO/HELO
        try:
            server.ehlo()
        except Exception:
            server.helo()
        
        # Some servers require MAIL FROM first
        server.mail('')
        
        # Try RCPT TO - this checks if the mailbox is accepted
        code, message = server.rcpt(email)
        
        # 250 = success, 251/252 = success (forwarding or catch-all)
        if code in (250, 251, 252):
            server.quit()
            return True, "Accepted"
        else:
            server.quit()
            msg = message.decode('utf-8', errors='ignore') if isinstance(message, bytes) else str(message)
            return False, f"Rejected: {code} {msg}"
            
    except (socket.timeout, smtplib.socket.timeout, TimeoutError):
        if server:
            try:
                server.quit()
            except:
                pass
        return False, "Connection timeout"
    except socket.gaierror:
        if server:
            try:
                server.quit()
            except:
                pass
        return False, "Could not resolve host"
    except (ConnectionRefusedError, OSError) as e:
        if server:
            try:
                server.quit()
            except:
                pass
        return False, f"Connection error: {str(e)}"
    except smtplib.SMTPServerDisconnected:
        return False, "Server disconnected"
    except Exception as e:
        if server:
            try:
                server.quit()
            except:
                pass
        return False, f"SMTP error: {str(e)}"


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
    
    # Step 3: SMTP handshake
    accepted, error_msg = smtp_handshake(mx_hosts[0], email)
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
