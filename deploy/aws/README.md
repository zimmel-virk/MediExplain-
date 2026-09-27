# AWS deployment plan — MediExplain+

This directory prepares the project for a **controlled academic deployment**. It does not claim HIPAA/GDPR certification or production clinical approval.

## Recommended rollout

1. **Shadow/parallel phase first.** Keep the normal clinical/manual process in place. Run MediExplain+ alongside it, compare outputs, record errors/review time, and do not make the prototype the sole clinical record or decision path.
2. **Host the application on a private EC2 origin** (or a suitable managed compute service) with an encrypted EBS volume. Run the supplied Docker Compose stack. Only the reverse proxy should accept inbound web traffic.
3. **Use HTTPS and edge protection.** Put an Application Load Balancer or other HTTPS origin in front of the instance, then CloudFront. The included CloudFormation template adds CloudFront, AWS WAF managed rules, TLS-only viewer access and a basic IP rate limit. Use ACM for the certificate and Route 53 for DNS.
4. **Add MFA/organisational identity before real users.** For a proper deployment, put staff authentication behind the institution's IdP or Amazon Cognito with MFA. The application's current JWT/password login is retained so the academic prototype remains runnable locally; it is not presented as the final hospital identity system.
5. **Use least privilege.** EC2/task IAM roles should only access the exact S3/CloudWatch/KMS resources required. Never put AWS credentials, ElevenLabs keys, model-provider keys or database passwords in the repository.
6. **Data protection.** Enable EBS/RDS/S3 encryption, S3 Block Public Access, encrypted backups, log retention, credential rotation, CloudTrail and CloudWatch alarms. Keep consultation/audio retention as short as the research protocol permits.
7. **Database/storage migration.** SQLite is suitable for the single-host academic build. For multi-user production engineering, migrate to RDS PostgreSQL and object storage after validating lifecycle/deletion/audit behaviour. The backend already accepts `DATABASE_URL`; storage has an explicit deployment extension point.
8. **Incident response.** Connect the in-app *Report a data breach* route to the organisation's real incident-management process. The included form records a ticket inside the prototype; it is not itself a regulatory notification mechanism.

## Single EC2 academic deployment

Copy the project to the instance, create `.env` from `.env.example`, set a new `SECRET_KEY`, configure the model services you actually intend to use, then run:

```bash
docker compose up -d --build
docker compose ps
```

Do **not** expose port 8000 publicly. In a secure deployment, allow the origin only from the trusted proxy/load-balancer path and enforce HTTPS.

## CloudFront/WAF

`cloudfront-waf-template.yaml` is intentionally a small edge-security template. It expects an existing HTTPS origin and an ACM certificate in `us-east-1`. Deploy the CloudFront/WAF stack in `us-east-1`, then review WAF rules and rate limits against your evaluation traffic before applying it. A hospital deployment would require a fuller threat model, penetration testing, institutional security review and applicable data-processing agreements.
