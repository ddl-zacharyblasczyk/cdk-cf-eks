from dataclasses import dataclass
from typing import Dict, List

from domino_cdk.config.util import IngressRule, check_leavins, from_loader


@dataclass
class EKS:
    """
    version: "1.20" - Kubernetes version for EKS cluster. _MUST BE A STRING_!
    control_plane_access_cidrs: ["0.0.0.0/0", ...] - List of CIDRs with access to the control plane
                                                     Only valid when private_api is flase
    private_api: true/false - Limits Kubernetes API access to the VPC. Access must be through a
                              bastion, peered network, or other in-VPC resource.
    max_nodegroup_azs: 3 - Will provision nodegroups in up to this many availability zones.
    global_node_labels: some-label: "true"  - Labels to apply to all kubernetes nodes
    global_node_tags: some-tags: "true"  - Labels to apply to all kubernetes nodes
    secrets_encryption_key_arn: ARN  - KMS key arn to encrypt kubernetes secrets. A new key will be created if omitted.
    """

    @dataclass
    class NodegroupBase:
        # Docs are combined since I haven't figured out a good way of placing them.
        # I would kind of prefer ng docs before managed, managed docs right below the
        # managed_nodegroups key, and the unmanaged similarly right below it. However,
        # configuring it this way seemed to place the empty managed value in the template
        # after the doc string for some bizarre reason. TODO. "..." is to prevent it from not
        # starting the empty lines with comments. Just personally bugs me.
        """
        Nodegroup Configuration:
        disk_size: 1000 - Size in GB for disk on nodes in nodegroup
        key_name: some-key-pair - Pre-existing AWS key pair to configure for instances in the nodegorup
        min_size: 1 - Minimum node count for nodegroup. Can't be 0 on managed nodegroups.
        max_size: 10 - Maximum limit for node count in node gorup
        ami_id: ami-123abc - AMI to use for nodegroup, empty/null will default to the current EKS AMI.
                             When specifying an AMI, you MUST specify a custom user_data script to join
                             the node to the cluster, and this script must do any sort of node setup that
                             is desired. Additionally, some nodegroup options (ie labels, taints,
                             ssm_agent) are only allowed when using the default EKS AMI, as they may not
                             be compatible with other AMIs. When specifying an AMI, you must implement
                             those options manually via your user_data script.
        user_data: ... - Custom script for user_data, ran by cloud_init on node startup. When using the
                         default EKS AMI, this does not replace the default user_data. Your custom script
                         will be injected _before_ the default one, and both will be ran. However, when
                         specifying a custom AMI, this will be the *only* user_data script in use.
        instance_types: ["m5.2xlarge", "m5.4xlarge"] - Instance types available to nodegroup
        labels: some-label: "true" - Labels to apply to all nodes in nodegroup
        tags: some-tag: "true" - Tags to apply to all nodes in nodegroup
        ...
        Managed nodegroup-specific options:
        spot: true/false - Use spot instances, may affect reliability/availability of nodegroup
        desired_size: 1 - Preferred size of nodegroup
        ...
        Unmanaged nodegroup-specific options:
        gpu: true/false - Setup GPU instance support
        nodegroup_access_cidrs: ["x.x.x.x/x", ...] - CIDRs with SSH access to unmanaged nodes
                                                     (adds to security group w/port 22)
        ssm_agent: true/false - Install SSM agent (ie for console access via aws web ui)
        taints: some-taint: "true" - Taints to apply to all nodes in nodegroup
                                     ie to taint gpu nodes, etc.)
        ingress_ports: List of ingress rules to nodegroup instances in the following format:
                       - name: API
                         from_port: 22
                         to_port: 22
                         protocol: TCP
                         ip_cidrs:
                         - 0.0.0.0/0
        """

        ssm_agent: bool
        disk_size: int
        key_name: str
        min_size: int
        max_size: int
        ami_id: str
        user_data: str
        instance_types: List[str]
        labels: Dict[str, str]
        tags: Dict[str, str]

        def base_load(ng):
            return {
                "ssm_agent": ng.pop("ssm_agent"),
                "disk_size": ng.pop("disk_size"),
                "key_name": ng.pop("key_name", None),
                "min_size": ng.pop("min_size"),
                "max_size": ng.pop("max_size"),
                "ami_id": ng.pop("ami_id", None),
                "user_data": ng.pop("user_data", None),
                "instance_types": ng.pop("instance_types"),
                "labels": ng.pop("labels"),
                "tags": ng.pop("tags"),
            }

    @dataclass
    class ManagedNodegroup(NodegroupBase):
        spot: bool
        desired_size: int

        @classmethod
        def load(cls, ng):
            out = cls(**cls.base_load(ng), spot=ng.pop("spot"), desired_size=ng.pop("desired_size"))
            check_leavins("managed nodegroup attribute", "config.eks.unmanaged_nodegroups", ng)
            return out

    @dataclass
    class UnmanagedNodegroup(NodegroupBase):
        gpu: bool
        imdsv2_required: bool
        taints: Dict[str, str]
        ingress_ports: List[IngressRule]

        @classmethod
        def load(cls, ng):
            out = cls(
                **cls.base_load(ng),
                gpu=ng.pop("gpu"),
                imdsv2_required=ng.pop("imdsv2_required"),
                taints=ng.pop("taints", {}),
                ingress_ports=IngressRule.load_rules("config.eks.unmanaged_nodegroups", ng.pop("ingress_ports")),
            )
            check_leavins("unmanaged nodegroup attribute", "config.eks.unmanaged_nodegroups", ng)
            return out

    version: str
    control_plane_access_cidrs: List[str]
    private_api: bool
    max_nodegroup_azs: int
    global_node_labels: Dict[str, str]
    global_node_tags: Dict[str, str]
    secrets_encryption_key_arn: str
    managed_nodegroups: Dict[str, ManagedNodegroup]
    unmanaged_nodegroups: Dict[str, UnmanagedNodegroup]

    def __post_init__(self):
        errors = []

        def check_ami_exceptions(ng_name: str, ami_id: str, user_data: str, incompatible_options: bool = False):
            if ami_id and not user_data:
                errors.append(f"{ng_name}: User data must be provided when specifying a custom AMI")
            if ami_id and incompatible_options:
                errors.append(
                    f"{ng_name}: ssm_agent, labels and taints cannot be automatically configured when specifying a custom AMI. "
                    "You need to configure all of this using user_data."
                )

        for name, ng in self.managed_nodegroups.items():
            error_name = f"Managed nodegroup [{name}]"
            check_ami_exceptions(error_name, ng.ami_id, ng.user_data, (ng.ssm_agent or ng.labels))
            if ng.min_size == 0:
                errors.append(
                    f"Error: {error_name} has min_size of 0. Only unmanaged nodegroups support min_size of 0."
                )
        for name, ng in self.unmanaged_nodegroups.items():
            error_name = f"Unmanaged nodegroup [{name}]"
            check_ami_exceptions(error_name, ng.ami_id, ng.user_data, (ng.ssm_agent or ng.labels or ng.taints))

        if self.control_plane_access_cidrs and self.private_api:
            errors.append("Cannot use 'control_plane_access_cidrs' with 'private_api'")

        if errors:
            raise ValueError(errors)

    @staticmethod
    def from_0_0_0(c: dict):
        def remap_mi(ng, unmanaged=False):
            if unmanaged:
                ng["imdsv2_required"] = False
                ng["ingress_ports"] = {}
            return {**ng.pop("machine_image", {}), **ng}

        return from_loader(
            "config.eks",
            EKS(
                version=c.pop("version"),
                control_plane_access_cidrs=[],
                private_api=c.pop("private_api"),
                max_nodegroup_azs=c.pop("max_nodegroup_azs"),
                global_node_labels=c.pop("global_node_labels"),
                global_node_tags=c.pop("global_node_tags"),
                managed_nodegroups={
                    name: EKS.ManagedNodegroup.load(remap_mi(ng))
                    for name, ng in c.pop("managed_nodegroups", {}).items()
                },
                unmanaged_nodegroups={
                    name: EKS.UnmanagedNodegroup.load(remap_mi(ng, True))
                    for name, ng in c.pop("nodegroups", {}).items()
                },
                secrets_encryption_key_arn=None,
            ),
            c,
        )

    @staticmethod
    def from_0_0_1(c: dict):
        return from_loader(
            "config.eks",
            EKS(
                version=c.pop("version"),
                control_plane_access_cidrs=c.pop("control_plane_access_cidrs"),
                private_api=c.pop("private_api"),
                secrets_encryption_key_arn=c.pop("secrets_encryption_key_arn", None),
                max_nodegroup_azs=c.pop("max_nodegroup_azs"),
                global_node_labels=c.pop("global_node_labels"),
                global_node_tags=c.pop("global_node_tags"),
                managed_nodegroups={
                    name: EKS.ManagedNodegroup.load(ng) for name, ng in c.pop("managed_nodegroups", {}).items()
                },
                unmanaged_nodegroups={
                    name: EKS.UnmanagedNodegroup.load(ng) for name, ng in c.pop("unmanaged_nodegroups", {}).items()
                },
            ),
            c,
        )