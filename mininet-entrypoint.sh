#!/usr/bin/env bash

service openvswitch-switch start
ovs-vsctl set-manager ptcp:6640

python3 "$@"

service openvswitch-switch stop
