from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController, Controller
from mininet.cli import CLI
from mininet.log import setLogLevel
from mininet.link import TCLink
import socket
import time
from mininet.link import Intf

ryu_ipaddr = socket.gethostbyname('sdn_ryu')

def run_load_balancer_topo():
    controller = RemoteController('c0', ip=ryu_ipaddr, port=6653)

    net = Mininet(controller=None, switch=OVSSwitch, link=TCLink)

    print(f"*** Configurando controlador no endereço {ryu_ipaddr}")
    net.addController(controller)

    print("*** Adicionando hosts e switch")
    client1 = net.addHost('client1', ip='10.0.0.1/24', mac='00:00:00:00:00:01')
    client2 = net.addHost('client2', ip='10.0.0.2/24', mac='00:00:00:00:00:02')

    host1 = net.addHost('host1', ip='10.0.0.3/24', mac='00:00:00:00:01:01')
    host2 = net.addHost('host2', ip='10.0.0.4/24', mac='00:00:00:00:01:02')
    host3 = net.addHost('host3', ip='10.0.0.5/24', mac='00:00:00:00:01:03')
    host4 = net.addHost('host4', ip='10.0.0.6/24', mac='00:00:00:00:01:04')

    s1 = net.addSwitch('s1', protocols='OpenFlow13')
    # Link switch to physical container network interface
    Intf('eth0', node=s1)

    print("*** Criando links")
    net.addLink(client1, s1)
    net.addLink(client2, s1)
    net.addLink(host1, s1)
    net.addLink(host2, s1)
    net.addLink(host3, s1)
    net.addLink(host4, s1)

    print("*** Iniciando rede")
    net.start()

    time.sleep(2)

    host1.cmd('bash -c "echo \'RESPONSE FROM H1\' | python3 -m http.server 80 &"')
    host2.cmd('bash -c "echo \'RESPONSE FROM H2\' | python3 -m http.server 80 &"')
    host3.cmd('bash -c "echo \'RESPONSE FROM H3\' | python3 -m http.server 80 &"')
    host4.cmd('bash -c "echo \'RESPONSE FROM H4\' | python3 -m http.server 80 &"')

    print("\n--- Rede Mininet Pronta ---")
    print(f"Controlador Ryu deve estar rodando em {controller.ip}:{controller.port}")
    print(f"Hosts: client1, client2 (clientes), host1, host2, host3, host4 (servidores backend)")
    print(f"Switch: s1 (OVS, OpenFlow13)")
    print(f"VIP para o balanceamento de carga: 10.0.0.100")
    print("\nNo terminal do Mininet, use 'client1 curl 10.0.0.100' para testar o balanceador.")
    print("Você pode usar 'host1 ping 10.0.0.1' para testar a conectividade básica.")

    CLI(net)

    print("*** Parando rede")
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    run_load_balancer_topo()
