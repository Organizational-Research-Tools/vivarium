
# Plan based on what we know:
# Same recipe → very different results per project (lab_b confirmed)
# 
# Our per-project status:
status = {
    'QP-4476': {'PL':'PL-57', 'heat': 78.78, 'strength': 7.25, 'water': 81.65, 
                'note': 'GG7 recipe PASSES all — need GG7-free version'},
    'QP-6572': {'PL':'PL-57', 'heat': None, 'strength': None, 'water': None,
                'note': 'No data — lab_b finds low strength (4.86). Need to explore.'},
    'QP-6843': {'PL':'PL-57', 'heat': 72.92, 'strength': 7.19, 'water': 72.73,
                'note': 'Heat low, water low. Need better recipe.'},
    'QP-7212': {'PL':'PL-95', 'heat': 78.21, 'strength': 7.18, 'water': 73.46,
                'note': 'Water fails badly (-11 steps). Need different AP2/AP3/joint.'},
    'QP-3473': {'PL':'PL-95', 'heat': 78.08, 'strength': 7.23, 'water': 73.07,
                'note': 'Water fails badly (-12 steps). Same water problem.'},
    'QP-8607': {'PL':'PL-95', 'heat': None, 'strength': None, 'water': None,
                'note': 'No data. Likely water problem like other PL-95.'},
    'QP-3089': {'PL':'PL-98', 'heat': 78.21, 'strength': 6.73, 'water': 79.14,
                'note': 'Strength fails (-12 steps). lab_b finds 7.21 on QP-3089 v3!'},
    'QP-8265': {'PL':'PL-98', 'heat': 78.65, 'strength': 6.66, 'water': 79.03,
                'note': 'Strength fails (-15 steps). Need different recipe.'},
    'QP-7604': {'PL':'PL-98', 'heat': None, 'strength': None, 'water': None,
                'note': 'No data.'},
}

print("=== PROJECT-BY-PROJECT STATUS ===")
for proj, s in status.items():
    ht = f"{s['heat']:.2f}" if s['heat'] else "?"
    st = f"{s['strength']:.2f}" if s['strength'] else "?"
    wa = f"{s['water']:.2f}" if s['water'] else "?"
    hp = "✓" if s['heat'] and s['heat'] >= 77.5 else ("✗" if s['heat'] else "?")
    sp = "✓" if s['strength'] and s['strength'] >= 7.1 else ("✗" if s['strength'] else "?")
    wp = "✓" if s['water'] and s['water'] >= 78.0 else ("✗" if s['water'] else "?")
    print(f"  {proj} ({s['PL']}): heat={ht}{hp} str={st}{sp} water={wa}{wp}")
    print(f"    → {s['note']}")
print()
print("Key insight: SAME recipe → DIFFERENT results per project (projects have different baselines)")
print()
print("Priority actions:")
print("1. QP-4476: Create GG7-free version (JA8,3HW,M2P,...) → should pass all (margin ~3 steps)")
print("2. QP-7212/3473/8607: Fix water — change AP2/joint/AP3 interaction triple")
print("3. QP-3089/8265/7604: Fix strength — lab_b has v3 for QP-3089 that gives 7.21!")
print("4. QP-6572/6843: Need exploratory data — both project-specific baselines unknown")
