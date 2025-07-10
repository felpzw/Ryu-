from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController, Controller
from mininet.cli import CLI
from mininet.log import setLogLevel
from mininet.link import TCLink
import time

def run_load_balancer_topo():
    c = RemoteController('c0', ip='127.0.0.1', port=6653)

    net = Mininet(controller=None, switch=OVSSwitch, link=TCLink)

    net.addController(c)

    print("*** Adicionando hosts e switch")
    h1 = net.addHost('h1', ip='10.0.0.1/24', mac='00:00:00:00:00:01')
    h2 = net.addHost('h2', ip='10.0.0.2/24', mac='00:00:00:00:00:02')
    h3 = net.addHost('h3', ip='10.0.0.3/24', mac='00:00:00:00:00:03')
    h4 = net.addHost('h4', ip='10.0.0.4/24', mac='00:00:00:00:00:04')

    s1 = net.addSwitch('s1', protocols='OpenFlow13')

    print("*** Criando links")
    net.addLink(h1, s1)
    net.addLink(h2, s1)
    net.addLink(h3, s1)
    net.addLink(h4, s1)

    print("*** Iniciando rede")
    net.start()

    time.sleep(2)

    h2.cmd('bash -c "echo \'RESPONSE FROM H2\' | python3 -m http.server 80 &"')
    h3.cmd('bash -c "echo \'RESPONSE FROM H3\' | python3 -m http.server 80 &"')
    h4.cmd('bash -c "echo \'RESPONSE FROM H4\' | python3 -m http.server 80 &"')

    print("\n--- Rede Mininet Pronta ---")
    print(f"Controlador Ryu deve estar rodando em {c.ip}:{c.port}")
    print(f"Hosts: h1 (cliente), h2, h3, h4 (servidores backend)")
    print(f"Switch: s1 (OVS, OpenFlow13)")
    print(f"VIP para o balanceamento de carga: 10.0.0.100")
    print("\nNo terminal do Mininet, use 'h1 curl 10.0.0.100' para testar o balanceador.")
    print("Você pode usar 'h2 ping 10.0.0.1' para testar a conectividade básica.")

    CLI(net)

    print("*** Parando rede")
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    run_load_balancer_topo()