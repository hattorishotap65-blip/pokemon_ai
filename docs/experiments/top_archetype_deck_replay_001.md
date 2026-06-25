# Top Archetype Deck Replay 001

## Purpose

Top Episodes との行動差がデッキ差かロジック差かを判別する。Top 層で使われている Crustle deck を再現し、#164 ロジックで動かして比較する。

## Reproduced Deck: Crustle (strayuru)

Source: Top Episode 81428299, player strayuru (WIN)

| Card ID | Name | Count | Role |
|---------|------|-------|------|
| 1 | Basic Grass Energy | 11 | Energy |
| 11 | Mist Energy | 4 | Special Energy (protection) |
| 14 | Spiky Energy | 4 | Special Energy (chip damage) |
| 18 | Grow Grass Energy | 4 | Special Energy |
| 344 | Dwebble | 4 | Evolution base |
| 345 | Crustle | 4 | Main attacker (120 dmg) |
| 1086 | Buddy-Buddy Poffin | 4 | Search |
| 1120 | Crushing Hammer | 4 | Disruption |
| 1147 | Jumbo Ice Cream | 4 | Item |
| 1152 | Poke Pad | 4 | Item reuse |
| 1159 | Hero's Cape | 1 | ACE SPEC (HP+) |
| 1212 | Cook | 4 | Supporter |
| 1227 | Lillie's Determination | 4 | Supporter |
| 1235 | Waitress | 4 | Supporter |

File: `experiments/decks/top_crustle_replay.csv` (60 cards, exact reproduction)

## Experiment

- Deck: top_crustle_replay.csv (temporary swap, deck.csv restored after)
- Logic: #164 (ml_hybrid ON, bonus=10, area_fix_only, ionos active attach, attack_plan ON)
- Note: ionos-specific rules (Voltorb scoring etc) don't apply to Crustle deck

## 100g Results

### Three-Way Comparison

| Metric | Top Episodes | #164 Iono | Crustle Replay | Interpretation |
|--------|-------------|-----------|----------------|----------------|
| **PLAY %** | **26.1%** | **14.0%** | **22.2%** | **Deck difference** |
| ATTACK % | 9.2% | 7.4% | 15.4% | Deck difference |
| **Attach to active** | **81.2%** | **54.4%** | **92.2%** | **Deck difference** |
| Active starved | 0 | 180 | 0 | Deck difference |
| Bench oversetup | 0 | 52 | 0 | Deck difference |
| Attack when legal | 31.9% | 89.8% | 85.4% | **Partial logic difference** |
| END % | 3.3% | 3.4% | 11.2% | Deck/logic |
| END+legal_attack | 5 | 0 | 0 | OK |
| zero_damage | 0 | 0 | 0 | OK |
| miss_KO | N/A | 7 | 113 | Crustle miss_KO is high |
| KO capture | N/A | 97.3% | 86.0% | Crustle lower |

### Safety
- errors=0, timeouts=0, zero_damage=0 for all

## Analysis

### Deck difference explains most gaps

1. **PLAY rate**: Iono 14% → Crustle 22.2% — Crustle deck has more trainer cards and supporters
2. **Attach to active**: Iono 54.4% → Crustle 92.2% — Crustle has only one Pokemon line (Dwebble/Crustle), so energy always goes to the main attacker
3. **Active starved / bench oversetup**: Both 0 with Crustle — single attacker line means no energy distribution problem

### Attack when legal is partially a logic issue

Crustle replay shows 85.4% attack when legal — closer to Iono (89.8%) than Top (31.9%). This suggests:
- Top agents with similar decks may have more sophisticated pre-attack logic
- Our agent attacks as soon as possible, even when trainer plays could strengthen the next turn
- However, the difference may also reflect different Top deck strategies (some decks have complex multi-step turns)

### Crustle deck has high miss_KO (113)

The #164 logic is not tuned for Crustle. miss_KO=113 (86% capture) is much worse than Iono's 97.3%. This is expected — ionos_rules scoring doesn't help Crustle.

## Conclusion

**The PLAY rate / attach_to_active / active_starved gaps are primarily deck differences, not logic problems.**

- Iono deck has multiple Pokemon lines (Voltorb, Tadbulb/Bellibolt, Wattrel/Kilowattrel) → energy is distributed
- Crustle has one line → energy concentrates on active → attach_to_active ~92%
- Iono deck has fewer trainer cards → lower PLAY rate is structural

**Attack when legal (85-90%) is a potential logic improvement area**, but:
- The gap vs Top (32%) is partly because Top includes setup-heavy decks
- Reducing attack-when-legal without careful design would risk miss_KO and KO capture

## Recommendation

1. **Stop trying to match Top PLAY rate / attach_active** — these gaps are deck-structural
2. **Focus Iono improvements on Iono-specific metrics** — ionos_rules attach priority, Voltorb damage optimization
3. **#164 remains the primary candidate** — logic is sound for the Iono deck
4. **Consider Crustle deck switch only if** Iono ceiling is reached and Crustle shows clear leaderboard advantage
