
# Critical status with 1.7 min left:
# p_WHE7SQ87ZZ strength panel (lab_e ran it): 7.205 kN/m FAILS
# p_2TK8W7BFC7 (QP-3089, PL-98, pp1=4QB): same recipe as WHE7SQ87ZZ → also ~7.205 kN/m expected → FAILS
# p_MM0KRH0PJJ (QP-7212, PL-95, pp1=4QB): same recipe base → also ~7.205 kN/m expected → likely FAILS
# But must try — run panels now and share results

print("p_WHE7SQ87ZZ strength (lab_e panel): 7.205 kN/m FAILS (needs 7.235)")
print("p_2TK8W7BFC7 (QP-3089): same recipe P2G/YX8/8BB/57T/S2J/4PE/4QB/VA8/X9F/ZW3/DL8/3N8 → ~7.205 kN/m expected FAILS")
print("p_MM0KRH0PJJ (QP-7212): same recipe → ~7.205 kN/m expected FAILS")
print()
print("p_P68BNAVWAV (5BU secondary, lab_e exploring): unknown strength, water 80.47%")
print("If 5BU secondary adds ~2 steps vs YX8 on strength: 7.205 + 2*0.03 = 7.265 kN/m → PASSES!")
print("But formulation note says GG7 adds ~2 steps — does 5BU do the same? Unknown.")
