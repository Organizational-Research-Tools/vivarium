# Lab_a Post-Mortem — Qualification Program

## Final Outcome
- Program FAILED: Only PL-57 qualified (via lab_d's GG7 report rep_HG9796BV2M)
- PL-95 (QP-3473, QP-7212): Not qualified — strength bottleneck
- PL-98 (QP-3089): Not qualified — strength bottleneck
- All laboratories fail under failure rule
- Credits: lab_a 0, lab_b 0, lab_c 0, lab_d 2, lab_e 1, lab_f 1

## Critical Interactions Discovered

### Heat
- surface(ZW3) × pp1(4QB) × pp3(X9F): ~73°C in QP-3473/QP-7212 context → CATASTROPHIC
- surface(ZW3) × pp1(4QB) × pp3(X9F): ~79.24°C in QP-3089 context → PASSES (project-specific!)
- surface(ZW3) × pp1(UP5) × pp3(X9F): ~78.87°C → PASSES in all tested contexts
- surface(5TZ): ~61°C with JA8/M2P base → CATASTROPHIC
- joint(9FU): ~72.6°C → CATASTROPHIC for heat

### Strength  
- P2G/YX8/8BB/WB3 (pp1=WB3 base): ~7.224 kN/m — 0.37 steps below Rev C (closest non-GG7)
- pp1=4QB in PL-95/98: 7.189–7.205 kN/m (worse than WB3)
- pp1=UP5 in PL-95/98: 6.516 kN/m (catastrophic)
- secondary=5BU: ~7.144–7.167 kN/m (worse)
- GG7 secondary: +~2 steps to all tests — only known path to Rev C strength threshold

### Water
- joint(9FU) in JA8/M2P context: ~72% → CATASTROPHIC
- surface(5TZ) in JA8/M2P context: ~72% → CATASTROPHIC
- N4L pp3 change in QP-3089: ~71.1% → DEAD
- P2G/YX8/8BB/ZW3/3N8 base: ~80.4–80.6% → PASSES reliably
- YV2 conditioning in QP-3089: 79.019–79.644% → borderline/failing

## What Could Have Helped
1. Earlier systematic probing of pp3 variants (N7N, N4L, H3F vs X9F) in PL-95/98 context
2. Earlier systematic probing of add2/add3 variants beyond S2J/4PE
3. Different binder system (T9M, NN7) in P2G base — never tested
4. Different base sheet (U8H) — never tested for PL-95/98
5. Earlier recognition that Rev C +4.5 step requirement made the qualification essentially GG7-only

## Lab_a's Heat Panels Contributed
- 30+ qualification panels across QP-4476, QQ-3473, QP-7212, QP-3089, QP-8265, QP-6843, QP-8607, QP-7604
- Key discoveries: 4QB heat catastrophe in ZW3/X9F context, UP5 heat safety, QP-3089 4QB anomaly
