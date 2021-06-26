from os.path import isfile
from re import MULTILINE
from re import split as re_split

import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_eks as eks
import aws_cdk.aws_iam as iam
import aws_cdk.aws_lambda as aws_lambda
from aws_cdk import core as cdk
from aws_cdk.lambda_layer_awscli import AwsCliLayer
from aws_cdk.lambda_layer_kubectl import KubectlLayer
from requests import get as requests_get
from yaml import safe_load as yaml_safe_load

manifests = [
    [
        "calico",
        "https://raw.githubusercontent.com/aws/amazon-vpc-cni-k8s/v1.7.10/config/master/calico.yaml",
    ]
]


# Currently this just installs calico directly via manifest, but will
# ultimately become a lambda that handles various tasks (calico,
# deprovisoning efs backups/route53, tagging the eks cluster until
# the CloudFormation api supports it, etc.)
class DominoAwsConfigurator:
    def __init__(self, scope: cdk.Construct, eks_cluster: eks.Cluster, vpc: ec2.Vpc):
        self.scope = scope
        self.eks_cluster = eks_cluster
        self.vpc = vpc

        self.install_calico()

    def install_calico(self):
        # This produces an obnoxious diff on every subsequent run
        # Using a helm chart does not, so we should switch to that
        # However, we need to figure out how to get the helm chart
        # accessible by the CDK lambda first. Not clear how to give
        # s3 perms to it programmatically, and while ECR might be
        # an option it also doesn't seem like there's a way to push
        # the chart with existing api calls.
        # Probably need to do some custom lambda thing.
        for manifest in manifests:
            filename = f"{manifest[0]}.yaml"
            if isfile(filename):
                with open(filename) as f:
                    manifest_text = f.read()
            else:
                manifest_text = requests_get(manifest[1]).text
            loaded_manifests = [yaml_safe_load(i) for i in re_split("^---$", manifest_text, flags=MULTILINE) if i]
            crds = eks.KubernetesManifest(
                self.scope,
                "calico-crds",
                cluster=self.eks_cluster,
                manifest=[crd for crd in loaded_manifests if crd["kind"] == "CustomResourceDefinition"],
            )
            non_crds = eks.KubernetesManifest(
                self.scope,
                "calico",
                cluster=self.eks_cluster,
                manifest=[notcrd for notcrd in loaded_manifests if notcrd["kind"] != "CustomResourceDefinition"],
            )
            non_crds.node.add_dependency(crds)
