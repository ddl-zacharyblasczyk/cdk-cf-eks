from typing import List

import aws_cdk.aws_iam as iam
from aws_cdk import core as cdk


class DominoEksIamProvisioner:
    def __init__(
        self,
        scope: cdk.Construct,
    ) -> None:
        self.scope = scope

    def provision(self, name: str, cluster_name: str, r53_zone_ids: List[str]):
        asg_group_statement = iam.PolicyStatement(
            actions=[
                "autoscaling:DescribeAutoScalingInstances",
                "autoscaling:SetDesiredCapacity",
                "autoscaling:TerminateInstanceInAutoScalingGroup",
            ],
            resources=["*"],
            conditions={"StringEquals": {"autoscaling:ResourceTag/eks:cluster-name": cluster_name}},
        )

        autoscaler_policy = iam.ManagedPolicy(
            self.scope,
            "autoscaler",
            managed_policy_name=f"{name}-autoscaler",
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "autoscaling:DescribeAutoScalingGroups",
                        "autoscaling:DescribeLaunchConfigurations",
                        "autoscaling:DescribeTags",
                        "ec2:DescribeLaunchTemplateVersions",
                    ],
                    resources=["*"],
                ),
                asg_group_statement,
            ],
        )

        if r53_zone_ids:
            route53_policy = iam.ManagedPolicy(
                self.scope,
                "route53",
                managed_policy_name=f"{name}-route53",
                statements=[
                    iam.PolicyStatement(
                        actions=["route53:ListHostedZones"],
                        resources=["*"],
                    ),
                    iam.PolicyStatement(
                        actions=[
                            "route53:ChangeResourceRecordSets",
                            "route53:ListResourceRecordSets",
                        ],
                        resources=[f"arn:aws:route53:::hostedzone/{zone_id}" for zone_id in r53_zone_ids],
                    ),
                ],
            )

        ecr_policy = iam.ManagedPolicy(
            self.scope,
            f"{name}-DominoEcrRestricted",
            managed_policy_name=f"{name}-DominoEcrRestricted",
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.DENY,
                    actions=[
                        "ecr:BatchCheckLayerAvailability",
                        "ecr:BatchGetImage",
                        "ecr:GetDownloadUrlForLayer",
                    ],
                    conditions={"StringNotEqualsIfExists": {"ecr:ResourceTag/domino-deploy-id": name}},
                    resources=[f"arn:aws:ecr:*:{self.scope.account}:*"],
                ),
            ],
        )

        managed_policies = [
            ecr_policy,
            autoscaler_policy,
            iam.ManagedPolicy.from_aws_managed_policy_name('AmazonEKSWorkerNodePolicy'),
            iam.ManagedPolicy.from_aws_managed_policy_name('AmazonEC2ContainerRegistryReadOnly'),
            iam.ManagedPolicy.from_aws_managed_policy_name('AmazonEKS_CNI_Policy'),
            iam.ManagedPolicy.from_aws_managed_policy_name('AmazonSSMManagedInstanceCore'),
        ]
        if r53_zone_ids:
            managed_policies.append(route53_policy)

        return iam.Role(
            self.scope,
            f'{name}-NG',
            role_name=f"{name}-NG",
            assumed_by=iam.ServicePrincipal('ec2.amazonaws.com'),
            managed_policies=managed_policies,
        )
