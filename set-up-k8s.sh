#!/bin/sh

instance=${1:?"Usage: set-up-k8s.sh INSTANCE"}

# Add to docker group, log out
ssh $instance "sudo usermod -aG docker $USER"

rsync -a ~/repos/container-service/scripts $instance:/home/johnflavin/

ssh $instance << EOF
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64 && \
sudo install minikube-linux-amd64 /usr/local/bin/minikube && \
sudo mkdir /home/xnat/tmp && \
sudo mkdir /home/xnat/tomcat/.kube && \
sudo cp -r /home/johnflavin/scripts /home/xnat/tmp/ && \
sudo chown -R tomcat:tomcat /home/xnat/tmp && \
sudo chown -R tomcat:tomcat /home/xnat/tomcat/.kube && \
sudo -u tomcat /usr/local/bin/minikube start --mount --mount-string /opt/data:/opt/data && \
sudo -u tomcat /home/xnat/tmp/scripts/set_up_kubernetes.sh /home/xnat/tomcat/.kube/config
EOF
