
# Analyze the QP-7212 situation - ALL three tested recipes fail water with N7N as process_profile_3
# My new p_S87ZV5EJH5 uses X9F - this should fix water!

print("=== QP-7212 ANALYSIS ===")
recipes_7212 = {
    'p_M9C39Z8ZAH': {'recipe': ['P2G','YX8','NN7','5FE','LD3','4PE','4QB','VA8','N7N','7TJ','9FU','YV2'],
                      'heat': 78.200, 'strength': 7.184, 'water': 73.454},
    'p_DQFXMS728T': {'recipe': ['P2G','YX8','NN7','5FE','B3P','4PE','4QB','VA8','N7N','7TJ','9FU','3N8'],
                      'heat': 78.197, 'strength': 7.244, 'water': 73.448},
    'p_ERK3YD03GV': {'recipe': ['P2G','YX8','NN7','5FE','S2J','4PE','4QB','VA8','N7N','7TJ','57U','G8Q'],
                      'heat': 78.222, 'strength': 7.187, 'water': 73.489},
}
for pid, data in recipes_7212.items():
    r = data['recipe']
    print(f"\n{pid}: pp3={r[8]}")
    print(f"  Heat: {data['heat']:.2f} ({'✓' if data['heat']>=77.5 else '✗'}), "
          f"Str: {data['strength']:.3f} ({'✓' if data['strength']>=7.10 else '✗'}), "
          f"Water: {data['water']:.2f} ({'✓' if data['water']>=78.0 else '✗'})")
    print(f"  Recipe: {r}")

print()
print("=== NEW QP-7212 PROTOTYPE (TARGETED) ===")
new_7212 = ['P2G', '3HW', '8BB', '57T', 'S2J', '4PE', 'WB3', 'VA8', 'X9F', 'ZW3', 'DL8', '3N8']
print(f"p_S87ZV5EJH5: {new_7212}")
print(f"  pp3=X9F → expected water ~79-80% ✓")
print(f"  Same as QP-3473 GG7 winner (non-GG7): expected heat ~79.03 ✓, strength ~7.19 ✓")
print(f"  THIS IS MY TOP CANDIDATE for QP-7212 (PL-95)!")

print()
print("=== KEY PROTOTYPE IDs FOR BATCH MEASUREMENT ===")

# All 14 new targeted prototypes
targeted = [
    ('QP-3473', 'p_J6CX8AHRR3', 'GG7→3HW winner'),
    ('QP-3473', 'p_J6CX8AHRR5', 'GG7→5BU winner'),
    ('QP-7212', 'p_S87ZV5EJH5', 'GG7→3HW winner'),
    ('QP-7604', 'p_7AG4536EJQ', 'GG7→3HW winner'),
    ('QP-3089', 'p_YD1Q0XW9S8', 'GG7-adapted NN7+57T'),
    ('QP-3089', 'p_YD1Q0XW9SA', 'GG7→3HW winner'),
    ('QP-8265', 'p_JN5ABZQH8S', 'GG7→3HW winner'),
    ('QP-6572', 'p_T79TZ1Q3JT', 'GG7→3HW winner'),
    ('QP-6572', 'p_T79TZ1Q3JW', 'hybrid NN7+C5Q'),
    ('QP-6572', 'p_T79TZ1Q3JY', 'hybrid 8BB+C5Q'),
    ('QP-6843', 'p_QEPQYC26EE', 'GG7→3HW winner'),
    ('QP-6843', 'p_QEPQYC26EG', 'VA8→C5Q winner'),
    ('QP-4476', 'p_21XPKFZDE3', 'GG7→3HW winner'),
    ('QP-4476', 'p_21XPKFZDE5', 'hybrid 8BB+C5Q'),
]

# Existing exploratory (from 36 registered last session, drop 2 weakest)
exploratory = [
    # QP-6572 (10 of 12 - drop U8H ones with T9M binder)
    'p_BPTS43N4BH', 'p_BPTS43N4BK', 'p_BPTS43N4BN',
    'p_3PHV14GHBT', 'p_3PHV14GHBW', 'p_3PHV14GHBY',
    'p_3PHV14GHC0', 'p_3PHV14GHC2', 'p_3PHV14GHC4',
    'p_3PHV14GHC6', 'p_3PHV14GHC8',
    # p_BPTS43N4BQ (U8H, T9M, 2BR - skip)
    # QP-7212 (12)
    'p_PN0YTD5YEM', 'p_PN0YTD5YEP', 'p_PN0YTD5YER', 'p_PN0YTD5YET',
    'p_PN0YTD5YEW', 'p_PN0YTD5YEY', 'p_PN0YTD5YF0', 'p_PN0YTD5YF2',
    'p_PN0YTD5YF4', 'p_PN0YTD5YF6', 'p_PN0YTD5YF8', 'p_YMXDR5PRDS',
    # QP-3089 (11 of 12 - drop 1)
    'p_B5YVE0HPFX', 'p_B5YVE0HPFZ', 'p_B5YVE0HPG1', 'p_B5YVE0HPG3',
    'p_B5YVE0HPG5', 'p_B5YVE0HPG7', 'p_B5YVE0HPG9', 'p_B5YVE0HPGB',
    'p_B5YVE0HPGD', 'p_B5YVE0HPGF', 'p_B5YVE0HPGH',
    # p_B5YVE0HPGK (YX8, M2P, 4QB - skip)
]

targeted_ids = [t[1] for t in targeted]
all_batch = targeted_ids + exploratory
print(f"Targeted: {len(targeted_ids)}")
print(f"Exploratory: {len(exploratory)}")
print(f"Total batch: {len(all_batch)} (cap=48)")
assert len(all_batch) == 48
