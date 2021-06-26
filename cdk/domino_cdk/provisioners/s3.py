from typing import List

import aws_cdk.aws_iam as iam
from aws_cdk import core as cdk
from aws_cdk.aws_kms import Key
from aws_cdk.aws_s3 import Bucket, BucketEncryption

from domino_cdk.config import S3


class DominoS3Provisioner:
    def __init__(self, scope: cdk.Construct, construct_id: str, name: str, s3: List[S3], nest: bool, **kwargs):
        self.scope = cdk.NestedStack(scope, construct_id, **kwargs) if nest else scope
        self.provision_buckets(name, s3)

    def provision_buckets(self, name: str, s3: List[S3]):
        self.buckets = {}
        for bucket, attrs in s3.buckets.items():
            use_sse_kms_key = False
            if attrs.sse_kms_key_id:
                use_sse_kms_key = True
                sse_kms_key = Key.from_key_arn(self, f"{bucket}-kms-key", attrs.sse_kms_key_id)

            self.buckets[bucket] = Bucket(
                self.scope,
                bucket,
                bucket_name=f"{name}-{bucket}",
                auto_delete_objects=attrs.auto_delete_objects and attrs.removal_policy_destroy,
                removal_policy=cdk.RemovalPolicy.DESTROY if attrs.removal_policy_destroy else cdk.RemovalPolicy.RETAIN,
                enforce_ssl=True,
                bucket_key_enabled=use_sse_kms_key,
                encryption_key=(sse_kms_key if use_sse_kms_key else None),
                encryption=(BucketEncryption.KMS if use_sse_kms_key else BucketEncryption.S3_MANAGED),
            )
            self.buckets[bucket].add_to_resource_policy(
                iam.PolicyStatement(
                    sid="DenyIncorrectEncryptionHeader",
                    effect=iam.Effect.DENY,
                    principals=[iam.ArnPrincipal("*")],
                    actions=[
                        "s3:PutObject",
                    ],
                    resources=[f"{self.buckets[bucket].bucket_arn}/*"],
                    conditions={
                        "StringNotEquals": {
                            "s3:x-amz-server-side-encryption": "aws:kms" if use_sse_kms_key else "AES256"
                        }
                    },
                )
            )
            self.buckets[bucket].add_to_resource_policy(
                iam.PolicyStatement(
                    sid="DenyUnEncryptedObjectUploads",
                    effect=iam.Effect.DENY,
                    principals=[iam.ArnPrincipal("*")],
                    actions=[
                        "s3:PutObject",
                    ],
                    resources=[f"{self.buckets[bucket].bucket_arn}/*"],
                    conditions={"Null": {"s3:x-amz-server-side-encryption": "true"}},
                )
            )

            cdk.CfnOutput(self.scope, f"{bucket}-output", value=self.buckets[bucket].bucket_name)
