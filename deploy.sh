#!/usr/bin/env bash
# Publish out/site/ to an S3 static website.
#
#   ./deploy.sh my-bucket-name [region]
#
# Needs the AWS CLI and credentials with s3:CreateBucket, s3:PutObject,
# s3:PutBucketPolicy and s3:PutBucketWebsite.
#
# READ THIS FIRST: this makes the bucket publicly readable, and data.js
# carries the whole run inlined - consignee names, addresses, ports, weights
# and OC numbers. Anyone with the link, and any crawler that finds it, can
# read all of it.
#
# So this defaults to out/site-demo, the scrambled build, and refuses to
# publish the real one unless you say so:
#
#   ./deploy.sh my-bucket                     # scrambled demo  (safe)
#   ./deploy.sh my-bucket ap-southeast-1 real # the real bundle (deliberate)
#
# Build the demo first with:
#   python run.py && python tools/demo_data.py
#   python ui/build.py --results out/results-demo.json --out out/site-demo
set -euo pipefail

BUCKET="${1:-}"
REGION="${2:-ap-southeast-1}"
WHICH="${3:-demo}"
HERE="$(cd "$(dirname "$0")" && pwd)"

case "$WHICH" in
  demo) SITE="$HERE/out/site-demo" ;;
  real) SITE="$HERE/out/site" ;;
  *) echo "third argument must be 'demo' or 'real', not '$WHICH'" >&2; exit 64 ;;
esac

if [ -z "$BUCKET" ]; then
  echo "usage: ./deploy.sh <bucket-name> [region] [demo|real]" >&2
  exit 64
fi
if [ ! -f "$SITE/index.html" ]; then
  echo "no site at $SITE" >&2
  echo "build it first - see the header of this script" >&2
  exit 66
fi

if [ "$WHICH" = "real" ]; then
  echo "About to publish the REAL bundle - every consignee name, address and"
  echo "OC number - to a world-readable bucket. Type 'publish real data' to go on."
  read -r -p "> " CONFIRM
  [ "$CONFIRM" = "publish real data" ] || { echo "stopped."; exit 1; }
fi

echo "account: $(aws sts get-caller-identity --query Account --output text)"
echo "bucket : s3://$BUCKET  ($REGION)"
echo "source : $SITE  [$WHICH]"
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
# data.js is regenerated on every run, so it must not be cached; the pages,
# the stylesheet and the shared modules can be.
aws s3 sync "$SITE" "s3://$BUCKET" --delete \
  --exclude "data.js" --cache-control "public, max-age=300"
aws s3 cp "$SITE/data.js" "s3://$BUCKET/data.js" \
  --cache-control "no-cache" --content-type "application/javascript; charset=utf-8"

URL="http://$BUCKET.s3-website-$REGION.amazonaws.com"
[ "$REGION" = "us-east-1" ] && URL="http://$BUCKET.s3-website-us-east-1.amazonaws.com"

echo
echo "live at: $URL"
echo
echo "Note: S3 website endpoints are HTTP only. For https:// put CloudFront in"
echo "front of this bucket, which also gets you a cert and a cleaner hostname."
