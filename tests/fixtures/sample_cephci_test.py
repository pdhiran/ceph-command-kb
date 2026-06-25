"""Sample cephci-style test for validation testing."""

import logging

log = logging.getLogger(__name__)


def run(ceph_cluster, **kwargs):
    """Test RBD mirror setup and failover."""
    config = kwargs.get("config", {})
    pool_name = config.get("pool_name", "test_mirror_pool")
    image_name = config.get("image_name", "test_image")

    # Setup
    ceph_cluster.shell(cmd=f"ceph osd pool create {pool_name} 32")
    ceph_cluster.shell(cmd=f"ceph osd pool application enable {pool_name} rbd")
    ceph_cluster.shell(cmd=f"rbd create {image_name} --size 1024 --pool {pool_name}")
    ceph_cluster.shell(cmd=f"rbd mirror pool enable {pool_name} image")
    ceph_cluster.shell(cmd=f"rbd mirror image enable {pool_name}/{image_name}")

    # Write some data
    ceph_cluster.shell(cmd=f"rbd bench --io-type write --io-size 4096 {pool_name}/{image_name}")

    # Check mirror status
    ceph_cluster.shell(cmd=f"rbd mirror image status {pool_name}/{image_name}")
    ceph_cluster.shell(cmd="ceph health")

    # Failover test
    ceph_cluster.shell(cmd=f"rbd mirror image demote {pool_name}/{image_name}")
    ceph_cluster.shell(cmd=f"rbd mirror image promote {pool_name}/{image_name} --force")

    # Duplicate health check
    ceph_cluster.shell(cmd="ceph -s")
    ceph_cluster.shell(cmd="ceph -s")

    # No cleanup - pool and image not deleted
    return 0
