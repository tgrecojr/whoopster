# Security Findings Report

**Project**: Whoopster - Whoop Data Collection Application
**Date**: 2025-12-19
**Reviewer**: Security Analysis
**Scope**: Full application security review focusing on OWASP Top 10 (2021)

## Executive Summary

This security review identified **15 security findings** across 7 of the OWASP Top 10 categories, ranging from **CRITICAL** to **LOW** severity. The most critical issues involve plaintext storage of OAuth tokens, exposed network ports, and missing CSRF protection in the OAuth flow.

**Risk Summary:**
- 🔴 **CRITICAL**: 3 findings
- 🟠 **HIGH**: 5 findings
- 🟡 **MEDIUM**: 4 findings
- 🔵 **LOW**: 3 findings

**Overall Security Posture**: ⚠️ **MODERATE RISK**
The application implements some good security practices (parameterized queries, non-root Docker user) but has critical gaps in credential protection and network security.

---

## Findings by OWASP Category

### A01:2021 - Broken Access Control

#### Finding #1: No Application-Level Access Control
**Severity**: 🟠 **HIGH**
**Category**: A01 - Broken Access Control
**CWE**: CWE-862 (Missing Authorization)

**Description:**
The application has no authentication or authorization mechanism for accessing the application itself. There is no user login, no API authentication, and no access control between different users' data.

**Affected Components:**
- `src/main.py` - No authentication middleware
- All service files - No access control checks
- `src/database/session.py` - No row-level security

**Impact:**
- Anyone with network access to the application can trigger data syncs
- Anyone with database access can view all users' Whoop data
- No audit trail of who accessed what data
- No way to restrict access to sensitive operations

**Proof of Concept:**
```python
# Any code with database access can read all user data
with get_db_context() as db:
    all_tokens = db.query(OAuthToken).all()  # No access control!
```

**Recommendation:**
1. Implement user authentication (API keys, OAuth, or session-based auth)
2. Add authorization checks before data access
3. Implement row-level security in PostgreSQL
4. Add audit logging for sensitive operations
5. Consider multi-tenant isolation if supporting multiple users

**References:**
- [OWASP Access Control Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Access_Control_Cheat_Sheet.html)

---

### A02:2021 - Cryptographic Failures

#### Finding #2: OAuth Tokens Stored in Plaintext
**Severity**: 🔴 **CRITICAL**
**Category**: A02 - Cryptographic Failures
**CWE**: CWE-312 (Cleartext Storage of Sensitive Information)

**Description:**
OAuth access tokens and refresh tokens are stored in plaintext in the PostgreSQL database with no encryption at rest. This violates security best practices for credential storage.

**Affected Components:**
- `src/auth/token_manager.py:90, 107-110` - Plaintext token storage
- `src/models/db_models.py:OAuthToken` - No encryption column types
- Database - No transparent data encryption configured

**Impact:**
- Database backup files contain plaintext tokens
- Database administrators can read all OAuth tokens
- Compromised database dump exposes all user credentials
- Tokens can be extracted from database logs
- No protection if database storage media is stolen

**Proof of Concept:**
```sql
-- Anyone with database access can extract tokens
SELECT user_id, access_token, refresh_token FROM oauth_tokens;
```

**Current Code:**
```python
# src/auth/token_manager.py:90
existing_token.access_token = access_token  # Stored as plaintext!
existing_token.refresh_token = refresh_token  # Stored as plaintext!
```

**Recommendation:**
1. **Implement application-level encryption:**
   ```python
   from cryptography.fernet import Fernet

   class TokenEncryption:
       def __init__(self):
           key = os.getenv("ENCRYPTION_KEY")  # Store in secure vault
           self.cipher = Fernet(key.encode())

       def encrypt(self, token: str) -> str:
           return self.cipher.encrypt(token.encode()).decode()

       def decrypt(self, encrypted: str) -> str:
           return self.cipher.decrypt(encrypted.encode()).decode()
   ```

2. **Use database-level encryption:**
   - Enable PostgreSQL `pgcrypto` extension
   - Use `encrypt()` and `decrypt()` functions
   - Or enable Transparent Data Encryption (TDE)

3. **Key Management:**
   - Store encryption keys in AWS Secrets Manager or HashiCorp Vault
   - Implement key rotation policy
   - Never store keys in environment variables in production

4. **Add to `.env`:**
   ```bash
   ENCRYPTION_KEY=<generated-32-byte-key>  # Use Fernet.generate_key()
   ```

