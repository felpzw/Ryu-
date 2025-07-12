from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER, DEAD_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, tcp, arp, ether_types
import subprocess

class SimpleLoadBalancer(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleLoadBalancer, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.datapaths = {}
        self.backend_servers = {
            '10.0.0.3': {'mac': None, 'connections': 0},
            '10.0.0.4': {'mac': None, 'connections': 0},
            '10.0.0.5': {'mac': None, 'connections': 0},
            '10.0.0.6': {'mac': None, 'connections': 0},
        }
        self.least_connections_backend = None
        self.flow_to_backend = {}
        self.VIP = '10.0.0.100'
        self.VIRTUAL_MAC_FOR_VIP = '0A:0A:0A:0A:0A:0A'

    def health_check(ip):
        try:
            subprocess.check_output(['ping', '-c', '1', ip])
            return True
        except subprocess.CalledProcessError:
            return False

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        self.datapaths[datapath.id] = datapath
        self.mac_to_port.setdefault(datapath.id, {})
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)
        self.logger.info(f"Switch {datapath.id} conectado. Regra table-miss instalada.")

    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                     priority=priority, match=match,
                                     instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                     match=match, instructions=inst)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        if ev.msg.msg_len < ev.msg.total_len:
            self.logger.debug("packet truncated: only %s of %s bytes",
                              ev.msg.msg_len, ev.msg.total_len)
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']
        pkt = packet.Packet(msg.data)
        eth_pkt = pkt.get_protocols(ethernet.ethernet)[0]

        if eth_pkt.ethertype == 35020 or eth_pkt.ethertype == 34825:
             return

        dst = eth_pkt.dst
        src = eth_pkt.src
        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        self.logger.info("Packet-in: switch=%s src_mac=%s dst_mac=%s in_port=%s", dpid, src, dst, in_port)

        _arp = pkt.get_protocols(arp.arp)
        if _arp:
            arp_pkt = _arp[0]
            if arp_pkt.opcode == arp.ARP_REQUEST and arp_pkt.dst_ip == self.VIP:
                self.logger.info(f"ARP Request for VIP {self.VIP} received from {arp_pkt.src_ip} on port {in_port}")
                self.handle_arp_request(datapath, in_port, eth_pkt, arp_pkt)
                return

        _ipv4 = pkt.get_protocols(ipv4.ipv4)
        if _ipv4:
            ip_pkt = _ipv4[0]
            src_ip = ip_pkt.src
            dst_ip = ip_pkt.dst
            proto = ip_pkt.proto

            self.logger.info(f"IP Packet: src_ip={src_ip}, dst_ip={dst_ip}, proto={proto}")

            if dst_ip == self.VIP:
                self.logger.info(f"Pacote para o VIP {self.VIP} recebido. Aplicando balanceamento de carga.")
                min_connections = float('inf')
                chosen_backend_ip = None

                for ip, data in self.backend_servers.items():
                    if not self.health_check(ip):
                        self.logger.info(f"Backend {ip} down. Roteando para próximo host...")
                        continue
                    if data['connections'] < min_connections:
                        min_connections = data['connections']
                        chosen_backend_ip = ip

                if chosen_backend_ip:
                    self.backend_servers[chosen_backend_ip]['connections'] += 1
                    self.logger.info(f"Backend escolhido: {chosen_backend_ip} (conexões: {self.backend_servers[chosen_backend_ip]['connections']})")

                    backend_mac = self.backend_servers[chosen_backend_ip]['mac']
                    if not backend_mac:
                        last_octet = chosen_backend_ip.split('.')[-1]
                        backend_mac = f"00:00:00:00:00:{int(last_octet):02x}"
                        self.backend_servers[chosen_backend_ip]['mac'] = backend_mac
                        self.logger.warning(f"MAC para {chosen_backend_ip} inferido como {backend_mac}. Confirme que isso corresponde à sua topologia Mininet.")

                    if self.backend_servers[chosen_backend_ip]['mac'] is None:
                        self.backend_servers[chosen_backend_ip]['mac'] = backend_mac

                    out_port_to_backend = self.mac_to_port[dpid].get(backend_mac)

                    if not out_port_to_backend:
                        if dpid == 1:
                            if chosen_backend_ip == '10.0.0.3': out_port_to_backend = 3
                            elif chosen_backend_ip == '10.0.0.4': out_port_to_backend = 4
                            elif chosen_backend_ip == '10.0.0.5': out_port_to_backend = 5
                            elif chosen_backend_ip == '10.0.0.6': out_port_to_backend = 6
                        
                        if not out_port_to_backend:
                            self.logger.error(f"Não foi possível determinar a porta de saída para o backend {chosen_backend_ip} (MAC: {backend_mac}) no switch {dpid}. Descartando pacote.")
                            return

                    match_client_to_backend = parser.OFPMatch(
                        eth_type=ether_types.ETH_TYPE_IP,
                        ipv4_src=src_ip,
                        ipv4_dst=self.VIP,
                    )
                    actions_client_to_backend = [
                        parser.OFPActionSetField(ipv4_dst=chosen_backend_ip),
                        parser.OFPActionSetField(eth_dst=backend_mac),
                        parser.OFPActionOutput(out_port_to_backend)
                    ]
                    self.add_flow(datapath, 10, match_client_to_backend, actions_client_to_backend, msg.buffer_id)
                    self.logger.info(f"Fluxo instalado: {src_ip} -> {self.VIP} (encaminhado para {chosen_backend_ip}) no switch {dpid}")

                    match_backend_to_client = parser.OFPMatch(
                        eth_type=ether_types.ETH_TYPE_IP,
                        ipv4_src=chosen_backend_ip,
                        ipv4_dst=src_ip,
                    )
                    client_port = in_port
                    actions_backend_to_client = [
                        parser.OFPActionSetField(ipv4_src=self.VIP),
                        parser.OFPActionSetField(eth_src=self.VIRTUAL_MAC_FOR_VIP),
                        parser.OFPActionOutput(client_port)
                    ]
                    self.add_flow(datapath, 10, match_backend_to_client, actions_backend_to_client, None)
                    self.logger.info(f"Fluxo de retorno instalado: {chosen_backend_ip} -> {src_ip} (encaminhado via {self.VIP}) no switch {dpid}")

                    data = msg.data
                    actions_initial_packet = [
                        parser.OFPActionSetField(ipv4_dst=chosen_backend_ip),
                        parser.OFPActionSetField(eth_dst=backend_mac),
                        parser.OFPActionOutput(out_port_to_backend)
                    ]
                    out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                              in_port=in_port, actions=actions_initial_packet, data=data)
                    datapath.send_msg(out)
                    self.logger.info(f"primeiro pacote encaminhado para {chosen_backend_ip}")
                else:
                    self.logger.warning("Sem server backend")
            else:
                self.logger.info(f"Pacote IP: src={src}, dst={dst} encaminhado")
                self.forward_l2_packet(msg, datapath, ofproto, parser, in_port, dst)
        else:
            self.logger.info(f"Pacote não IP/ARP: src={src}, dst={dst} encaminhado")
            self.forward_l2_packet(msg, datapath, ofproto, parser, in_port, dst)

    def handle_arp_request(self, datapath, in_port, eth_pkt, arp_pkt):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        hwtype = 1
        proto = 0x0800
        hlen = 6
        plen = 4
        opcode = arp.ARP_REPLY
        arp_reply = packet.Packet()
        arp_reply.add_protocol(ethernet.ethernet(dst=eth_pkt.src,
                                                 src=self.VIRTUAL_MAC_FOR_VIP,
                                                 ethertype=0x0806))
        arp_reply.add_protocol(arp.arp(hwtype=hwtype, proto=proto,
                                       hlen=hlen, plen=plen, opcode=opcode,
                                       src_mac=self.VIRTUAL_MAC_FOR_VIP, src_ip=self.VIP,
                                       dst_mac=arp_pkt.src_mac, dst_ip=arp_pkt.dst_ip))
        actions = [parser.OFPActionOutput(in_port)]
        out = parser.OFPPacketOut(datapath=datapath,
                                  buffer_id=ofproto.OFP_NO_BUFFER,
                                  in_port=ofproto.OFPP_CONTROLLER,
                                  actions=actions, data=arp_reply.data)
        datapath.send_msg(out)
        self.logger.info(f"ARP Reply sent for VIP {self.VIP} ({self.VIRTUAL_MAC_FOR_VIP}) to {arp_pkt.src_ip} on port {in_port}")
        match_arp_reply = parser.OFPMatch(eth_type=0x0806,
                                          arp_tpa=self.VIP,
                                          arp_op=arp.ARP_REQUEST,
                                          in_port=in_port)
        actions_arp_reply = [
            parser.OFPActionSetField(eth_src=self.VIRTUAL_MAC_FOR_VIP),
            parser.OFPActionSetField(eth_dst=eth_pkt.src),
            parser.OFPActionSetField(arp_spa=self.VIP),
            parser.OFPActionSetField(arp_sha=self.VIRTUAL_MAC_FOR_VIP),
            parser.OFPActionSetField(arp_tpa=arp_pkt.src_ip),
            parser.OFPActionSetField(arp_tha=arp_pkt.src_mac),
            parser.OFPActionSetField(arp_op=arp.ARP_REPLY),
            parser.OFPActionOutput(in_port)
        ]
        self.add_flow(datapath, 20, match_arp_reply, actions_arp_reply)
        self.logger.info(f"FlowMod instalado para respostas ARP automáticas para {self.VIP} no switch {datapath.id}.")

    def forward_l2_packet(self, msg, datapath, ofproto, parser, in_port, dst_mac):
        dpid = datapath.id
        if dst_mac in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst_mac]
        else:
            out_port = ofproto.OFPP_FLOOD
        actions = [parser.OFPActionOutput(out_port)]
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst_mac)
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.add_flow(datapath, 1, match, actions, msg.buffer_id)
                return
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data
        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def _port_status_handler(self, ev):
        msg = ev.msg
        reason = msg.reason
        port_no = msg.desc.port_no
        ofproto = msg.datapath.ofproto
        if reason == ofproto.OFPPR_ADD:
            self.logger.info("Porta adicionada: %s", port_no)
        elif reason == ofproto.OFPPR_DELETE:
            self.logger.info("Porta deletada: %s", port_no)
        elif reason == ofproto.OFPPR_MODIFY:
            self.logger.info("Porta modificada: %s", port_no)
        else:
            self.logger.info("Estado da porta ilegal: %s %s", port_no, reason)
