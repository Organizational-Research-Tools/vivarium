
import pandas as pd

df = pd.read_csv('records.csv')

# Find prototypes that have been granted to me (I can measure them) but don't have strength panels
# Group by project and prototype_id to see what's available
panels = df[df['kind']=='panel'].groupby(['project','prototype_id','test'])['value'].agg(['mean','count']).reset_index()

print("=== ALL PANELS BY PROJECT ===")
for proj in sorted(panels['project'].unique()):
    sub = panels[panels['project']==proj]
    print(f"\n{proj}:")
    for _, row in sub.iterrows():
        status = "✓" if (
            (row['test']=='heat' and row['mean']>=78.25) or
            (row['test']=='strength' and row['mean']>=7.19) or
            (row['test']=='water' and row['mean']>=79.2)
        ) else "✗"
        print(f"  {row['prototype_id'][:12]} {row['test']:10s} {row['mean']:.4f} {status}")
