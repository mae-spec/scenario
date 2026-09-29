"""Verrou « hors ligne » : interdit toute connexion sortante depuis le processus.

L'application n'a besoin d'aucun accès réseau sortant : elle ne fait qu'écouter les requêtes du
réseau local. Ce verrou le garantit au niveau du processus Python : toute tentative de connexion
vers une adresse autre que la boucle locale, ou toute résolution DNS d'un nom externe, lève une
erreur (et est journalisée). Même une bibliothèque tierce ne pourrait donc rien envoyer en ligne.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
import sys

log = logging.getLogger("scenario.offline")

_LOCAL_NAMES = {None, "", "localhost", "localhost.localdomain", "ip6-localhost"}
_installed = False


class OutboundBlocked(ConnectionRefusedError):
    pass


def _is_loopback(host) -> bool:
    if host in _LOCAL_NAMES:
        return True
    try:
        return ipaddress.ip_address(str(host).split("%")[0]).is_loopback
    except ValueError:
        return False


def _is_numeric_or_wildcard(host) -> bool:
    if host in _LOCAL_NAMES or host in ("0.0.0.0", "::"):
        return True
    try:
        ipaddress.ip_address(str(host).split("%")[0])
        return True
    except ValueError:
        return False


def install() -> None:
    global _installed
    if _installed:
        return
    _installed = True
    orig_connect = socket.socket.connect
    orig_connect_ex = socket.socket.connect_ex
    orig_getaddrinfo = socket.getaddrinfo

    def check(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            host = address[0] if isinstance(address, tuple) else address
            if not _is_loopback(host):
                log.error("Connexion sortante bloquée vers %s", host)
                raise OutboundBlocked(f"Connexion sortante interdite (mode hors ligne) : {host}")

    def connect(self, address):
        check(self, address)
        return orig_connect(self, address)

    def connect_ex(self, address):
        check(self, address)
        return orig_connect_ex(self, address)

    def getaddrinfo(host, *args, **kwargs):
        h = host.decode() if isinstance(host, bytes) else host
        if not _is_numeric_or_wildcard(h):
            log.error("Résolution DNS bloquée : %s", h)
            raise socket.gaierror(socket.EAI_NONAME, f"Résolution DNS interdite (mode hors ligne) : {h}")
        return orig_getaddrinfo(host, *args, **kwargs)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.getaddrinfo = getaddrinfo
    print("Mode hors ligne actif : aucune connexion sortante n'est possible.", file=sys.stderr, flush=True)
