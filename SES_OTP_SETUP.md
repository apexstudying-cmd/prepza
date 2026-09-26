# Prepza transactional email — Amazon SES

Prepza uses Amazon Simple Email Service (SES) through Boto3 for transactional email. SES is an AWS service; AWS is the cloud account/provider, while SES is the specific email service.

## Render environment variables

Add these to the Prepza backend Render service:

- `AWS_ACCESS_KEY_ID` — IAM access key with only the SES permissions Prepza needs.
- `AWS_SECRET_ACCESS_KEY` — matching IAM secret.
- `AWS_SES_REGION` — the SES region where the sender identity is verified.
- `SES_FROM_EMAIL` — verified sender address or an address under a verified SES domain.

Do not commit secret values to GitHub or place them in frontend variables.

## Required SES permissions

The IAM principal should be limited to:

- `ses:SendEmail`
- `ses:GetAccount`

## SES setup before production

1. Verify the sender email address or domain in SES.
2. Request SES production access if the account is still in the sandbox.
3. Confirm the SES region matches `AWS_SES_REGION`.
4. Confirm the Render variables above are present.
5. Apply `add_email_otp.sql` to the production database.
6. Test signup verification and password recovery.
7. Confirm Admin → Infrastructure shows the live SES quota and application email counts.

SES account quotas are regional and include the 24-hour sending quota, maximum sending rate, and rolling 24-hour usage. These are distinct from AWS Free Tier allowances.
