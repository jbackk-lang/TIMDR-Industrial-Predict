"""
obd_source.py — most z prawdziwego OBD-II (python-obd) do formatu CSV
oczekiwanego przez monitor.py
====================================================================
Odpytuje prawdziwy adapter OBD-II (ELM327 po USB/Bluetooth) - albo,
do testowania bez fizycznego auta, prawdziwy emulator protokolu ELM327
(pakiet `ELM327-emulator`, pip) - i dopisuje kolejne wiersze do
rosnacego pliku CSV w formacie, jakiego oczekuje `monitor.py`
(naglowek `t` + jedna kolumna na kazdy PID).

UCZCIWA GRANICA TEGO, CO JEST TU "REALNE": kod uzywa prawdziwej,
niezmodyfikowanej biblioteki `python-obd` i mowi prawdziwym protokolem
ELM327/ISO 15765-4 (CAN). Jesli podasz prawdziwy port szeregowy
prawdziwego adaptera podlaczonego do prawdziwego auta, ten skrypt
dziala z realnym pojazdem bez zadnych zmian. W TYM SANDBOXIE nie ma
fizycznego auta ani adaptera USB, wiec zweryfikowano go tutaj wylacznie
wobec `ELM327-emulator` (niezalezny, prawdziwy symulator protokolu
ELM327 - nie napisany na potrzeby tej sesji) - to test protokolu i
kodu integracyjnego, NIE test na prawdziwym pojezdzie.

PRZYKLADY:
  Prawdziwy adapter (Linux, port szeregowy):
    python obd_source.py --port /dev/ttyUSB0 --csv silnik_live.csv --interval 1
  Prawdziwy adapter (Windows):
    python obd_source.py --port COM5 --csv silnik_live.csv --interval 1
  Test wobec emulatora protokolu (bez auta, patrz README):
    python obd_source.py --port /dev/pts/3 --csv silnik_live.csv --interval 0.5 --n 20

Domyslny zestaw PID-ow (--pids) to podzbior dostepny na WIEKSZOSCI aut
(silnikowe/emisyjne) - realny sprzet moze wspierac wiecej albo mniej,
`--list-supported` pokazuje co dany adapter faktycznie oferuje.
"""
import argparse
import csv
import os
import sys
import time

import obd


DEFAULT_PIDS = [
    "RPM", "SPEED", "COOLANT_TEMP", "INTAKE_TEMP", "THROTTLE_POS",
    "ENGINE_LOAD", "MAF", "INTAKE_PRESSURE",
]


def resolve_commands(pid_names):
    cmds = []
    for name in pid_names:
        cmd = getattr(obd.commands, name, None)
        if cmd is None:
            print(f"UWAGA: PID '{name}' nie istnieje w python-obd - pomijam.", file=sys.stderr)
            continue
        cmds.append(cmd)
    return cmds


def main():
    ap = argparse.ArgumentParser(description="Most OBD-II (python-obd) -> CSV dla monitor.py")
    ap.add_argument("--port", required=True, help="Port szeregowy adaptera (np. /dev/ttyUSB0, COM5) lub pty emulatora")
    ap.add_argument("--csv", default=None, help="Docelowy plik CSV (dopisywany, tworzony jesli nie istnieje) - wymagany, chyba ze --list-supported")
    ap.add_argument("--pids", nargs="*", default=DEFAULT_PIDS, help="Lista nazw PID-ow python-obd do odpytywania")
    ap.add_argument("--interval", type=float, default=1.0, help="Sekund miedzy kolejnymi odczytami")
    ap.add_argument("--n", type=int, default=None, help="Liczba odczytow (domyslnie: bez limitu, do Ctrl+C)")
    ap.add_argument("--list-supported", action="store_true",
                     help="Polacz sie, wypisz PID-y faktycznie wspierane przez ten adapter/pojazd, i wyjdz")
    ap.add_argument("--fast", action="store_true", help="Tryb 'fast' python-obd (mniej bezpieczny, szybszy)")
    args = ap.parse_args()
    if not args.list_supported and not args.csv:
        ap.error("--csv jest wymagane (chyba ze uzywasz --list-supported)")

    conn = obd.OBD(args.port, fast=args.fast, timeout=10)
    if not conn.is_connected():
        print(f"BLAD: nie udalo sie polaczyc z {args.port} (status: {conn.status()})", file=sys.stderr)
        sys.exit(1)

    print(f"Polaczono: {args.port}  status={conn.status()}  protokol={conn.protocol_name()}")

    if args.list_supported:
        supported = sorted(c.name for c in conn.supported_commands if c.name.isupper())
        print(f"PID-y wspierane przez ten adapter/pojazd ({len(supported)}):")
        for name in supported:
            print(f"  {name}")
        conn.close()
        return

    cmds = resolve_commands(args.pids)
    if not cmds:
        print("BLAD: zadny z podanych PID-ow nie istnieje w python-obd.", file=sys.stderr)
        conn.close()
        sys.exit(1)

    file_exists = os.path.exists(args.csv) and os.path.getsize(args.csv) > 0
    f = open(args.csv, "a", newline="")
    writer = csv.writer(f)
    if not file_exists:
        writer.writerow(["t"] + [c.name for c in cmds])

    t0 = time.time()
    i = 0
    try:
        while args.n is None or i < args.n:
            row_t = time.time() - t0
            row = [row_t]
            values = []
            for c in cmds:
                r = conn.query(c)
                v = r.value
                # python-obd zwraca Pint Quantity dla wiekszosci PID-ow -
                # bierzemy magnitude (surowa liczbe), jednostka jest stala
                # per-PID wiec i tak nie zmieni sie miedzy wierszami.
                if hasattr(v, "magnitude"):
                    v = v.magnitude
                if v is None:
                    v = float("nan")
                values.append(v)
            writer.writerow([row_t] + values)
            f.flush()
            print(f"  t={row_t:6.2f}s  " + "  ".join(f"{c.name}={v}" for c, v in zip(cmds, values)))
            i += 1
            if args.n is None or i < args.n:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nZatrzymano.")
    finally:
        f.close()
        conn.close()


if __name__ == "__main__":
    main()