**Migration Guide for Existing Installations:**

If you're upgrading from a version without token encryption:

1. **Generate encryption key:**
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

2. **Add to your `.env` file:**
   ```bash
   TOKEN_ENCRYPTION_KEY=<your-generated-key>
   ```

3. **Existing tokens will become invalid:**
   - The application expects encrypted tokens in the database
   - Existing plaintext tokens cannot be automatically migrated (security best practice)
   - Users must re-authenticate via OAuth flow

4. **Force re-authentication:**
   ```sql
   -- Clear existing plaintext tokens (run this after adding encryption key)
   DELETE FROM oauth_tokens;
   ```

5. **Restart application:**
   ```bash
   docker-compose restart app
   ```

6. **Users must re-run OAuth setup:**
   ```bash
   docker-compose exec app python scripts/init_oauth.py
   ```

**IMPORTANT:** Once encryption is enabled, never change the `TOKEN_ENCRYPTION_KEY` without clearing all tokens, as existing encrypted tokens will become unreadable.

**References:**
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html)
- [Python Cryptography Documentation](https://cryptography.io/en/latest/)

---

#### Finding #3: Database Credentials Logged in Plaintext
**Severity**: 🔴 **CRITICAL**
**Category**: A02 - Cryptographic Failures
**CWE**: CWE-532 (Insertion of Sensitive Information into Log File)

**Description:**
The database connection URL, which contains the database password, is logged in plaintext.

**Affected Components:**
- `src/database/session.py:85` - Logs full database URL

**Current Code:**
```python
# src/database/session.py:85
def init_db() -> None:
    logger.info("Database initialized", database_url=settings.database_url)
    # database_url contains password: postgresql://user:PASSWORD@host/db
```

**Impact:**
- Database passwords exposed in application logs
- Log aggregation systems contain credentials
- Log files on disk contain plaintext passwords
- Anyone with log access can extract database credentials

**Recommendation:**
1. **Remove sensitive data from logs:**
   ```python
   def init_db() -> None:
       # Log without credentials
       safe_url = settings.database_url.split('@')[1] if '@' in settings.database_url else 'unknown'
       logger.info("Database initialized", database_host=safe_url)
   ```

2. **Implement log scrubbing:**
   ```python
   import re

   def scrub_sensitive_data(log_message: str) -> str:
       # Remove passwords from database URLs
       return re.sub(
           r'postgresql://([^:]+):([^@]+)@',
           r'postgresql://\1:***@',
           log_message
       )
   ```

3. **Configure logging filters:**
   - Add structured logging processors to redact sensitive fields
   - Never log raw configuration values

**References:**
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)

---

#### Finding #4: No SSL/TLS for Database Connections
**Severity**: 🟠 **HIGH**
**Category**: A02 - Cryptographic Failures
**CWE**: CWE-319 (Cleartext Transmission of Sensitive Information)

**Description:**
Database connections do not enforce SSL/TLS encryption, allowing data to be transmitted in plaintext over the network.

**Affected Components:**
- `src/config.py:18-31` - Database URL construction
- `src/database/session.py:17` - Engine creation without SSL config
- `docker-compose.yml` - No SSL configuration for PostgreSQL

**Impact:**
- OAuth tokens transmitted in cleartext between app and database
- Credentials exposed on network (especially in cloud deployments)
- Man-in-the-middle attacks possible
- Packet sniffing can capture sensitive data

**Recommendation:**
1. **Enable SSL in database URL:**
   ```python
   @property
   def database_url(self) -> str:
       encoded_user = quote_plus(self.postgres_user)
       encoded_password = quote_plus(self.postgres_password)

       # Add sslmode parameter for production
       ssl_mode = "require" if self.environment == "production" else "prefer"

       return (
           f"postgresql://{encoded_user}:{encoded_password}"
           f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
           f"?sslmode={ssl_mode}"
       )
   ```

2. **Configure PostgreSQL for SSL:**
   ```yaml
   # docker-compose.yml
   postgres:
     environment:
       POSTGRES_INITDB_ARGS: "--ssl=on"
     volumes:
       - ./certs/server.crt:/var/lib/postgresql/server.crt:ro
       - ./certs/server.key:/var/lib/postgresql/server.key:ro
   ```

3. **Production deployment:**
   - Use managed PostgreSQL service with SSL (RDS, Cloud SQL, etc.)
   - Configure SSL certificates properly
   - Enforce SSL connections (reject non-SSL)

