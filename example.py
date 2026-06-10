"""
example.py — dimostrazione d'uso + export su JSON/CSV.
Esegui:  python example.py
"""
import csv
import json
from pathlib import Path

from soccerstats import SoccerStats
from footystats import FootyStats
# from sofascore import SofaScore   # richiede Playwright (browser headless)

OUT = Path("output")
OUT.mkdir(exist_ok=True)


def export_json(rows, name):
    (OUT / f"{name}.json").write_text(
        json.dumps([r.to_dict() if hasattr(r, "to_dict") else r for r in rows],
                   ensure_ascii=False, indent=2),
        encoding="utf-8")


def export_csv(rows, name):
    if not rows:
        return
    data = [r.to_dict() if hasattr(r, "to_dict") else r for r in rows]
    with (OUT / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(data[0].keys()))
        writer.writeheader()
        writer.writerows(data)


def demo_soccerstats():
    print("=== SoccerStats: classifica Serie A ===")
    ss = SoccerStats(min_interval=2.0)
    standings = ss.league_standings("italy")
    for s in standings[:10]:
        print(f"{s.position:>2}. {s.team:<20} {s.points} pt "
              f"({s.won}-{s.drawn}-{s.lost})")
    export_json(standings, "serie_a_standings")
    export_csv(standings, "serie_a_standings")
    print(f"-> salvati in {OUT}/serie_a_standings.json/.csv")


def demo_footystats():
    print("\n=== FootyStats: tabelle della pagina ===")
    fs = FootyStats(min_interval=2.5)
    table = fs.biggest_table("italy/serie-a")
    for row in table[:5]:
        print(row)


def demo_sofascore():
    print("\n=== SofaScore: statistiche partita (browser headless) ===")
    # from sofascore import SofaScore
    # sofa = SofaScore(min_interval=2.0)
    # stats = sofa.match_statistics("https://www.sofascore.com/...URL_PARTITA...")
    # for st in stats:
    #     print(f"{st.label}: {st.home} - {st.away}")
    print("  Scommenta e inserisci l'URL di una partita (serve 'playwright install chromium').")


if __name__ == "__main__":
    demo_soccerstats()
    # demo_footystats()
    # demo_sofascore()
