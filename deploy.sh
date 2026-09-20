#!/usr/bin/env bash
# Publish out/site/ to an S3 static website.
#
#   ./deploy.sh my-bucket-name [region]
#
# Needs the AWS CLI and credentials with s3:CreateBucket, s3:PutObject,
# s3:PutBucketPolicy and s3:PutBucketWebsite.
#
# READ THIS FIRST: this makes the bucket publicly readable, and checks.html
# carries the whole run inlined - consignee names, addresses, ports, weights
# and OC numbers from the organizers' bundle. Anyone with the link, and any
# crawler that finds it, can read all of it. That is normally fine for a
# hackathon demo and not fine for client data. Decide deliberately.
set -euo pipefail

BUCKET="${1:-}"
REGION="${2:-ap-southeast-1}"
SITE="$(cd "$(dirname "$0")" && pwd)/out/site"

if [ -z "$BUCKET" ]; then
  echo "usage: ./deploy.sh <bucket-name> [region]" >&2
  exit 64
fi
if [ ! -f "$SITE/index.html" ]; then
  echo "no site to deploy - run: python run.py && python ui/build.py" >&2
  exit 66
fi

echo "account: $(aws sts get-caller-identity --query Account --output text)"
echo "bucket : s3://$BUCKET  ($REGION)"
echo "source : $SITE"
echo

if ! aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  echo "creating the bucket..."
  if [ "$REGION" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION"
  else
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
      --create-bucket-configuration "LocationConstraint=$REGION"
  fi
fi

echo "allowing public reads..."
aws s3api put-public-access-block --bucket "$BUCKET" \
  --public-access-block-configuration \
  "BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false"

aws s3api put-bucket-policy --bucket "$BUCKET" --policy "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [{
    \"Sid\": \"PublicRead\",
    \"Effect\": \"Allow\",
    \"Principal\": \"*\",
    \"Action\": \"s3:GetObject\",
    \"Resource\": \"arn:aws:s3:::$BUCKET/*\"
  }]
}"

echo "turning on website hosting..."
aws s3api put-bucket-website --bucket "$BUCKET" --website-configuration \
  '{"IndexDocument":{"Suffix":"index.html"},"ErrorDocument":{"Key":"index.html"}}'

echo "uploading..."
# The board is rebuilt on every run, so it must not be cached; the stylesheet
# and the two static pages can be.
aws s3 sync "$SITE" "s3://$BUCKET" --delete \
  --exclude "checks.html" --cache-control "public, max-age=300"
aws s3 cp "$SITE/checks.html" "s3://$BUCKET/checks.html" \
  --cache-control "no-cache" --content-type "text/html; charset=utf-8"

URL="http://$BUCKET.s3-website-$REGION.amazonaws.com"
[ "$REGION" = "us-east-1" ] && URL="http://$BUCKET.s3-website-us-east-1.amazonaws.com"

echo
echo "live at: $URL"
echo
echo "Note: S3 website endpoints are HTTP only. For https:// put CloudFront in"
echo "front of this bucket, which also gets you a cert and a cleaner hostname."
