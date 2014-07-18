#!/bin/sh

IMAGE=ubuntu-14.04-server-cloudimg-amd64-disk1.img
URL=http://cloud-images.ubuntu.com/releases/14.04/release/$IMAGE

# Download image
if [ ! -f $IMAGE]; then
    wget $URL
fi

# Adding 500 MB so we can install Java
qemu-img resize $IMAGE +500M
sudo qemu-nbd --connect=/dev/nbd0 $IMAGE

sudo sfdisk -d /dev/nbd0 > s
echo 'Please edit the file partitions'
read a
sudo e2fsck -f /dev/nbd0p1
sudo resize2fs /dev/nbd0p1
rm s

# Mount image and chroot to it
sudo mount /dev/nbd0p1 /mnt
sudo chroot /mnt
mount -t proc proc proc/
mount -t sysfs sys sys/
mount -o bind /dev dev/

apt-get -q update
sudo apt-get install -y -q build-essential default-jdk ant python-dev openssh-server

# # Unattended Oracle Java install
# echo debconf shared/accepted-oracle-license-v1-1 select true | sudo debconf-set-selections
# #echo debconf shared/accepted-oracle-license-v1-1 seen true | sudo debconf-set-selections
# add-apt-repository -y ppa:webupd8team/java
# apt-get -q update
# apt-get -y -q install oracle-java8-installer ant

# Install FloodLight 0.90
cd /usr/local/bin
wget http://floodlight-download.projectfloodlight.org/files/floodlight-source-0.90.tar.gz
tar xzf floodlight-source-0.90.tar.gz
cd floodlight-0.90
ant

cat > /etc/rc.local <<EOF
#!/bin/sh -e

java -jar /usr/local/src/floodlight-0.90/target/floodlight.jar > /var/log/floodlight.log &

exit 0

EOF

chmod + /etc/rc.local

# Get out of chroot
exit 0
