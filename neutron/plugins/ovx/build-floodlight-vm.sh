#!/bin/bash

set -e

# Build VM image that starts FloodLight at boot.

# Ubuntu cloud image to use
#IMAGE=precise-server-cloudimg-amd64-disk1.img
#URL=https://cloud-images.ubuntu.com/precise/current/$IMAGE
#IMAGE=saucy-server-cloudimg-amd64-disk1.img
#URL=https://cloud-images.ubuntu.com/saucy/current/$IMAGE
IMAGE=ubuntu-14.04-server-cloudimg-amd64-disk1.img
URL=http://cloud-images.ubuntu.com/releases/14.04/release/$IMAGE
# Old and new size of root filesystem (in sectors)
OLD_SIZE=4192256
NEW_SIZE=5192256

# Install dependencies
#   * qemu-utils needed for qemu-nbd
#   * util-linux needed for sfdisk
sudo apt-get -y -q install qemu-utils util-linux

# Load nbd kernel module
sudo modprobe nbd

# Download image
if [ ! -f $IMAGE ]; then
    curl -O $URL
fi

# Adding 500 MB so we can install Java
# First resize the image, then the file system
qemu-img resize $IMAGE +500M
# Sometimes qemu-nbd wants the full path to the image
sudo qemu-nbd --connect=/dev/nbd0 `pwd`/$IMAGE
PTABLE=`mktemp`
sudo sfdisk -d /dev/nbd0 > $PTABLE
sed 's/4192256/5192256/' $PTABLE
sudo sfdisk /dev/nbd0 < $PTABLE
rm $PTABLE
sudo e2fsck -f /dev/nbd0p1
sudo resize2fs /dev/nbd0p1

# Mount image and chroot to it
TMP_DIR=`mktemp -d`
sudo mount /dev/nbd0p1 $TMP_DIR
sudo mv $TMP_DIR/etc/resolv.conf $TMP_DIR/etc/resolv.conf.original
sudo cp /etc/resolv.conf $TMP_DIR/etc/
sudo mount -t proc proc $TMP_DIR/proc/
sudo mount -t sysfs sys $TMP_DIR/sys/
sudo mount -o bind /dev $TMP_DIR/dev/

# Install java
sudo chroot $TMP_DIR apt-get -q update
sudo chroot $TMP_DIR apt-get install -y -q build-essential default-jdk ant python-dev openssh-server

# Install FloodLight 0.90
sudo chroot $TMP_DIR curl -o /usr/local/src/floodlight-0.90.tar.gz http://floodlight-download.projectfloodlight.org/files/floodlight-source-0.90.tar.gz
sudo chroot $TMP_DIR tar xzvf /usr/local/src/floodlight-0.90.tar.gz -C /usr/local/src
sudo chroot $TMP_DIR ant -buildfile /usr/local/src/floodlight-0.90/build.xml

sudo chroot $TMP_DIR bash -c 'cat > /etc/init/floodlight.conf << EOF
description "FloodLight OpenFlow Controller"

start on runlevel [2345]
stop on runlevel [!2345]

script
  exec /usr/bin/java -jar /usr/local/src/floodlight-0.90/target/floodlight.jar > /var/log/floodlight.log 2>&1 &
end script
EOF'

# Unmount & remove tmp dir
sudo rm $TMP_DIR/etc/resolv.conf
sudo mv $TMP_DIR/etc/resolv.conf.original $TMP_DIR/etc/resolv.conf
sudo umount $TMP_DIR/proc
sudo umount $TMP_DIR/sys
sudo umount $TMP_DIR/dev
sudo umount $TMP_DIR
rmdir $TMP_DIR
sudo qemu-nbd --disconnect /dev/nbd0
