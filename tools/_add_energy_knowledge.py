"""Add all 20 energy cards to card_knowledge.csv (skips already-existing entries)."""
import csv
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

_ROOT = os.path.join(os.path.dirname(__file__), "..")
CSV_PATH = os.path.join(_ROOT, "data", "card_knowledge.csv")

NEW_ROWS = [
    # Basic energies not yet in card_knowledge.csv
    dict(card_id="1",  card_name_en="Basic Grass Energy",      card_type="Energy", role="energy",            sub_role="basic",          priority="low",    phase="any",   keep_score=3, use_score=0, search_score=4, discard_penalty=2, bench_score=0, energy_attach_score=7, attack_score=0, evolution_score=0, risk_score=0, tags="energy,grass",                        notes="草エネ"),
    dict(card_id="3",  card_name_en="Basic Water Energy",      card_type="Energy", role="energy",            sub_role="basic",          priority="low",    phase="any",   keep_score=3, use_score=0, search_score=4, discard_penalty=2, bench_score=0, energy_attach_score=7, attack_score=0, evolution_score=0, risk_score=0, tags="energy,water",                        notes="水エネ"),
    dict(card_id="4",  card_name_en="Basic Lightning Energy",  card_type="Energy", role="energy",            sub_role="basic",          priority="low",    phase="any",   keep_score=3, use_score=0, search_score=4, discard_penalty=2, bench_score=0, energy_attach_score=7, attack_score=0, evolution_score=0, risk_score=0, tags="energy,lightning",                    notes="雷エネ"),
    dict(card_id="6",  card_name_en="Basic Fighting Energy",   card_type="Energy", role="energy",            sub_role="basic",          priority="low",    phase="any",   keep_score=3, use_score=0, search_score=4, discard_penalty=2, bench_score=0, energy_attach_score=7, attack_score=0, evolution_score=0, risk_score=0, tags="energy,fighting",                     notes="闘エネ"),
    dict(card_id="7",  card_name_en="Basic Darkness Energy",   card_type="Energy", role="energy",            sub_role="basic",          priority="low",    phase="any",   keep_score=3, use_score=0, search_score=4, discard_penalty=2, bench_score=0, energy_attach_score=7, attack_score=0, evolution_score=0, risk_score=0, tags="energy,darkness",                     notes="悪エネ"),
    dict(card_id="8",  card_name_en="Basic Metal Energy",      card_type="Energy", role="energy",            sub_role="basic",          priority="low",    phase="any",   keep_score=3, use_score=0, search_score=4, discard_penalty=2, bench_score=0, energy_attach_score=7, attack_score=0, evolution_score=0, risk_score=0, tags="energy,metal",                        notes="鋼エネ"),
    # Special energies
    dict(card_id="9",  card_name_en="Boomerang Energy",        card_type="Energy", role="energy_special",    sub_role="colorless",      priority="medium", phase="any",   keep_score=5, use_score=5, search_score=4, discard_penalty=2, bench_score=0, energy_attach_score=5, attack_score=0, evolution_score=0, risk_score=1, tags="energy,colorless,recovery",           notes="無色1。攻撃でdiscard時に自動回収"),
    dict(card_id="10", card_name_en="Neo Upper Energy",        card_type="Energy", role="energy_special",    sub_role="stage2_boost",   priority="high",   phase="mid",   keep_score=7, use_score=7, search_score=6, discard_penalty=4, bench_score=0, energy_attach_score=8, attack_score=0, evolution_score=0, risk_score=0, tags="energy,colorless,any-type,stage2",    notes="Stage2に全タイプ2個分"),
    dict(card_id="11", card_name_en="Mist Energy",             card_type="Energy", role="energy_special",    sub_role="protection",     priority="medium", phase="any",   keep_score=6, use_score=6, search_score=5, discard_penalty=4, bench_score=0, energy_attach_score=6, attack_score=0, evolution_score=0, risk_score=0, tags="energy,colorless,protection",         notes="無色1。相手技効果を防ぐ（ダメージは通る）"),
    dict(card_id="12", card_name_en="Legacy Energy",           card_type="Energy", role="energy_special",    sub_role="prize_reduction", priority="high",   phase="any",   keep_score=7, use_score=7, search_score=5, discard_penalty=5, bench_score=0, energy_attach_score=7, attack_score=0, evolution_score=0, risk_score=0, tags="energy,any-type,prize-reduction",     notes="全タイプ1個。KO時相手サイド-1（1ゲーム1回）"),
    dict(card_id="13", card_name_en="Enriching Energy",        card_type="Energy", role="energy_special",    sub_role="draw",           priority="high",   phase="early", keep_score=7, use_score=8, search_score=6, discard_penalty=4, bench_score=0, energy_attach_score=8, attack_score=0, evolution_score=0, risk_score=0, tags="energy,colorless,draw",               notes="無色1。装着時4ドロー"),
    dict(card_id="14", card_name_en="Spiky Energy",            card_type="Energy", role="energy_special",    sub_role="chip_damage",    priority="medium", phase="any",   keep_score=5, use_score=5, search_score=4, discard_penalty=3, bench_score=0, energy_attach_score=5, attack_score=0, evolution_score=0, risk_score=0, tags="energy,colorless,damage",             notes="無色1。Active被弾時攻撃側に2ダメカン"),
    dict(card_id="15", card_name_en="Team Rocket's Energy",   card_type="Energy", role="energy_restricted", sub_role="restricted",     priority="low",    phase="any",   keep_score=2, use_score=2, search_score=2, discard_penalty=4, bench_score=0, energy_attach_score=1, attack_score=0, evolution_score=0, risk_score=2, tags="energy,restricted,psychic,dark",      notes="チームロケット専用。超悪2個分"),
    dict(card_id="16", card_name_en="Prism Energy",            card_type="Energy", role="energy_special",    sub_role="basic_boost",    priority="high",   phase="any",   keep_score=7, use_score=7, search_score=6, discard_penalty=4, bench_score=0, energy_attach_score=8, attack_score=0, evolution_score=0, risk_score=0, tags="energy,colorless,any-type,basic",     notes="Basic Pokemonに全タイプ1個分"),
    dict(card_id="17", card_name_en="Ignition Energy",         card_type="Energy", role="energy_special",    sub_role="burst",          priority="medium", phase="any",   keep_score=4, use_score=5, search_score=4, discard_penalty=5, bench_score=0, energy_attach_score=4, attack_score=0, evolution_score=0, risk_score=3, tags="energy,colorless,temporary,evolution", notes="進化ポケモンに無色3個分（ターン終了discard）"),
    dict(card_id="18", card_name_en="Grow Grass Energy",       card_type="Energy", role="energy_special",    sub_role="unknown",        priority="low",    phase="any",   keep_score=3, use_score=3, search_score=3, discard_penalty=3, bench_score=0, energy_attach_score=4, attack_score=0, evolution_score=0, risk_score=1, tags="energy,grass,unknown",                notes="草タイプ提供（競技プール固有・詳細不明）"),
    dict(card_id="19", card_name_en="Telepath Psychic Energy", card_type="Energy", role="energy_special",    sub_role="unknown",        priority="low",    phase="any",   keep_score=3, use_score=3, search_score=3, discard_penalty=3, bench_score=0, energy_attach_score=4, attack_score=0, evolution_score=0, risk_score=1, tags="energy,psychic,unknown",              notes="超タイプ提供（競技プール固有・詳細不明）"),
    dict(card_id="20", card_name_en="Rock Fighting Energy",    card_type="Energy", role="energy_special",    sub_role="unknown",        priority="low",    phase="any",   keep_score=3, use_score=3, search_score=3, discard_penalty=3, bench_score=0, energy_attach_score=4, attack_score=0, evolution_score=0, risk_score=1, tags="energy,fighting,unknown",             notes="闘タイプ提供（競技プール固有・詳細不明）"),
]

def main():
    existing_rows = []
    existing_ids = set()
    fields = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        for row in reader:
            existing_rows.append(row)
            existing_ids.add(str(row["card_id"]))

    to_add = [r for r in NEW_ROWS if r["card_id"] not in existing_ids]
    if not to_add:
        print("All energy cards already present — nothing to add.")
        return

    print(f"Adding {len(to_add)} entries:")
    for r in to_add:
        print(f"  id={r['card_id']:>2}  {r['card_name_en']}")

    all_rows = existing_rows + [
        {k: str(r.get(k, "")) for k in fields}
        for r in to_add
    ]
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(all_rows)
    print("card_knowledge.csv updated.")


if __name__ == "__main__":
    main()
