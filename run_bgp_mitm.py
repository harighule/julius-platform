#!/usr/bin/env python3
"""Run the BGP MITM subsystem (lab/testing).

This script is a thin entrypoint around backend.services.bgp_mitm.*
"""

import argparse

from backend.services.bgp_mitm import (
    scan_network,
    get_gateway,
    arp_spoof,
    start_sniffer,
    start_modifier,
    start_dns_spoof,
    run_bgp_simulation,
    run_attack,
)


def main():
    parser = argparse.ArgumentParser(description="BGP MITM lab runner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan", help="Scan network via ping sweep")
    p_scan.add_argument("--ip-range", default="192.168.1.0/24")

    p_gateway = sub.add_parser("gateway", help="Print default gateway")

    p_spoof = sub.add_parser("spoof", help="Run ARP spoofing (requires permissions; local LAN)")
    p_spoof.add_argument("--target", required=True)
    p_spoof.add_argument("--gateway", required=True)
    p_spoof.add_argument("--interface", default="eth0")

    p_sniff = sub.add_parser("sniff", help="Start packet sniffer (local interface)")
    p_sniff.add_argument("--interface", default="eth0")
    p_sniff.add_argument("--timeout", type=int, default=None)

    p_modify = sub.add_parser("modify", help="Start transaction modifier (local interface)")
    p_modify.add_argument("--interface", default="eth0")

    p_dns = sub.add_parser("dns-spoof", help="Start mitmproxy DNS spoofing")
    p_dns.add_argument("--interface", default=None)
    p_dns.add_argument("--port", type=int, default=53)

    p_bgp = sub.add_parser("simulate-bgp", help="Run BGP hijack simulation")

    p_attack = sub.add_parser("attack", help="Run full orchestration chain")
    p_attack.add_argument("--target", required=True)
    p_attack.add_argument("--gateway", required=True)
    p_attack.add_argument("--interface", default="eth0")

    args = parser.parse_args()

    if args.cmd == "scan":
        hosts = scan_network(args.ip_range)
        print(hosts)
        return

    if args.cmd == "gateway":
        print(get_gateway())
        return

    if args.cmd == "spoof":
        arp_spoof(args.target, args.gateway, args.interface)
        return

    if args.cmd == "sniff":
        start_sniffer(args.interface, args.timeout)
        return

    if args.cmd == "modify":
        start_modifier(args.interface)
        return

    if args.cmd == "dns-spoof":
        start_dns_spoof(args.interface, args.port)
        return

    if args.cmd == "simulate-bgp":
        run_bgp_simulation()
        return

    if args.cmd == "attack":
        run_attack(args.target, args.gateway, args.interface)
        return


if __name__ == "__main__":
    main()



