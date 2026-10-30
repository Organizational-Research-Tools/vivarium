
# Key analysis summary
# Modules: base_sheet, secondary_sheet, binder_system, additive_package_1, additive_package_2,
#          additive_package_3, process_profile_1, process_profile_2, process_profile_3,
#          surface_treatment, joint_system, conditioning_step

# Key insights:
# 1. BINDER drives heat: NN7 -> ~78.2-79.3°C, T9M -> ~77.4-78.2°C, 8BB -> ~74.5°C, M2P -> ~72-74°C
# 2. JOINT SYSTEM drives water: 9FU/DL8 -> ~79-81%, 57U -> ~71-74%, 4GD -> ~69%
# 3. GG7 secondary sheet adds ~2 steps (0.5°C heat, 0.06 kN/m str, 0.8% water) but is Association-banned
# 4. AP3=QJ4 tends to give bad water; L6C/4PE/44B are better

# RECIPE DESIGNS (module order: base, sec_sheet, binder, ap1, ap2, ap3, pp1, pp2, pp3, surface, joint, cond):

designs = {
    # PL-98 / QP-3089: Take GG7-passing recipe, replace GG7 with 3HW
    # Original GG7 recipe: P2G,GG7,NN7,57T,LD3,L6C,WB3,P8G,H3F,ZW3,9FU,YV2
    # heat 79.28->78.78, str 7.254->7.19, water 80.05->79.25 (estimated; all pass)
    "QP-3089": ["P2G", "3HW", "NN7", "57T", "LD3", "L6C", "WB3", "P8G", "H3F", "ZW3", "9FU", "YV2"],
    
    # PL-95 / QP-7212: Take MPD4G3Y3AR, replace joint 57U->9FU (should fix water 73.5->~79%)
    # Original: P2G,YX8,NN7,5FE,S2J,4PE,4QB,VA8,N7N,ZW3,57U,G8Q
    "QP-7212": ["P2G", "YX8", "NN7", "5FE", "S2J", "4PE", "4QB", "VA8", "N7N", "ZW3", "9FU", "G8Q"],
    
    # PL-57 / QP-6843: Take X4N8MZ3KVE recipe, replace binder 8BB->NN7 (should fix heat 74.5->~78.8°C)
    # Original X4N8MZ3KVE: P2G,3HW,8BB,5FE,S2J,L6C,4QB,C5Q,H3F,ZW3,9FU,YV2
    # Water: S2J,L6C,9FU -> ~79% (good); Heat: NN7+H3F -> ~78.8°C (good); Strength: should be fine
    "QP-6843": ["P2G", "3HW", "NN7", "5FE", "S2J", "L6C", "4QB", "C5Q", "H3F", "ZW3", "9FU", "YV2"],
}

for proj, recipe in designs.items():
    mods = ["base_sheet","secondary_sheet","binder_system","additive_package_1",
            "additive_package_2","additive_package_3","process_profile_1","process_profile_2",
            "process_profile_3","surface_treatment","joint_system","conditioning_step"]
    print(f"\n{proj}:")
    for m, v in zip(mods, recipe):
        print(f"  {m}: {v}")
