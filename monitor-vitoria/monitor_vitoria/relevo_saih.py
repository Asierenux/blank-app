"""Relevo del SAIH Ebro para la app del iPhone.

El iPhone no acepta el certificado de www.saihebro.com, así que no puede leer sus fichas.
Este programa lo ejecuta GitHub cada ~20 minutos en sus servidores:

  1. Descarga la ficha de cada estación (embalses y aforos) del catálogo.
  2. Si la web no envía completa su cadena de certificados (un error típico que Windows
     tolera y el iPhone no), busca el certificado intermedio que falta en la dirección
     oficial que indica el propio certificado (AIA) y VUELVE A COMPROBARLO TODO hasta una
     autoridad raíz de confianza. No se desactiva ninguna comprobación de seguridad.
  3. Guarda los valores de los últimos 7 días en saih.json, que GitHub publica en una
     dirección con certificado válido (raw.githubusercontent.com) para que la lea el iPhone.

Uso:  python -m monitor_vitoria.relevo_saih anterior.json salida.json
"""

from __future__ import annotations

import json
import socket
import ssl
import sys
import time
import urllib.request
from datetime import datetime, timezone

import certifi

from .recolectores.saih import CATALOGO, RecolectorSaih, SENALES

HOST = "www.saihebro.com"
URL = "https://www.saihebro.com/tiempo-real/estacion-{tipo}-{codigo}-{slug}"
NAVEGADOR = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/130.0 Safari/537.36")
DIAS = 7


def contexto_basico() -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=certifi.where())
    # Que un certificado intermedio añadido NUNCA cuente como raíz de confianza
    if hasattr(ssl, "VERIFY_X509_PARTIAL_CHAIN"):
        ctx.verify_flags &= ~ssl.VERIFY_X509_PARTIAL_CHAIN
    return ctx


def probar(ctx: ssl.SSLContext) -> None:
    with socket.create_connection((HOST, 443), timeout=20) as s:
        with ctx.wrap_socket(s, server_hostname=HOST):
            pass


def describir_certificado() -> str:
    """Datos del certificado que presenta la web (para el registro), sin confiar en él."""
    from cryptography import x509
    pem = ssl.get_server_certificate((HOST, 443), timeout=20)
    c = x509.load_pem_x509_certificate(pem.encode())
    return (f"emisor={c.issuer.rfc4514_string()} | sujeto={c.subject.rfc4514_string()} | "
            f"válido hasta={c.not_valid_after_utc:%Y-%m-%d}")


def intermedios_aia(max_niveles: int = 3) -> str:
    """Descarga, siguiendo las direcciones AIA, los certificados intermedios que la web no envía."""
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import Encoding
    from cryptography.hazmat.primitives.serialization.pkcs7 import load_der_pkcs7_certificates
    from cryptography.x509.oid import AuthorityInformationAccessOID, ExtensionOID

    actual = x509.load_pem_x509_certificate(ssl.get_server_certificate((HOST, 443), timeout=20).encode())
    pems = []
    for _ in range(max_niveles):
        try:
            aia = actual.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS).value
        except x509.ExtensionNotFound:
            break
        urls = [d.access_location.value for d in aia if d.access_method == AuthorityInformationAccessOID.CA_ISSUERS]
        if not urls:
            break
        datos = urllib.request.urlopen(urls[0], timeout=20).read()
        try:
            siguiente = x509.load_der_x509_certificate(datos)
        except ValueError:
            try:
                siguiente = x509.load_pem_x509_certificate(datos)
            except ValueError:
                siguiente = load_der_pkcs7_certificates(datos)[0]
        pems.append(siguiente.public_bytes(Encoding.PEM).decode())
        if siguiente.issuer == siguiente.subject:      # llegamos a una raíz: no hace falta más
            break
        actual = siguiente
    return "".join(pems)


def contexto() -> tuple[ssl.SSLContext, str]:
    ctx = contexto_basico()
    try:
        probar(ctx)
        return ctx, "cadena de certificados completa"
    except ssl.SSLCertVerificationError as e:
        print(f"Certificado no verificable tal cual: {e.verify_message}. {describir_certificado()}")
    ctx = contexto_basico()
    ctx.load_verify_locations(cadata=intermedios_aia())
    probar(ctx)        # si sigue sin validar hasta una raíz de confianza, aquí falla y se para
    return ctx, "cadena completada con el certificado intermedio oficial (AIA)"


def descargar(ctx: ssl.SSLContext, url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": NAVEGADOR, "Accept": "text/html"})
    with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def fusionar(anterior: dict, nuevas: dict[str, dict[str, list]], ahora_ms: int) -> dict:
    """Añade los valores nuevos a las series guardadas, sin duplicar, y quita lo de hace más de 7 días."""
    limite = ahora_ms - DIAS * 86400_000
    salida = {}
    previas = anterior.get("estaciones", {})
    for e in CATALOGO:
        series = {}
        for senal in SENALES[e.tipo]:
            puntos = {int(t): v for t, v in previas.get(e.id, {}).get("series", {}).get(senal, [])}
            puntos.update({int(t): v for t, v in nuevas.get(e.id, {}).get(senal, [])})
            lista = sorted([t, v] for t, v in puntos.items() if t >= limite)
            if lista:
                series[senal] = lista
        if series:
            salida[e.id] = {"nombre": e.nombre, "tipo": e.tipo, "codigo": e.codigo, "series": series}
    return salida


def main(entrada: str, salida: str) -> int:
    try:
        with open(entrada, encoding="utf-8") as f:
            anterior = json.load(f)
    except (OSError, ValueError):
        anterior = {}
    ahora_ms = int(time.time() * 1000)
    errores: list[str] = []
    nuevas: dict[str, dict[str, list]] = {}
    try:
        ctx, como = contexto()
        print(f"Conexión segura con {HOST}: {como}")
    except Exception as e:  # noqa: BLE001
        ctx, como = None, None
        errores.append(f"No se pudo verificar el certificado de {HOST}: {e}")
    rec = RecolectorSaih(None, None)       # solo usamos su lector de páginas
    for e in CATALOGO:
        if not e.codigo or ctx is None:
            continue
        url = URL.format(tipo="embalses" if e.tipo == "embalse" else "aforos", codigo=e.codigo, slug=e.slug)
        try:
            for l in rec.parsear(e, descargar(ctx, url)):
                senal = l.metrica.split(".", 1)[1]
                t = int(l.momento.timestamp() * 1000)
                nuevas.setdefault(e.id, {}).setdefault(senal, []).append([t, l.valor])
            print(f"{e.id}: {sorted(nuevas.get(e.id, {}))}")
        except Exception as ex:  # noqa: BLE001 — una estación no tumba a las demás
            errores.append(f"{e.nombre}: {type(ex).__name__}: {ex}")
    resultado = {
        "generado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fuente": "SAIH Ebro (www.saihebro.com)",
        "conexion": como,
        "errores": errores,
        "estaciones": fusionar(anterior, nuevas, ahora_ms),
    }
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, separators=(",", ":"))
    for err in errores:
        print("ERROR:", err)
    # Falla (en rojo en GitHub) solo si no se ha podido leer nada
    return 0 if nuevas else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
