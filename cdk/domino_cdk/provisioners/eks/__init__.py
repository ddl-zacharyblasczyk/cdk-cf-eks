from typing import List, Dict

import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_eks as eks
import aws_cdk.aws_iam as iam
from aws_cdk import core as cdk
from aws_cdk.aws_s3 import Bucket

from domino_cdk.config import EKS
from domino_cdk.provisioners.eks.eks_cluster import DominoEksClusterProvisioner
from domino_cdk.provisioners.eks.eks_iam import DominoEksIamProvisioner
from domino_cdk.provisioners.eks.eks_nodegroup import DominoEksNodegroupProvisioner
from domino_cdk.provisioners.eks.eks_iam_roles_for_k8s import DominoEksK8sIamRolesProvisioner


class DominoEksProvisioner:
    def __init__(
        self,
        scope: cdk.Construct,
        construct_id: str,
        name: str,
        eks_cfg: EKS,
        vpc: ec2.Vpc,
        private_subnet_name: str,
        bastion_sg: ec2.SecurityGroup,
        r53_zone_ids: List[str],
        nest: bool,
        buckets: Dict[str, Bucket],
        **kwargs,
    ) -> None:
        self.scope = cdk.NestedStack(scope, construct_id, **kwargs) if nest else scope

        eks_version = getattr(eks.KubernetesVersion, f"V{eks_cfg.version.replace('.', '_')}")

        self.cluster = DominoEksClusterProvisioner(self.scope).provision(
            name, eks_version, eks_cfg.private_api, eks_cfg.secrets_encryption_key_arn, vpc, bastion_sg
        )
        ng_role = DominoEksIamProvisioner(self.scope).provision(name, self.cluster.cluster_name, r53_zone_ids)
        DominoEksNodegroupProvisioner(
            self.scope, self.cluster, ng_role, name, eks_cfg, eks_version, vpc, private_subnet_name, bastion_sg
        )
        DominoEksK8sIamRolesProvisioner(self.scope).provision(name, self.cluster, buckets)
