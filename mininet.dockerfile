FROM ubuntu:24.04

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    dnsutils \
    ifupdown \
    iproute2 \
    iptables \
    iputils-ping \
    mininet \
    net-tools \
    openvswitch-switch \
    openvswitch-testcontroller \
    tcpdump \
    vim \
    x11-xserver-utils \
    xterm \
    wget \
 && rm -rf /var/lib/apt/lists/* \
 && touch /etc/network/interfaces

WORKDIR /code
COPY mininet_topology.py /code/
COPY mininet-entrypoint.sh /
RUN chmod +x /mininet-entrypoint.sh
RUN ln /usr/bin/ovs-testcontroller /usr/bin/controller

EXPOSE 6633 6653 6640

ENTRYPOINT ["/mininet-entrypoint.sh"]