**References:**
- [PostgreSQL SSL Documentation](https://www.postgresql.org/docs/current/ssl-tcp.html)

---

### A03:2021 - Injection

#### ✅ Finding #5: SQL Injection - NOT VULNERABLE
**Severity**: 🟢 **INFORMATIONAL** (Good Practice)
**Category**: A03 - Injection
**Status**: ✅ **SECURE**

**Description:**
The application uses SQLAlchemy ORM with parameterized queries throughout, which effectively prevents SQL injection attacks.

**Evidence:**
```python
# src/services/sleep_service.py
stmt = select(SyncStatus).where(SyncStatus.user_id == user_id)  # Parameterized
insert_stmt = insert(SleepRecord).values(**db_record)  # Parameterized
```

**Best Practices Observed:**
- All database queries use SQLAlchemy ORM
- No raw SQL string concatenation
- User input (user_id) properly parameterized
- No dynamic query construction from user input

**Recommendation:**
✅ Continue using parameterized queries. No action needed.

---

### A04:2021 - Insecure Design

#### Finding #6: OAuth Redirect URI Uses HTTP (Not HTTPS)
**Severity**: 🔴 **CRITICAL**
**Category**: A04 - Insecure Design
**CWE**: CWE-319 (Cleartext Transmission of Sensitive Information)

**Description:**
The default OAuth redirect URI uses HTTP instead of HTTPS, exposing the authorization code in transit.

**Affected Components:**
- `src/config.py:36` - Default redirect URI
- `.env.example:11` - Example uses HTTP
- `docker-compose.yml:48` - Default HTTP redirect

**Current Configuration:**
```python
# src/config.py:36
whoop_redirect_uri: str = "http://localhost:8000/callback"
```

**Impact:**
- Authorization codes transmitted in cleartext
- Network sniffing can intercept OAuth flow
- Man-in-the-middle attacks possible
- Violates OAuth 2.0 security best practices (RFC 6749)

**Attack Scenario:**
1. Attacker on same network intercepts HTTP callback
2. Extracts authorization code from URL
3. Exchanges code for access token before legitimate app
4. Gains full access to user's Whoop data

**Recommendation:**
1. **Enforce HTTPS in production:**
   ```python
   @property
   def whoop_redirect_uri(self) -> str:
       if self.environment == "production" and not self._redirect_uri.startswith("https://"):
           raise ValueError("Redirect URI must use HTTPS in production")
       return self._redirect_uri
   ```

2. **Update .env.example:**
   ```bash
   # Development (local testing only)
   WHOOP_REDIRECT_URI=http://localhost:8000/callback

   # Production (REQUIRED)
   # WHOOP_REDIRECT_URI=https://yourdomain.com/callback
   ```

3. **Add validation in OAuth client:**
   ```python
   # src/auth/oauth_client.py
   if settings.environment == "production":
       assert settings.whoop_redirect_uri.startswith("https://"), \
           "Production redirect URI must use HTTPS"
   ```

**References:**
- [OAuth 2.0 Security Best Current Practice](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-security-topics)
- [RFC 6749 Section 10.6](https://datatracker.ietf.org/doc/html/rfc6749#section-10.6)

---

#### Finding #7: Missing CSRF Protection in OAuth Flow
**Severity**: 🟠 **HIGH**
**Category**: A04 - Insecure Design
**CWE**: CWE-352 (Cross-Site Request Forgery)

**Description:**
The OAuth callback handler receives and logs the `state` parameter but there's no evidence of validation against the originally sent state, making the flow vulnerable to CSRF attacks.

**Affected Components:**
- `scripts/init_oauth.py:43-44` - State received but not validated
- `src/auth/oauth_client.py` - Need to verify state generation and validation

**Current Code:**
```python
# scripts/init_oauth.py:43-44
OAuthCallbackHandler.auth_code = params.get("code", [None])[0]
OAuthCallbackHandler.state = params.get("state", [None])[0]  # Captured but not validated!
```

**Impact:**
- CSRF attacks can trick users into authorizing attacker's app
- Attacker can link their Whoop account to victim's application instance
- Session fixation attacks possible
- Violates OAuth 2.0 security requirements

**Attack Scenario:**
1. Attacker generates authorization URL with malicious redirect
2. Victim clicks attacker's link while logged into application
3. Victim authorizes, but authorization code goes to attacker
4. Attacker exchanges code for access token
5. Attacker gains access to victim's Whoop data

**Recommendation:**
1. **Generate and validate state parameter:**
   ```python
   import secrets

   # Generate state (store in session or database)
   state = secrets.token_urlsafe(32)

   # Store state with user session
   with get_db_context() as db:
       user.oauth_state = state
       user.oauth_state_expiry = datetime.now() + timedelta(minutes=10)
       db.commit()

   # Validate in callback
   if received_state != stored_state:
       raise ValueError("Invalid state parameter - possible CSRF attack")

   if datetime.now() > user.oauth_state_expiry:
       raise ValueError("State parameter expired")
   ```

2. **Add state validation to OAuthCallbackHandler:**
   ```python
   def do_GET(self):
       # ... existing code ...

       # Validate state parameter
       if not self._validate_state(OAuthCallbackHandler.state):
           self.send_response(403)
           self.wfile.write(b"<h1>Security Error</h1><p>Invalid state parameter</p>")
           return
   ```

**References:**
- [OAuth 2.0 Threat Model - CSRF](https://datatracker.ietf.org/doc/html/rfc6819#section-4.4.1.8)
- [OWASP CSRF Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)

---

### A05:2021 - Security Misconfiguration

#### Finding #8: Database Port Exposed to All Interfaces
**Severity**: 🟠 **HIGH**
**Category**: A05 - Security Misconfiguration
**CWE**: CWE-200 (Exposure of Sensitive Information)

**Description:**
PostgreSQL and Grafana ports are exposed to all network interfaces (0.0.0.0) instead of localhost only, allowing external access.

**Affected Components:**
- `docker-compose.yml:14-15` - PostgreSQL port mapping
- `docker-compose.yml:84-85` - Grafana port mapping

**Current Configuration:**
```yaml
# docker-compose.yml:14-15
ports:
  - "5432:5432"  # Exposes to 0.0.0.0:5432 - BAD!

# docker-compose.yml:84-85
ports:
  - "3000:3000"  # Exposes to 0.0.0.0:3000 - BAD!
```

**Impact:**
- Database accessible from external networks
- Grafana admin panel exposed to internet
- Brute force attacks possible on exposed services
- Lateral movement easier for attackers

**Recommendation:**
1. **Bind to localhost only:**
   ```yaml
   postgres:
     ports:
       - "127.0.0.1:5432:5432"  # Only accessible from localhost

   grafana:
     ports:
       - "127.0.0.1:3000:3000"  # Only accessible from localhost
   ```

2. **For production, remove port mappings entirely:**
   ```yaml
   postgres:
     # No ports section - only accessible within Docker network
     networks:
       - whoopster-network

   grafana:
     # Use reverse proxy (nginx) for external access
     # No direct port exposure
   ```

3. **If remote access needed:**
   - Use SSH tunnel: `ssh -L 3000:localhost:3000 server`
   - Use VPN for secure remote access
   - Configure firewall rules to restrict source IPs

**References:**
- [Docker Security Best Practices](https://docs.docker.com/engine/security/)
- [CIS Docker Benchmark](https://www.cisecurity.org/benchmark/docker)

---

#### Finding #9: Weak Default Credentials in Example Configuration
**Severity**: 🟡 **MEDIUM**
**Category**: A05 - Security Misconfiguration
**CWE**: CWE-798 (Use of Hard-coded Credentials)

**Description:**
The `.env.example` file contains weak default passwords that users might not change.

**Affected Components:**
- `.env.example:4, 20` - Weak default passwords

**Current Configuration:**
```bash
# .env.example:4
POSTGRES_PASSWORD=change_me_in_production  # Weak and predictable!

# .env.example:20
GRAFANA_ADMIN_PASSWORD=change_me_in_production  # Weak and predictable!
```

**Impact:**
- Users may forget to change default passwords
- Weak passwords easily guessed by attackers
- No guidance on password complexity
- Brute force attacks succeed quickly

**Recommendation:**
1. **Use placeholder values:**
   ```bash
   # .env.example
   POSTGRES_PASSWORD=<GENERATE_STRONG_PASSWORD>
   GRAFANA_ADMIN_PASSWORD=<GENERATE_STRONG_PASSWORD>
   ```

2. **Add password generation instructions:**
   ```bash
   # PostgreSQL Configuration
   POSTGRES_DB=whoopster
   POSTGRES_USER=whoopster
   # Generate with: openssl rand -base64 32
   POSTGRES_PASSWORD=<REPLACE_WITH_GENERATED_PASSWORD>
   ```

3. **Add validation in application:**
   ```python
   # src/config.py
   from pydantic import field_validator

   class Settings(BaseSettings):
       postgres_password: str

       @field_validator('postgres_password')
       def validate_password_strength(cls, v):
           if v in ['password', 'change_me', 'change_me_in_production']:
               raise ValueError('Default password detected! Generate a strong password.')
           if len(v) < 16:
               raise ValueError('Password must be at least 16 characters')
           return v
   ```

4. **Update README with security checklist:**
   ```markdown
   ### Security Checklist
   - [ ] Generate strong passwords (32+ characters)
   - [ ] Never use default credentials
   - [ ] Enable SSL/TLS for database
   - [ ] Bind services to localhost only
   - [ ] Encrypt OAuth tokens at rest
   ```

**References:**
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)

---

#### Finding #10: Missing Security Headers
**Severity**: 🟡 **MEDIUM**
**Category**: A05 - Security Misconfiguration
**CWE**: CWE-116 (Improper Encoding or Escaping of Output)

**Description:**
The application and Grafana instance don't configure security headers (CSP, HSTS, X-Frame-Options, etc.).

**Affected Components:**
- `docker-compose.yml` - No Grafana security header configuration
- No reverse proxy configured with security headers

**Impact:**
- Clickjacking attacks possible
- Cross-site scripting (XSS) easier to exploit
- No HTTPS enforcement
- Missing defense-in-depth protections

**Recommendation:**
1. **Add Grafana security configuration:**
   ```yaml
   # docker-compose.yml
   grafana:
     environment:
       # Security headers
       GF_SECURITY_STRICT_TRANSPORT_SECURITY: "true"
       GF_SECURITY_X_CONTENT_TYPE_OPTIONS: "true"
       GF_SECURITY_X_XSS_PROTECTION: "true"
       GF_SECURITY_CONTENT_SECURITY_POLICY: "true"
       GF_SECURITY_COOKIE_SECURE: "true"
       GF_SECURITY_COOKIE_SAMESITE: "strict"
   ```

2. **Add nginx reverse proxy with security headers:**
   ```nginx
   # nginx.conf
   server {
       listen 443 ssl http2;
       server_name yourdomain.com;

       # Security headers
       add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
       add_header X-Frame-Options "SAMEORIGIN" always;
       add_header X-Content-Type-Options "nosniff" always;
       add_header X-XSS-Protection "1; mode=block" always;
       add_header Content-Security-Policy "default-src 'self'" always;
       add_header Referrer-Policy "strict-origin-when-cross-origin" always;

       location / {
           proxy_pass http://grafana:3000;
       }
   }
   ```

**References:**
- [OWASP Secure Headers Project](https://owasp.org/www-project-secure-headers/)
- [Mozilla Observatory](https://observatory.mozilla.org/)

---

#### Finding #11: Docker Healthcheck Uses Non-Existent Function
**Severity**: 🟡 **MEDIUM**
**Category**: A05 - Security Misconfiguration
**CWE**: CWE-754 (Improper Check for Unusual or Exceptional Conditions)

**Description:**
The `docker-compose.yml` file contains a healthcheck that calls a non-existent function `verify_connection()`, which will cause the healthcheck to always fail.

**Affected Components:**
- `docker-compose.yml:63` - Invalid healthcheck command

**Current Configuration:**
```yaml
# docker-compose.yml:63
healthcheck:
  test: ["CMD-SHELL", "python -c 'from src.database.session import verify_connection; import sys; sys.exit(0 if verify_connection() else 1)'"]
```

**Impact:**
- Container appears unhealthy but keeps running
- Monitoring systems get false alarms
- Actual health issues may be missed
- Automated recovery mechanisms won't trigger

**Recommendation:**
1. **Fix healthcheck to match Dockerfile:**
   ```yaml
   healthcheck:
     test: ["CMD-SHELL", "python -c 'import sys; from src.config import settings; sys.exit(0)'"]
     interval: 60s
     timeout: 10s
     retries: 3
     start_period: 30s
   ```

2. **Or implement actual health check:**
   ```python
   # src/database/session.py
   def verify_connection() -> bool:
       try:
           with engine.connect() as conn:
               conn.execute("SELECT 1")
           return True
       except Exception:
           return False
   ```

**References:**
- [Docker Healthcheck Best Practices](https://docs.docker.com/engine/reference/builder/#healthcheck)

---

### A06:2021 - Vulnerable and Outdated Components

#### Finding #12: No Automated Dependency Scanning
**Severity**: 🟡 **MEDIUM**
**Category**: A06 - Vulnerable and Outdated Components
**CWE**: CWE-1395 (Dependency on Vulnerable Third-Party Component)

**Description:**
The project has no automated dependency vulnerability scanning or security advisories configured.

**Affected Components:**
- `requirements.txt` - No lock file with hashes
- `.github/workflows/` - No security scanning workflow
- No Dependabot configuration

**Impact:**
- Unknown vulnerabilities in dependencies
- No alerts for new CVEs
- Delayed patching of security issues
- Supply chain attack risk

**Current Dependencies (Sample):**
```
httpx==0.25.2          # Need to check for CVEs
authlib==1.6.5         # Need to check for CVEs
sqlalchemy==2.0.36     # Need to check for CVEs
```

**Recommendation:**
1. **Enable GitHub Dependabot:**
   ```yaml
   # .github/dependabot.yml
   version: 2
   updates:
     - package-ecosystem: "pip"
       directory: "/"
       schedule:
         interval: "weekly"
       open-pull-requests-limit: 10
       reviewers:
         - "security-team"
       labels:
         - "dependencies"
         - "security"
   ```

2. **Add safety check to CI/CD:**
   ```yaml
   # .github/workflows/security-scan.yml
   name: Security Scan

   on: [push, pull_request]

   jobs:
     security:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - name: Set up Python
           uses: actions/setup-python@v4
           with:
             python-version: '3.11'

         - name: Install safety
           run: pip install safety

         - name: Check dependencies for vulnerabilities
           run: safety check --file requirements.txt --json

         - name: SAST scanning with Bandit
           run: |
             pip install bandit
             bandit -r src/ -f json -o bandit-report.json
   ```

3. **Use pip-audit:**
   ```bash
   pip install pip-audit
   pip-audit --requirement requirements.txt
   ```

4. **Add container scanning:**
   ```yaml
   # .github/workflows/docker-build.yml
   - name: Run Trivy vulnerability scanner
     uses: aquasecurity/trivy-action@master
     with:
       image-ref: 'ghcr.io/${{ github.repository }}:latest'
       format: 'sarif'
       output: 'trivy-results.sarif'
       severity: 'CRITICAL,HIGH'
   ```

**References:**
- [GitHub Dependabot Documentation](https://docs.github.com/en/code-security/dependabot)
- [OWASP Dependency Check](https://owasp.org/www-project-dependency-check/)
- [Python Safety](https://pyup.io/safety/)

---

### A07:2021 - Identification and Authentication Failures

#### Finding #13: No Token Revocation Mechanism
**Severity**: 🟠 **HIGH**
**Category**: A07 - Identification and Authentication Failures
**CWE**: CWE-613 (Insufficient Session Expiration)

**Description:**
There's no mechanism to revoke tokens in case of compromise. The `delete_token` method exists but isn't integrated into any security response workflow.

**Affected Components:**
- `src/auth/token_manager.py:275-308` - Delete function exists but no integration
- No administrative interface to revoke tokens
- No automatic revocation on security events

**Impact:**
- Compromised tokens remain valid until natural expiration
- No emergency response capability
- Stolen tokens usable for full validity period
- No way to force re-authentication

**Recommendation:**
1. **Implement token revocation API:**
   ```python
   async def revoke_token(
       self,
       user_id: int,
       reason: str = "user_request"
   ) -> bool:
       """
       Revoke user's OAuth token with audit logging.
       """
       logger.warning(
           "Token revocation requested",
           user_id=user_id,
           reason=reason
       )

       success = await self.delete_token(user_id)

       if success:
           # Log security event
           await log_security_event(
               event_type="token_revoked",
               user_id=user_id,
               reason=reason
           )

       return success
   ```

2. **Add token blacklist for immediate revocation:**
   ```python
   # New table in db_models.py
   class RevokedToken(Base):
       __tablename__ = "revoked_tokens"

       id = Column(Integer, primary_key=True)
       token_hash = Column(String(64), unique=True)  # SHA-256 hash
       revoked_at = Column(DateTime(timezone=True))
       reason = Column(String(255))
       user_id = Column(Integer, ForeignKey("users.id"))
   ```

3. **Check blacklist before using token:**
   ```python
   async def is_token_revoked(self, token: str) -> bool:
       token_hash = hashlib.sha256(token.encode()).hexdigest()
       with get_db_context() as db:
           revoked = db.query(RevokedToken).filter_by(
               token_hash=token_hash
           ).first()
           return revoked is not None
   ```

**References:**
- [RFC 7009 - OAuth 2.0 Token Revocation](https://datatracker.ietf.org/doc/html/rfc7009)

---

#### Finding #14: No Rate Limiting on OAuth Callback
**Severity**: 🔵 **LOW**
**Category**: A07 - Identification and Authentication Failures
**CWE**: CWE-307 (Improper Restriction of Excessive Authentication Attempts)

**Description:**
The OAuth callback handler has no rate limiting, allowing unlimited authorization attempts.

**Affected Components:**
- `scripts/init_oauth.py:29-83` - OAuthCallbackHandler class
- No rate limiting middleware

**Impact:**
- Brute force attacks on authorization codes
- Denial of service via callback flooding
- Resource exhaustion possible

**Recommendation:**
1. **Add rate limiting to callback handler:**
   ```python
   from collections import defaultdict
   from time import time

   class RateLimitedCallbackHandler(BaseHTTPRequestHandler):
       request_counts = defaultdict(list)
       MAX_REQUESTS = 5  # Per IP
       TIME_WINDOW = 60  # Seconds

       def do_GET(self):
           client_ip = self.client_address[0]

           # Clean old requests
           cutoff = time() - self.TIME_WINDOW
           self.request_counts[client_ip] = [
               t for t in self.request_counts[client_ip]
               if t > cutoff
           ]

           # Check rate limit
           if len(self.request_counts[client_ip]) >= self.MAX_REQUESTS:
               self.send_response(429)
               self.send_header("Retry-After", "60")
               self.end_headers()
               self.wfile.write(b"<h1>Too Many Requests</h1>")
               return

           self.request_counts[client_ip].append(time())
           # ... rest of handler ...
   ```

**References:**
- [OWASP API Security Top 10 - Rate Limiting](https://owasp.org/www-project-api-security/)

---

### A08:2021 - Software and Data Integrity Failures

#### Finding #15: Docker Images Use Non-Specific Tags
**Severity**: 🔵 **LOW**
**Category**: A08 - Software and Data Integrity Failures
**CWE**: CWE-494 (Download of Code Without Integrity Check)

**Description:**
Dockerfile uses `python:3.11-slim` and docker-compose uses `postgres:15-alpine` without digest pinning, allowing image substitution.

**Affected Components:**
- `Dockerfile:8, 30` - Uses `python:3.11-slim` tag
- `docker-compose.yml:6` - Uses `postgres:15-alpine` tag
- `docker-compose.yml:71` - Uses `grafana/grafana:10.2.0` tag

**Current Configuration:**
```dockerfile
FROM python:3.11-slim  # Mutable tag!
```

**Impact:**
- Image tags can be updated silently
- No guarantee of reproducible builds
- Supply chain attack vector
- Integrity verification impossible

**Recommendation:**
1. **Pin images by digest:**
   ```dockerfile
   FROM python:3.11-slim@sha256:158caf0e080e2cd74ef2879ed3c4e697792ee65251c8208b7afb56683c32ea6c
   ```

2. **Get digest:**
   ```bash
   docker pull python:3.11-slim
   docker inspect python:3.11-slim --format='{{index .RepoDigests 0}}'
   ```

3. **Update docker-compose:**
   ```yaml
   postgres:
     image: postgres:15-alpine@sha256:abc123...

   grafana:
     image: grafana/grafana:10.2.0@sha256:def456...
   ```

4. **Add Renovate or Dependabot for Docker:**
   ```json
   // renovate.json
   {
     "extends": ["config:base"],
     "docker": {
       "major": {
         "enabled": false
       },
       "pinDigests": true
     }
   }
   ```

**References:**
- [Docker Image Digest Best Practices](https://docs.docker.com/engine/reference/commandline/pull/#pull-an-image-by-digest-immutable-identifier)

---

## Summary of Recommendations by Priority

### 🔴 Critical (Immediate Action Required)

1. **Encrypt OAuth tokens at rest** (Finding #2)
   - Implement application-level encryption with Fernet
   - Use secure key management (Vault/Secrets Manager)
   - Estimated effort: 4-8 hours

2. **Remove credentials from logs** (Finding #3)
   - Implement log scrubbing for database URLs
   - Add structured logging filters
   - Estimated effort: 2-4 hours

3. **Enforce HTTPS for OAuth redirects** (Finding #6)
   - Add validation in production mode
   - Update documentation and examples
   - Estimated effort: 1-2 hours

### 🟠 High (Address Within 1 Week)

4. **Implement access control** (Finding #1)
   - Add authentication layer
   - Implement authorization checks
   - Estimated effort: 16-24 hours

5. **Enable SSL/TLS for database** (Finding #4)
   - Configure SSL in production
   - Update connection strings
   - Estimated effort: 2-4 hours

6. **Fix CSRF protection** (Finding #7)
   - Implement state validation
   - Add session management
   - Estimated effort: 4-6 hours

7. **Bind ports to localhost** (Finding #8)
   - Update docker-compose.yml
   - Document reverse proxy setup
   - Estimated effort: 1 hour

8. **Implement token revocation** (Finding #13)
   - Add revocation API
   - Create token blacklist
   - Estimated effort: 4-6 hours

### 🟡 Medium (Address Within 1 Month)

9. **Improve default credentials** (Finding #9)
10. **Add security headers** (Finding #10)
11. **Fix Docker healthcheck** (Finding #11)
12. **Enable dependency scanning** (Finding #12)

### 🔵 Low (Address As Time Permits)

13. **Add rate limiting to OAuth** (Finding #14)
14. **Pin Docker image digests** (Finding #15)

---

## Compliance Checklist

### Current Security Posture

- [ ] **CIS Docker Benchmark**: Partial compliance
  - ✅ Non-root container user
  - ❌ Port exposure issues
  - ❌ No image scanning

- [ ] **OWASP ASVS Level 1**: Partial compliance
  - ✅ Parameterized queries
  - ❌ Missing access control
  - ❌ Plaintext credential storage

- [ ] **PCI DSS** (if storing payment data): Not compliant
  - ❌ Encryption at rest required
  - ❌ Network segmentation required
  - ❌ Access logging required

- [ ] **GDPR** (if EU users): Partial compliance
  - ✅ Data minimization
  - ❌ Encryption at rest required
  - ❌ Audit logging required

---

## Testing Recommendations

### Security Testing Tools

1. **SAST (Static Analysis):**
   ```bash
   pip install bandit
   bandit -r src/ -f json -o security-report.json
   ```

2. **Dependency Scanning:**
   ```bash
   pip install safety
   safety check --file requirements.txt
   ```

3. **Container Scanning:**
   ```bash
   docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
     aquasec/trivy image whoopster:latest
   ```

4. **Secrets Scanning:**
   ```bash
   pip install detect-secrets
   detect-secrets scan --baseline .secrets.baseline
   ```

### Penetration Testing Checklist

- [ ] Test OAuth flow for CSRF/state validation
- [ ] Attempt SQL injection on all inputs
- [ ] Test rate limiting on API endpoints
- [ ] Verify SSL/TLS configuration
- [ ] Test access control bypass
- [ ] Attempt token reuse/replay attacks
- [ ] Test Docker container escape
- [ ] Verify secrets not in logs

---

## References

### OWASP Resources
- [OWASP Top 10 2021](https://owasp.org/www-project-top-ten/)
- [OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/)
- [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/)

### Standards
- [CWE Top 25](https://cwe.mitre.org/top25/)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)
- [CIS Benchmarks](https://www.cisecurity.org/cis-benchmarks/)

### Tools
- [Bandit (SAST for Python)](https://github.com/PyCQA/bandit)
- [Safety (Dependency Scanner)](https://github.com/pyupio/safety)
- [Trivy (Container Scanner)](https://github.com/aquasecurity/trivy)
- [GitGuardian (Secrets Scanner)](https://www.gitguardian.com/)

---

## Appendix: Quick Wins

These can be implemented in under 30 minutes each:

1. Update docker-compose port bindings to localhost
2. Fix docker-compose healthcheck command
3. Update .env.example with password generation instructions
4. Add database URL scrubbing to logs
5. Add HTTPS validation for production redirect URI
6. Enable Dependabot for automated dependency updates

---

**Report Generated**: 2025-12-19
**Next Review Due**: 2025-01-19 (30 days)
**Security Contact**: Create SECURITY.md for vulnerability reporting
