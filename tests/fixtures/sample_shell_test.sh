#!/bin/bash
# Sample test script for validation testing

set -e

POOL="test_pool"
IMAGE="test_img"

# Create pool and image
ceph osd pool create $POOL 32
ceph osd pool application enable $POOL rbd
rbd create $IMAGE --size 1024 --pool $POOL
rbd create $IMAGE --size 1024 --pool $POOL  # duplicate

# Destructive operation without proper guard
ceph osd pool delete $POOL $POOL --yes-i-really-really-mean-it

# Invalid flag
ceph osd pool create another_pool --nonexistent-flag 5

# Cleanup
rbd rm $IMAGE --pool $POOL
ceph osd pool delete $POOL $POOL --yes-i-really-really-mean-it
